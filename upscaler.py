import os
import shutil
import subprocess
import tempfile
import threading

import cv2
import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# realesrgan-ncnn-vulkan binary location
# Expected: a folder named "realesrgan" next to this script containing:
#   Windows: realesrgan-ncnn-vulkan.exe
#   Linux:   realesrgan-ncnn-vulkan
# Download: https://github.com/xinntao/Real-ESRGAN/releases
# ---------------------------------------------------------------------------

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_BINARY_DIR  = os.path.join(_SCRIPT_DIR, 'realesrgan')
_BINARY_WIN  = os.path.join(_BINARY_DIR, 'realesrgan-ncnn-vulkan.exe')
_BINARY_LIN  = os.path.join(_BINARY_DIR, 'realesrgan-ncnn-vulkan')
_BINARY      = _BINARY_WIN if os.name == 'nt' else _BINARY_LIN

# ---------------------------------------------------------------------------
# Presets — each defines a pre-processing pass before the upscale.
# The ncnn binary handles the neural upscale itself.
# ---------------------------------------------------------------------------

PRESETS = {
    'Inspection': {'denoise': 15, 'sharpen': 60},  # max edge clarity for PCB/solder
    'Medical':    {'denoise': 55, 'sharpen':  8},  # smooth, noise-free for tissue/skin
    'Balanced':   {'denoise': 30, 'sharpen': 25},  # general purpose
    'Clean':      {'denoise':  0, 'sharpen':  0},  # upscale only, no pre-processing
}

# ncnn models available inside the binary's models/ subfolder
_MODEL_MAP = {2: 'realesrgan-x2plus', 4: 'realesrgan-x4plus'}

SCALES = [2, 4]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_binary():
    if not os.path.isfile(_BINARY):
        raise FileNotFoundError(
            f"realesrgan-ncnn-vulkan binary not found at:\n{_BINARY}\n\n"
            "Download it from:\n"
            "https://github.com/xinntao/Real-ESRGAN/releases\n"
            "and place the extracted folder as 'realesrgan/' next to app.py."
        )


def _preprocess(img_bgr, denoise: int, sharpen: int):
    """Bilateral denoise + unsharp mask before neural upscaling."""
    if denoise > 0:
        img_bgr = cv2.bilateralFilter(img_bgr, d=7,
                                      sigmaColor=denoise,
                                      sigmaSpace=denoise)
    if sharpen > 0:
        w    = sharpen / 50.0
        blur = cv2.GaussianBlur(img_bgr, (0, 0), sigmaX=2)
        img_bgr = cv2.addWeighted(img_bgr, 1 + w, blur, -w, 0)
    return img_bgr


def _run_ncnn(input_path: str, output_path: str, scale: int):
    """Call the ncnn binary synchronously. Raises on failure."""
    _check_binary()
    model = _MODEL_MAP.get(scale, 'realesrgan-x4plus')
    cmd = [
        _BINARY,
        '-i', input_path,
        '-o', output_path,
        '-n', model,
        '-s', str(scale),
        '-f', 'jpg',        # output format
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"realesrgan-ncnn-vulkan failed (exit {result.returncode}):\n"
            f"{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_available() -> bool:
    """Return True if the ncnn binary is present and executable."""
    return os.path.isfile(_BINARY)


def upscale_frame(jpeg_bytes: bytes, preset: str, scale: int) -> bytes:
    """
    Pre-process and AI-upscale a single JPEG frame.
    Returns upscaled JPEG bytes.
    Raises FileNotFoundError if binary is missing.
    """
    p   = PRESETS.get(preset, PRESETS['Balanced'])
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes

    img = _preprocess(img, p['denoise'], p['sharpen'])

    with tempfile.TemporaryDirectory(prefix='suear_frame_') as tmp:
        src_path = os.path.join(tmp, 'input.jpg')
        dst_path = os.path.join(tmp, 'output.jpg')
        cv2.imwrite(src_path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        _run_ncnn(src_path, dst_path, scale)
        with open(dst_path, 'rb') as f:
            return f.read()


def upscale_video(input_path: str, output_path: str,
                  preset: str, scale: int,
                  progress_cb=None,
                  cancel_event: threading.Event = None):
    """
    Upscale a ProRes MOV frame by frame using the ncnn binary.

    progress_cb(current_frame, total_frames) — called after each frame.
    cancel_event                             — set() to abort.

    Output is re-encoded to ProRes 422HQ MOV via ffmpeg.
    The input file is never modified.
    """
    p = PRESETS.get(preset, PRESETS['Balanced'])
    _check_binary()

    with tempfile.TemporaryDirectory(prefix='suear_video_') as tmp:
        raw_dir = os.path.join(tmp, 'raw')
        up_dir  = os.path.join(tmp, 'up')
        os.makedirs(raw_dir)
        os.makedirs(up_dir)

        # --- extract frames ---
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-q:v', '1',
            os.path.join(raw_dir, 'frame_%06d.png')
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        frames = sorted(f for f in os.listdir(raw_dir) if f.endswith('.png'))
        total  = len(frames)
        if total == 0:
            raise RuntimeError("No frames extracted from video.")

        # --- pre-process + upscale each frame ---
        for i, fname in enumerate(frames):
            if cancel_event and cancel_event.is_set():
                return

            src = os.path.join(raw_dir, fname)
            img = cv2.imread(src)
            img = _preprocess(img, p['denoise'], p['sharpen'])

            pre_path = os.path.join(raw_dir, f'pre_{i+1:06d}.jpg')
            out_path = os.path.join(up_dir,  f'up_{i+1:06d}.png')
            cv2.imwrite(pre_path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            _run_ncnn(pre_path, out_path, scale)

            if progress_cb:
                progress_cb(i + 1, total)

        # --- re-encode to ProRes 422HQ MOV ---
        subprocess.run([
            'ffmpeg', '-y',
            '-framerate', '30',
            '-i', os.path.join(up_dir, 'up_%06d.png'),
            '-c:v', 'prores_ks', '-profile:v', '3',
            '-vendor', 'apl0', '-pix_fmt', 'yuv422p10le',
            output_path
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
