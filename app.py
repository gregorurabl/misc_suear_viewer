import datetime
import io
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog

from PIL import Image, ImageTk

from config import FRAME_INTERVAL, BATTERY_POLL_MS
from enhancer import enhance, enhance_full, DEFAULTS
from recorder import Recorder
from stream_thread import StreamThread


class SettingsWindow(tk.Toplevel):
    """Floating settings window — enhance sliders."""

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
        self.protocol("WM_DELETE_WINDOW", self.withdraw)  # hide instead of destroy
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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Suear Viewer")
        self._stream        = None
        self._recorder      = None
        self._rec_start     = None
        self._current_photo = None
        self._last_frame    = None
        self._canvas_w      = 640
        self._canvas_h      = 480
        self._enhance_on    = tk.BooleanVar(value=False)
        self._led_on        = tk.BooleanVar(value=True)
        self._enhance_busy  = False
        self._settings_win  = None
        self._build_ui()
        self.after(200, self._on_connect)

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- toolbar ---
        bar = ttk.Frame(self, padding=4)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(4, weight=1)

        ttk.Label(bar, text="Status:").grid(row=0, column=0, sticky="w")
        self._status_var = tk.StringVar(value="Disconnected")
        ttk.Label(bar, textvariable=self._status_var, width=20).grid(row=0, column=1, sticky="w", padx=(4, 0))

        ttk.Label(bar, text="Battery:").grid(row=0, column=2, sticky="w")
        self._battery_var = tk.StringVar(value="--")
        ttk.Label(bar, textvariable=self._battery_var, width=6).grid(row=0, column=3, sticky="w", padx=(4, 0))

        self._rec_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self._rec_var, foreground="red", width=10).grid(row=0, column=4, sticky="w")

        btn_frame = ttk.Frame(bar)
        btn_frame.grid(row=0, column=5, sticky="e")

        self._led_chk = ttk.Checkbutton(btn_frame, text="LED",
                                         variable=self._led_on,
                                         command=self._on_led_toggle,
                                         state="disabled")
        self._led_chk.pack(side="right", padx=(4, 0))

        self._enhance_chk = ttk.Checkbutton(btn_frame, text="Enhance",
                                              variable=self._enhance_on)
        self._enhance_chk.pack(side="right", padx=(4, 0))

        self._save_btn = ttk.Button(btn_frame, text="Save Frame",
                                     command=self._on_save_frame, state="disabled")
        self._save_btn.pack(side="right", padx=(4, 0))

        self._record_btn = ttk.Button(btn_frame, text="Record",
                                       command=self._on_record, state="disabled")
        self._record_btn.pack(side="right", padx=(4, 0))

        self._settings_btn = ttk.Button(btn_frame, text="Settings",
                                         command=self._on_toggle_settings)
        self._settings_btn.pack(side="right", padx=(4, 0))

        ttk.Button(btn_frame, text="About",
                   command=self._on_about).pack(side="right", padx=(4, 0))

        self._connect_btn = ttk.Button(btn_frame, text="Connect",
                                        command=self._on_connect)
        self._connect_btn.pack(side="right", padx=(4, 0))           

        # --- canvas fills remaining space ---
        self._canvas = tk.Canvas(self, bg="black")
        self._canvas.grid(row=1, column=0, sticky="nsew")
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        self.geometry("800x480")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # --- settings window ---

    def _on_toggle_settings(self):
        if self._settings_win is None:
            self._settings_win = SettingsWindow(self)
        else:
            self._settings_win.toggle()

    # --- canvas helpers ---

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

    # --- connect / disconnect ---

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

    def _on_about(self):
        win = tk.Toplevel(self)
        win.title("About Suear Viewer")
        win.resizable(False, False)
        f = ttk.Frame(win, padding=20)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text="Suear Viewer", font=("", 14, "bold")).pack()
        ttk.Label(f, text="WiFi Otoscope Camera Viewer").pack(pady=(2, 12))
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=(0, 12))
        ttk.Label(f, text="Developed by").pack()
        ttk.Label(f, text="GREGOR URABL, BA", font=("", 10, "bold")).pack()  # <-- replace
        ttk.Label(f, text="https://gregorurabl.at").pack(pady=(2, 2))  # <-- replace
        ttk.Label(f, text="https://github.com/gregorurabl").pack()  # <-- replace
        ttk.Separator(f, orient="horizontal").pack(fill="x", pady=12)
        ttk.Label(f, text="Based on Suear-Web-Viewer by SeanPesce",
                  foreground="gray").pack()
        ttk.Label(f, text="https://github.com/SeanPesce/Suear-Web-Viewer",
                  foreground="gray").pack(pady=(2, 12))
        ttk.Button(f, text="Close", command=win.destroy).pack()

    # --- LED ---

    def _on_led_toggle(self):
        if self._stream is not None:
            self._stream.set_led(self._led_on.get())

    # --- recording ---

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

    # --- save frame ---

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
        Image.open(io.BytesIO(data)).save(path)

    # --- polling ---

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
