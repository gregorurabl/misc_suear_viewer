import os
import subprocess
import tempfile
import threading

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Binary location
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BINARY_DIR = os.path.join(_SCRIPT_DIR, 'realesrgan')
_MODELS_DIR = os.path.join(_BINARY_DIR, 'models')
_BINARY     = os.path.join(_BINARY_DIR,
                            'realesrgan-ncnn-vulkan.exe'
                            if os.name == 'nt' else
                            'realesrgan-ncnn-vulkan')

# ---------------------------------------------------------------------------
# Dynamic model discovery
# ---------------------------------------------------------------------------

def discover_models() -> list[str]:
    """
    Scan the models/ subfolder for compatible ncnn model pairs.
    A model is valid when both <name>.param and <name>.bin exist.
    Returns a sorted list of model names (without extension).
    Returns an empty list if the folder does not exist.
    """
    if not os.path.isdir(_MODELS_DIR):
        return []
    params = {
        os.path.splitext(f)[0]
        for f in os.listdir(_MODELS_DIR)
        if f.endswith('.param')
    }
    bins = {
        os.path.splitext(f)[0]
        for f in os.listdir(_MODELS_DIR)
        if f.endswith('.bin')
    }
    return sorted(params & bins)   # only pairs with both files


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_binary():
    if not os.path.isfile(_BINARY):
        raise FileNotFoundError(
            f"realesrgan-ncnn-vulkan binary not found at:\n{_BINARY}\n\n"
            "Download from:\n"
            "https://github.com/xinntao/Real-ESRGAN/releases\n"
            "and place the extracted folder as 'realesrgan/' next to app.py."
        )


def _preprocess(img_bgr, denoise: int, sharpen: int):
    if denoise > 0:
        img_bgr = cv2.bilateralFilter(img_bgr, d=7,
                                      sigmaColor=denoise,
                                      sigmaSpace=denoise)
    if sharpen > 0:
        w    = sharpen / 50.0
        blur = cv2.GaussianBlur(img_bgr, (0, 0), sigmaX=2)
        img_bgr = cv2.addWeighted(img_bgr, 1 + w, blur, -w, 0)
    return img_bgr


def _run_ncnn(input_path: str, output_path: str, model: str, scale: int):
    """Call the ncnn binary. scale is passed explicitly via -s."""
    _check_binary()
    cmd = [
        _BINARY,
        '-i', input_path,
        '-o', output_path,
        '-n', model,
        '-s', str(scale),
        '-f', 'jpg',
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
    return os.path.isfile(_BINARY)


def upscale_frame(jpeg_bytes: bytes, denoise: int, sharpen: int,
                  model: str, scale: int) -> bytes:
    """
    Pre-process and AI-upscale a single JPEG frame.
    denoise/sharpen come from SettingsWindow; model is the ncnn model name.
    """
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes

    img = _preprocess(img, denoise, sharpen)

    with tempfile.TemporaryDirectory(prefix='suear_frame_') as tmp:
        src = os.path.join(tmp, 'input.jpg')
        dst = os.path.join(tmp, 'output.jpg')
        cv2.imwrite(src, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        _run_ncnn(src, dst, model, scale)
        with open(dst, 'rb') as f:
            return f.read()


def upscale_video(input_path: str, output_path: str,
                  denoise: int, sharpen: int,
                  model: str, scale: int,
                  progress_cb=None,
                  cancel_event: threading.Event = None):
    """
    Upscale a ProRes MOV file frame by frame.
    Original file is never modified.
    """
    _check_binary()

    with tempfile.TemporaryDirectory(prefix='suear_video_') as tmp:
        raw_dir = os.path.join(tmp, 'raw')
        up_dir  = os.path.join(tmp, 'up')
        os.makedirs(raw_dir)
        os.makedirs(up_dir)

        result = subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            os.path.join(raw_dir, 'frame_%06d.png'),
        ], capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg frame extraction failed:\n{result.stderr}")

        frames = sorted(f for f in os.listdir(raw_dir) if f.endswith('.png'))
        total  = len(frames)
        if total == 0:
            raise RuntimeError("No frames extracted from video.")

        for i, fname in enumerate(frames):
            if cancel_event and cancel_event.is_set():
                return

            img      = cv2.imread(os.path.join(raw_dir, fname))
            img      = _preprocess(img, denoise, sharpen)
            pre_path = os.path.join(raw_dir, f'pre_{i+1:06d}.jpg')
            out_path = os.path.join(up_dir,  f'up_{i+1:06d}.png')
            cv2.imwrite(pre_path, img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            _run_ncnn(pre_path, out_path, model, scale)

            if progress_cb:
                progress_cb(i + 1, total)

        subprocess.run([
            'ffmpeg', '-y',
            '-framerate', '30',
            '-i', os.path.join(up_dir, 'up_%06d.png'),
            '-c:v', 'prores_ks', '-profile:v', '3',
            '-vendor', 'apl0', '-pix_fmt', 'yuv422p10le',
            output_path,
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
