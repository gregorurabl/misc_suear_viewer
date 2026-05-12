# Suear Viewer

A Python/tkinter desktop application for live viewing, recording, and image enhancement of WiFi-connected otoscope cameras using the Suear protocol.

Developed as a fork of [Suear-Web-Viewer by SeanPesce](https://github.com/SeanPesce/Suear-Web-Viewer), extended with a full GUI, video recording, image enhancement, AI upscaling, and hardware controls.

---

## Compatibility

Tested with the **Qimic Otoscope (BK7231U-XRH-FBPRO)** and any camera using the Suear protocol / `com.i4season.bkCamera` app. Runs on **Windows** and **Linux**.

---

## Requirements

- Python 3.10+
- **ffmpeg** in PATH — required for video recording and upscaling

Python dependencies (`requirements.txt`):

```
Pillow
opencv-python
```

---

## Installation

### Step 1 — Python dependencies

**Windows:**
```
install.bat
```

**Linux:**
```bash
chmod +x install.sh
./install.sh
```

### Step 2 — AI Upscaling (optional)

Download the **realesrgan-ncnn-vulkan** standalone binary from:

> https://github.com/xinntao/Real-ESRGAN/releases

Extract the downloaded archive and place the resulting folder as **`realesrgan/`** directly next to `app.py`:

```
suear_viewer/
├── app.py
├── realesrgan/                        ← extracted here
│   ├── realesrgan-ncnn-vulkan.exe     ← Windows
│   ├── realesrgan-ncnn-vulkan         ← Linux
│   └── models/
└── ...
```

No Python package installation required for AI upscaling. The binary uses Vulkan and works with NVIDIA, AMD, and Intel GPUs.

---

## Usage

1. Power on the camera.
2. Connect your PC to the camera's WiFi network (`Soulear-XXXX`).
3. Run:
   - Windows: `python app.py`
   - Linux: `python3 app.py`
4. The application connects automatically on startup.

---

## Interface

The UI is split into two rows of controls above the live video canvas.

### Row 1 — Connection & Navigation

| Element | Description |
|---|---|
| **Status** | Current connection state |
| **Battery** | Camera battery percentage, updated every 5 seconds |
| **REC timer** | Elapsed recording time (red) |
| **Connect / Disconnect** | Start or stop the camera connection |
| **About** | Developer info |

### Row 2 — Controls

| Element | Description |
|---|---|
| **LED** checkbox | Toggle the camera's LED ring on/off (enabled after connect) |
| **Enhance** checkbox | Toggle real-time image enhancement |
| **Stabilize** checkbox | Toggle live Farneback optical flow stabilization |
| **Settings** button | Open the Enhance Settings window |
| **Save Frame** button | Save current frame as enhanced original; if AI binary is installed, opens upscale options dialog first |
| **Record / Stop** button | Start or stop ProRes 422HQ video recording |
| **Upscale Video** button | Opens upscale options dialog, then file dialog — processes selected .mov frame by frame |
| **Stabilize Video** button | Opens file dialog — applies two-pass Farneback stabilization to selected .mov |
 
---

## Enhance Settings

Open via the **Settings** button. Adjustments apply in real time to the live preview and to saved frames.

| Slider | Effect |
|---|---|
| **Denoise** | Bilateral filter strength — reduces noise while preserving edges |
| **Sharpen** | Unsharp mask — increases perceived edge sharpness |
| **Contrast** | CLAHE local contrast enhancement |
| **Brightness** | Global brightness offset |
| **Saturation** | HSV saturation scaling |

---

## Live Stabilization
 
Toggle via the **Stabilize** checkbox. Uses Farneback dense optical flow with translation-only correction, median-flow outlier rejection, and zoom-crop to hide borders. Stabilizer history resets on toggle and on connect.
 
---

## Stabilize Video
 
Opens a file dialog to select any `.mov`. Applies a two-pass Farneback stabilization (smoothing window: 30 frames, zoom: 1.06×) and saves the result as `_stabilized.mov` alongside the original. Progress is shown in the same dialog used for video upscaling. The original is never overwritten.
 
---

## AI Upscale Presets

Model and scale are selected per operation via a dialog that appears before the file dialog.
The Denoise and Sharpen values from the Enhance Settings window are used as pre-processing before the neural upscale. If Settings has not been opened, the defaults apply.
 
**Save Frame** saves the enhanced original first, then opens the upscale dialog if the AI binary is installed. Cancelling the dialog skips the upscaled copy without affecting the saved original.
 
**Upscale Video** opens the upscale dialog first, then the file picker. Output is saved as `_upscaled_Nx_<model>.mov` alongside the original. The original is never overwritten.

---

## Custom Upscale Models
 
Any ncnn-compatible upscale model can be added to the `realesrgan/models/` folder and will appear automatically in the upscale dialog. A model is recognized when both files are present:
 
- `<modelname>.param`
- `<modelname>.bin`
The model name shown in the dialog is derived from the filename (without extension). Models without a matching pair are ignored.
 
Compatible models can be found at:
- [upscale.wiki/wiki/Model_Database](https://upscale.wiki/wiki/Model_Database) — community model database
- [github.com/xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) — official Real-ESRGAN models
When converting models from other formats (PyTorch `.pth`, ONNX), use [realsr-ncnn-vulkan](https://github.com/nihui/realsr-ncnn-vulkan) or the `ncnn` toolchain to export `.param` / `.bin` pairs. The binary's `-s` flag passes the scale factor at runtime — the model itself must support the selected scale (2× or 4×).
 
---

## File Structure

| File | Description |
|---|---|
| `app.py` | Main application and GUI |
| `stream_thread.py` | Background thread for camera connection and frame delivery |
| `enhancer.py` | OpenCV image enhancement pipeline |
| `recorder.py` | ffmpeg-based ProRes video recorder |
| `upscaler.py` | AI upscaling via realesrgan-ncnn-vulkan |
| `config.py` | Camera IP, stream port, GUI constants |
| `suear_mirror.py` | Upstream: Suear protocol implementation |
| `suear_struct.py` | Upstream: Suear command/response structures |
| `suear_util.py` | Upstream: Utility functions |
| `ctypes_util.py` | Upstream: ctypes helpers |
| `realesrgan/` | ncnn-vulkan binary (download separately) |

---

## Credits

Protocol reverse engineering and original Python implementation:
**SeanPesce** — [Suear-Web-Viewer](https://github.com/SeanPesce/Suear-Web-Viewer)

GUI, recording, enhancement, and AI upscaling extensions:
**YOUR NAME HERE** — [Homepage](https://your-homepage.example.com) · [GitHub](https://github.com/your-username)

---

## License

See upstream repository for license terms: [github.com/SeanPesce/Suear-Web-Viewer](https://github.com/SeanPesce/Suear-Web-Viewer)
