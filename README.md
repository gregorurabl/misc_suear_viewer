# Suear Viewer

A Python/tkinter desktop application for live viewing, recording, and image enhancement of WiFi-connected otoscope cameras using the Suear protocol.

Developed as a fork of [Suear-Web-Viewer by SeanPesce](https://github.com/SeanPesce/Suear-Web-Viewer), extended with a full GUI, video recording, image enhancement, and hardware controls.

<img width="1172" height="526" alt="grafik" src="https://github.com/user-attachments/assets/b8a357df-8faa-498c-a7f9-90e93557e358" />

---

## Compatibility

Tested with the **Qimic Otoscope (BK7231U-XRH-FBPRO)** and any camera using the Suear protocol / `com.i4season.bkCamera` app. Runs on **Windows** and **Linux**.

---

## Requirements

- Python 3.10+
- ffmpeg (must be in PATH) — required for video recording

Python dependencies are listed in `requirements.txt`:

```
Pillow
opencv-python
```

---

## Installation

**Windows:**
```
install.bat
```

**Linux:**
```bash
chmod +x install.sh
./install.sh
```

---

## Usage

1. Power on the camera.
2. Connect your PC to the camera's WiFi network (`Soulear-XXXX`).
3. Run the application:
   - Windows: `python app.py`
   - Linux: `python3 app.py`
4. The application auto-connects on startup. Use the **Connect / Disconnect** button to control the connection manually.

---

## Features

### New in this fork

| Feature | Description |
|---|---|
| **tkinter GUI** | Native desktop window, no browser required |
| **Auto-Connect** | Connects automatically on startup |
| **Auto IP Detection** | Detects the camera's IP by probing all active gateways — no manual config needed |
| **Aspect-ratio-correct preview** | Video fills the window with letterboxing, no distortion |
| **LED Toggle** | Enable/disable the camera's built-in LED ring |
| **Enhance Toggle** | Real-time image enhancement via OpenCV (bilateral filter) |
| **Enhance Settings** | Separate floating window with sliders for Denoise, Sharpen, Contrast, Brightness, and Saturation |
| **Save Frame** | Capture a single JPEG or PNG frame (with full enhance pipeline applied) |
| **Video Recording** | Record to **ProRes 422HQ .mov** via ffmpeg |
| **Recording Timer** | Live REC timer displayed in the toolbar |
| **Battery Display** | Shows current battery percentage, polled every 5 seconds |
| **Device Name** | Camera model and firmware shown in the window title bar |

---

## Controls

| Button | Function |
|---|---|
| **Connect / Disconnect** | Start or stop the camera connection |
| **Record / Stop** | Start recording to a ProRes 422HQ .mov file (opens save dialog) |
| **Save Frame** | Save the current frame as JPEG or PNG |
| **Enhance** checkbox | Toggle real-time image enhancement on/off |
| **Settings** | Open the Enhance Settings window (sliders for image quality) |
| **LED** checkbox | Toggle the camera's LED ring on or off |
| **About** | Show application info and developer links |

---

## File Structure

| File | Description |
|---|---|
| `app.py` | Main application and GUI |
| `stream_thread.py` | Background thread for camera connection and frame delivery |
| `enhancer.py` | OpenCV image enhancement pipeline |
| `recorder.py` | ffmpeg-based video recorder |
| `config.py` | Camera IP, stream port, and GUI constants |
| `suear_mirror.py` | Upstream: Suear protocol implementation |
| `suear_struct.py` | Upstream: Suear command/response structures |
| `suear_util.py` | Upstream: Utility functions |
| `ctypes_util.py` | Upstream: ctypes helpers |

---

## Credits

Protocol reverse engineering and original Python implementation:
**SeanPesce** — [Suear-Web-Viewer](https://github.com/SeanPesce/Suear-Web-Viewer)

GUI, recording, enhancement, and hardware control extensions:
**Gregor Urabl** — [Homepage](https://gregorurabl.at) · [GitHub](https://github.com/gregorurabl)

---

## License

See upstream repository for license terms: [github.com/SeanPesce/Suear-Web-Viewer](https://github.com/SeanPesce/Suear-Web-Viewer)
