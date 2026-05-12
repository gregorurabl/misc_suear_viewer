import datetime
import io
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageTk

from config import FRAME_INTERVAL, BATTERY_POLL_MS
from enhancer import enhance, enhance_full, DEFAULTS
from recorder import Recorder
from stream_thread import StreamThread
from upscaler import discover_models, upscale_frame, upscale_video, is_available
from stabilizer import Stabilizer, stabilize_video


# --- About window -----------------------------------------------------------

class AboutWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("About Suear Viewer")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        f = ttk.Frame(self, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Suear Viewer", font=("", 14, "bold")).pack()
        ttk.Label(f, text="WiFi Otoscope Camera Viewer").pack(pady=(2, 12))
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(0, 12))
        ttk.Label(f, text="Developed by").pack()
        ttk.Label(f, text="YOUR NAME HERE", font=("", 10, "bold")).pack()  # <-- replace
        ttk.Label(f, text="https://your-homepage.example.com").pack(pady=(2, 2))  # <-- replace
        ttk.Label(f, text="https://github.com/your-username").pack()          # <-- replace
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=12)
        ttk.Label(f, text="Based on Suear-Web-Viewer by SeanPesce",
                  foreground="gray").pack()
        ttk.Label(f, text="https://github.com/SeanPesce/Suear-Web-Viewer",
                  foreground="gray").pack(pady=(2, 12))
        ttk.Button(f, text="Close", command=self.withdraw).pack()


# --- Enhance settings window ------------------------------------------------

class SettingsWindow(tk.Toplevel):
    SLIDERS = [
        ('denoise',    'Denoise',    0,    100, 1),
        ('sharpen',    'Sharpen',    0,    100, 1),
        ('contrast',   'Contrast',   0.0,  4.0, 0.1),
        ('brightness', 'Brightness', -50,  50,  1),
        ('saturation', 'Saturation', 0,    200, 1),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Enhance Settings")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        self._vars = {}
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill="both", expand=True)
        for col, (key, label, lo, hi, res) in enumerate(self.SLIDERS):
            ttk.Label(frame, text=label, anchor="center").grid(row=0, column=col, padx=8, pady=(0, 4))
            var = tk.DoubleVar(value=DEFAULTS[key])
            self._vars[key] = var
            ttk.Scale(frame, from_=lo, to=hi, orient="vertical",
                      length=110, variable=var,
                      command=lambda _v, k=key: self._update_label(k)
                      ).grid(row=1, column=col, padx=8)
            lbl = ttk.Label(frame, text=self._fmt(key, var.get()), width=7, anchor="center")
            lbl.grid(row=2, column=col, pady=(4, 0))
            var._lbl = lbl
        ttk.Button(frame, text="Reset to defaults", command=self._reset
                   ).grid(row=3, column=0, columnspan=len(self.SLIDERS), pady=(10, 0))

    def _fmt(self, key, val):
        if key == 'contrast':    return f"{val:.1f}"
        if key == 'saturation':  return f"{int(val)}%"
        if key == 'brightness':  return f"{int(val):+d}"
        return str(int(val))

    def _update_label(self, key):
        var = self._vars[key]
        var._lbl.config(text=self._fmt(key, var.get()))

    def _reset(self):
        for key, var in self._vars.items():
            var.set(DEFAULTS[key])
            var._lbl.config(text=self._fmt(key, DEFAULTS[key]))

    def get_params(self) -> dict:
        return {k: v.get() for k, v in self._vars.items()}

    def toggle(self):
        if self.winfo_viewable():
            self.withdraw()
        else:
            self.deiconify()
            self.lift()


# --- Video upscale progress dialog ------------------------------------------

class VideoProcessDialog(tk.Toplevel):
    """Reusable progress window for video export tasks (upscale / stabilize)."""

    def __init__(self, parent, input_path: str, title: str, worker_fn):
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._cancel   = threading.Event()
        self._out_path = None

        f = ttk.Frame(self, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=os.path.basename(input_path),
                  foreground="gray").pack(anchor="w", pady=(0, 10))

        self._progress_var = tk.DoubleVar(value=0)
        ttk.Progressbar(f, variable=self._progress_var,
                        maximum=100, length=400).pack(fill="x")

        self._label_var = tk.StringVar(value="Initialising…")
        ttk.Label(f, textvariable=self._label_var).pack(pady=(6, 12))
        ttk.Button(f, text="Cancel", command=self._on_cancel).pack()

        threading.Thread(
            target=self._run,
            args=(input_path, worker_fn),
            daemon=True,
        ).start()

    def _progress(self, current, total):
        pct = (current / total) * 100
        self._progress_var.set(pct)
        self._label_var.set(f"Frame {current} / {total}  ({pct:.0f}%)")

    def _run(self, input_path, worker_fn):
        try:
            worker_fn(self._progress, self._cancel)
            if not self._cancel.is_set():
                self.after(0, self._on_done)
        except Exception as exc:
            self.after(0, lambda e=exc: self._on_error(str(e)))

    def _on_done(self):
        messagebox.showinfo("Done", f"Saved to:\n{self._out_path}", parent=self)
        self.destroy()

    def _on_error(self, msg):
        messagebox.showerror("Failed", msg, parent=self)
        self.destroy()

    def _on_cancel(self):
        self._cancel.set()
        self.destroy()

    def set_output_path(self, path: str):
        self._out_path = path


# --- Upscale options dialog -------------------------------------------------

class UpscaleOptionsDialog(tk.Toplevel):
    """Modal dialog for model and scale selection before upscale operations."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Upscale Options")
        self.resizable(False, False)
        self.grab_set()
        self._result    = None
        self._model_var = tk.StringVar()
        self._scale_var = tk.StringVar(value="4")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _build(self):
        f = ttk.Frame(self, padding=16)
        f.pack(fill="both", expand=True)
        models  = discover_models()
        default = next((m for m in models if 'x4plus' in m), models[0] if models else '')
        self._model_var.set(default)
        ttk.Label(f, text="Model:").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Combobox(f, textvariable=self._model_var, values=models,
                     state="readonly", width=26).grid(row=0, column=1, padx=(8, 0), pady=(0, 6))
        ttk.Label(f, text="Scale:").grid(row=1, column=0, sticky="w", pady=(0, 14))
        ttk.Combobox(f, textvariable=self._scale_var, values=["2", "4"],
                     state="readonly", width=4).grid(row=1, column=1, padx=(8, 0), pady=(0, 14), sticky="w")
        btn = ttk.Frame(f)
        btn.grid(row=2, column=0, columnspan=2)
        ttk.Button(btn, text="OK",     command=self._on_ok).pack(side="left", padx=(0, 8))
        ttk.Button(btn, text="Cancel", command=self._on_cancel).pack(side="left")

    def _on_ok(self):
        self._result = (self._model_var.get(), int(self._scale_var.get()))
        self.destroy()

    def _on_cancel(self):
        self._result = None
        self.destroy()

    def show(self):
        """Block until dialog closes; return (model, scale) or None on cancel."""
        self.wait_window()
        return self._result


# --- Main application -------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Suear Viewer")
        self._stream         = None
        self._recorder       = None
        self._rec_start      = None
        self._last_rec_path  = None   # path of most recently completed recording
        self._current_photo  = None
        self._last_frame     = None
        self._canvas_w       = 640
        self._canvas_h       = 480
        self._enhance_on     = tk.BooleanVar(value=True)
        self._stabilize_on   = tk.BooleanVar(value=False)
        self._led_on         = tk.BooleanVar(value=True)
        self._enhance_busy   = False
        self._stabilizer     = Stabilizer(smoothing_window=12, zoom=1.06)
        self._settings_win   = None
        self._about_win      = None
        self._build_ui()
        self.after(200, self._on_connect)

    # --- UI -----------------------------------------------------------------

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)   # canvas row

        # === Row 0 — info bar ===
        info = ttk.Frame(self, padding=(4, 4, 4, 0))
        info.grid(row=0, column=0, sticky="ew")
        info.columnconfigure(4, weight=1)

        ttk.Label(info, text="Status:").grid(row=0, column=0, sticky="w")
        self._status_var = tk.StringVar(value="Disconnected")
        ttk.Label(info, textvariable=self._status_var, width=20).grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(info, text="Battery:").grid(row=0, column=2, sticky="w")
        self._battery_var = tk.StringVar(value="--")
        ttk.Label(info, textvariable=self._battery_var, width=6).grid(row=0, column=3, sticky="w", padx=(4, 4))

        self._rec_var = tk.StringVar(value="")
        ttk.Label(info, textvariable=self._rec_var, foreground="red", width=10).grid(row=0, column=4, sticky="w")

        right0 = ttk.Frame(info)
        right0.grid(row=0, column=5, sticky="e")
        ttk.Button(right0, text="About", command=self._on_about).pack(side="right", padx=(4, 0))
        self._connect_btn = ttk.Button(right0, text="Connect", command=self._on_connect)
        self._connect_btn.pack(side="right")

        # === Row 1 — controls bar ===
        ctrl = ttk.Frame(self, padding=(4, 2, 4, 4))
        ctrl.grid(row=1, column=0, sticky="ew")

        # Left group: hardware toggles
        self._led_chk = ttk.Checkbutton(ctrl, text="LED",
                                         variable=self._led_on,
                                         command=self._on_led_toggle,
                                         state="disabled")
        self._led_chk.pack(side="left", padx=(0, 4))

        self._enhance_chk = ttk.Checkbutton(ctrl, text="Enhance",
                                              variable=self._enhance_on)
        self._enhance_chk.pack(side="left", padx=(0, 2))

        self._stabilize_chk = ttk.Checkbutton(ctrl, text="Stabilize",
                                               variable=self._stabilize_on,
                                               command=self._on_stabilize_toggle)
        self._stabilize_chk.pack(side="left", padx=(0, 2))

        ttk.Button(ctrl, text="Settings", command=self._on_toggle_settings).pack(side="left", padx=(0, 12))

        # Centre group: separator (model/scale moved to UpscaleOptionsDialog)
        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=(0, 8))

        # Right group: actions
        ttk.Separator(ctrl, orient="vertical").pack(side="left", fill="y", padx=(0, 8))

        self._save_btn = ttk.Button(ctrl, text="Save Frame",
                                     command=self._on_save_frame, state="disabled")
        self._save_btn.pack(side="left", padx=(0, 4))

        self._record_btn = ttk.Button(ctrl, text="Record",
                                       command=self._on_record, state="disabled")
        self._record_btn.pack(side="left", padx=(0, 4))

        self._upscale_btn = ttk.Button(ctrl, text="Upscale Video",
                                        command=self._on_upscale_video)
        self._upscale_btn.pack(side="left", padx=(0, 4))

        self._stabilize_video_btn = ttk.Button(ctrl, text="Stabilize Video",
                                                command=self._on_stabilize_video)
        self._stabilize_video_btn.pack(side="left")

        # === Row 2 — canvas ===
        self._canvas = tk.Canvas(self, bg="black")
        self._canvas.grid(row=2, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        self.geometry("980x540")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- settings / about ---------------------------------------------------

    def _on_toggle_settings(self):
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self)
        else:
            self._settings_win.toggle()

    def _on_about(self):
        if self._about_win is None:
            self._about_win = AboutWindow(self)
        else:
            self._about_win.deiconify()
            self._about_win.lift()

    # --- canvas helpers -----------------------------------------------------

    def _on_canvas_resize(self, event):
        self._canvas_w = event.width
        self._canvas_h = event.height

    def _draw_frame(self, jpeg_bytes):
        img    = Image.open(io.BytesIO(jpeg_bytes))
        iw, ih = img.size
        cw, ch = self._canvas_w, self._canvas_h
        scale  = min(cw / iw, ch / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        img    = img.resize((nw, nh), Image.BILINEAR)
        x, y   = (cw - nw) // 2, (ch - nh) // 2
        photo  = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        self._canvas.create_image(x, y, anchor="nw", image=photo)
        self._current_photo = photo

    # --- connect / disconnect -----------------------------------------------

    def _on_connect(self):
        if self._stream is not None and self._stream.is_alive():
            if self._recorder is not None:
                self._stop_recording()
            self._stream.stop()
            self._stream = None
            self._connect_btn.config(text="Connect")
            self._record_btn.config(state="disabled")
            self._save_btn.config(state="disabled")
            self._led_chk.config(state="disabled")
            self._status_var.set("Disconnected")
            self._battery_var.set("--")
            self.title("Suear Viewer")
            return

        self._stabilizer.reset()
        self._stream = StreamThread()
        self._stream.start()
        self._connect_btn.config(text="Disconnect")
        self._poll_status()
        self._poll_frame()

    def _on_close(self):
        if self._recorder is not None:
            self._stop_recording()
        if self._stream is not None:
            self._stream.stop()
        self.destroy()

    # --- LED ----------------------------------------------------------------

    def _on_led_toggle(self):
        if self._stream is not None:
            self._stream.set_led(self._led_on.get())

    # --- recording ----------------------------------------------------------

    def _on_record(self):
        if self._recorder is not None and self._recorder.recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".mov",
            filetypes=[("QuickTime Movie", "*.mov")],
            initialfile=Recorder.make_output_path(),
        )
        if not path:
            return
        self._recorder = Recorder(path)
        self._recorder.start()
        self._stream.set_recorder(self._recorder)
        self._rec_start = datetime.datetime.now()
        self._record_btn.config(text="Stop")
        self._poll_rec_timer()

    def _stop_recording(self):
        if self._stream is not None:
            self._stream.set_recorder(None)
        if self._recorder is not None:
            self._last_rec_path = self._recorder.output_path
            self._recorder.stop()
            self._recorder = None
        self._rec_start = None
        self._rec_var.set("")
        self._record_btn.config(text="Record")

    def _poll_rec_timer(self):
        if self._recorder is None or not self._recorder.recording:
            return
        elapsed = datetime.datetime.now() - self._rec_start
        s = int(elapsed.total_seconds())
        self._rec_var.set(f"REC {s // 60:02d}:{s % 60:02d}")
        self.after(500, self._poll_rec_timer)

    # --- stabilizer ---------------------------------------------------------

    def _on_stabilize_toggle(self):
        self._stabilizer.reset()  # clear history on toggle

    def _on_stabilize_video(self):
        path = self._last_rec_path if (
            self._last_rec_path and os.path.isfile(self._last_rec_path)
        ) else None
        path = filedialog.askopenfilename(
            title="Select video to stabilize",
            initialfile=os.path.basename(path) if path else "",
            initialdir=os.path.dirname(path) if path else "",
            filetypes=[("QuickTime Movie", "*.mov"), ("All files", "*.*")],
        )
        if not path:
            return
        base, ext = os.path.splitext(path)
        out_path  = f"{base}_stabilized{ext}"
        dlg = VideoProcessDialog(
            self, path, "Stabilizing Video…",
            lambda cb, ce: stabilize_video(path, out_path,
                                            smoothing_window=30, zoom=1.06,
                                            progress_cb=cb, cancel_event=ce),
        )
        dlg.set_output_path(out_path)

    # --- AI video upscale ---------------------------------------------------

    def _on_upscale_video(self):
        opts = UpscaleOptionsDialog(self).show()
        if opts is None:
            return
        model, scale = opts
        path = self._last_rec_path if (
            self._last_rec_path and os.path.isfile(self._last_rec_path)
        ) else None
        path = filedialog.askopenfilename(
            title="Select video to upscale",
            initialfile=os.path.basename(path) if path else "",
            initialdir=os.path.dirname(path) if path else "",
            filetypes=[("QuickTime Movie", "*.mov"), ("All files", "*.*")],
        )
        if not path:
            return
        params   = self._settings_win.get_params() if self._settings_win else DEFAULTS
        denoise  = int(params['denoise'])
        sharpen  = int(params['sharpen'])
        base, ext = os.path.splitext(path)
        out_path  = f"{base}_upscaled_{scale}x_{model}{ext}"
        dlg = VideoProcessDialog(
            self, path, "Upscaling Video…",
            lambda cb, ce: upscale_video(path, out_path, denoise, sharpen, model, scale,
                                          progress_cb=cb, cancel_event=ce),
        )
        dlg.set_output_path(out_path)

    # --- save frame ---------------------------------------------------------

    def _on_save_frame(self):
        if self._last_frame is None:
            return
        ts   = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        path = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=[("JPEG", "*.jpg"), ("PNG", "*.png")],
            initialfile=f"suear_frame_{ts}.jpg",
        )
        if not path:
            return

        params = self._settings_win.get_params() if self._settings_win else DEFAULTS
        data   = enhance_full(self._last_frame, params)

        # save enhanced original
        Image.open(io.BytesIO(data)).save(path)

        # prompt for upscale options, then save AI upscaled copy
        if is_available():
            opts = UpscaleOptionsDialog(self).show()
            if opts is not None:
                model, scale = opts
                denoise  = int(params['denoise'])
                sharpen  = int(params['sharpen'])
                ai_data  = upscale_frame(data, denoise, sharpen, model, scale)
                base, ext = os.path.splitext(path)
                ai_path   = f"{base}_upscaled_{scale}x_{model}{ext}"
                Image.open(io.BytesIO(ai_data)).save(ai_path)

    # --- polling ------------------------------------------------------------

    def _poll_status(self):
        if self._stream is None:
            return
        self._status_var.set(self._stream.status)
        bat = self._stream.battery
        self._battery_var.set(f"{bat}%" if bat is not None else "--")

        if self._stream.device is not None:
            v, m, fw = self._stream.device
            self.title(f"Suear Viewer — {v} {m} {fw}")
            self._record_btn.config(state="normal")
            self._save_btn.config(state="normal")
            self._led_chk.config(state="normal")

        if self._stream.is_alive():
            self.after(500, self._poll_status)
        else:
            self._status_var.set(self._stream.status)
            self._connect_btn.config(text="Connect")
            self._record_btn.config(state="disabled")
            self._save_btn.config(state="disabled")
            self._led_chk.config(state="disabled")

    def _poll_frame(self):
        if self._stream is None:
            return
        try:
            jpeg             = self._stream.frame_queue.get_nowait()
            self._last_frame = jpeg

            # stabilize before enhance
            if self._stabilize_on.get():
                jpeg = self._stabilizer.process(jpeg)

            if self._enhance_on.get() and not self._enhance_busy:
                self._enhance_busy = True
                params = self._settings_win.get_params() if self._settings_win else DEFAULTS
                def _run(j=jpeg, p=params):
                    out = enhance(j, p)
                    self.after(0, lambda: self._finish_enhance(out))
                threading.Thread(target=_run, daemon=True).start()
            else:
                self._draw_frame(jpeg)
        except queue.Empty:
            pass

        if self._stream.is_alive():
            self.after(FRAME_INTERVAL, self._poll_frame)

    def _finish_enhance(self, jpeg_bytes):
        self._enhance_busy = False
        self._draw_frame(jpeg_bytes)


if __name__ == "__main__":
    app = App()
    app.mainloop()
