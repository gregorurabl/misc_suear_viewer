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
| **Enhance** checkbox | Toggle real-time image enhancement (bilateral filter) |
| **Settings** button | Open the Enhance Settings window |
| **AI Upscale** checkbox | Enable AI upscaling on frame export and video post-processing |
| **Preset** dropdown | Upscale preset (see below) |
| **Scale** dropdown | Upscale factor: 2× or 4× |
| **Save Frame** button | Save current frame as JPEG or PNG |
| **Record / Stop** button | Start or stop ProRes 422HQ video recording |
| **Upscale Video** button | Post-process the last recording with AI upscaling (unlocks after Stop) |

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

## AI Upscale Presets

| Preset | Best for | Processing |
|---|---|---|
| **Inspection** | Electronics, PCB, solder joints | Strong sharpening before upscale |
| **Medical** | Tissue, skin, ear canal | Strong denoising before upscale |
| **Balanced** | General use | Moderate denoise + sharpen |
| **Clean** | Maximum fidelity | No pre-processing, upscale only |

When AI Upscale is active:

- **Save Frame** saves two files: the enhanced original and an `_upscaled_Nx_Preset` copy.
- **Upscale Video** processes the last recording and saves a new `_upscaled_Nx_Preset.mov` alongside the original. The original is never overwritten.

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