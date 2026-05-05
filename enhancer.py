import cv2
import numpy as np


# Default parameter values — mirrored in app.py sliders
DEFAULTS = {
    'denoise':    30,   # bilateralFilter sigma (0-100)
    'sharpen':    30,   # unsharp mask amount  (0-100)
    'contrast':   1.5,  # CLAHE clip limit     (0.0-4.0)
    'brightness': 0,    # addWeighted beta     (-50..+50)
    'saturation': 120,  # HSV S scale %        (0-200)
}


def _apply_clahe(img, clip):
    """CLAHE on L channel of LAB."""
    if clip <= 0:
        return img
    lab  = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clip, tileGridSize=(8, 8))
    l     = clahe.apply(l)
    return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)


def _apply_saturation(img, pct):
    """Scale HSV saturation by pct/100."""
    if pct == 100:
        return img
    hsv    = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * (pct / 100.0), 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def _apply_sharpen(img, amount):
    """Unsharp mask — amount 0-100 maps to 0.0-2.0 weight."""
    if amount <= 0:
        return img
    w      = amount / 50.0          # 0..2
    blur   = cv2.GaussianBlur(img, (0, 0), sigmaX=2)
    return cv2.addWeighted(img, 1 + w, blur, -w, 0)


def enhance(jpeg_bytes: bytes, params: dict) -> bytes:
    """
    Apply enhancement pipeline to a JPEG frame.
    params keys: denoise, sharpen, contrast, brightness, saturation
    Falls back to DEFAULTS for any missing key.
    Returns enhanced JPEG bytes.
    """
    p   = {**DEFAULTS, **params}
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes

    # 1. denoise via bilateral filter
    sigma = int(p['denoise'])
    if sigma > 0:
        img = cv2.bilateralFilter(img, d=7, sigmaColor=sigma, sigmaSpace=sigma)

    # 2. CLAHE contrast
    img = _apply_clahe(img, float(p['contrast']))

    # 3. brightness
    beta = int(p['brightness'])
    if beta != 0:
        img = cv2.convertScaleAbs(img, alpha=1.0, beta=beta)

    # 4. saturation
    img = _apply_saturation(img, int(p['saturation']))

    # 5. sharpen last so it works on clean signal
    img = _apply_sharpen(img, int(p['sharpen']))

    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return buf.tobytes() if ok else jpeg_bytes


def enhance_full(jpeg_bytes: bytes, params: dict) -> bytes:
    """
    Full quality enhance for saved frames — adds NlMeans denoising on top.
    """
    p   = {**DEFAULTS, **params}
    arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return jpeg_bytes

    # stronger denoising for stills
    sigma = int(p['denoise'])
    if sigma > 0:
        img = cv2.bilateralFilter(img, d=7, sigmaColor=sigma, sigmaSpace=sigma)
        h   = max(3, sigma // 5)
        img = cv2.fastNlMeansDenoisingColored(img, None, h=h, hColor=h,
                                               templateWindowSize=7,
                                               searchWindowSize=21)

    img = _apply_clahe(img, float(p['contrast']))

    beta = int(p['brightness'])
    if beta != 0:
        img = cv2.convertScaleAbs(img, alpha=1.0, beta=beta)

    img = _apply_saturation(img, int(p['saturation']))
    img = _apply_sharpen(img, int(p['sharpen']))

    ok, buf = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return buf.tobytes() if ok else jpeg_bytes
