import subprocess
import tempfile
import os
import threading

import cv2
import numpy as np


class Stabilizer:
    """
    Real-time video stabilizer using Farneback dense optical flow.

    Computes per-frame translation via median optical flow,
    maintains a smoothed camera trajectory, and corrects each frame
    back toward that trajectory.

    Key design decisions vs. naive cumulative approach:
    - Correction is clamped to max_correction pixels to prevent extreme warps
    - BORDER_REFLECT_101 eliminates the stripe artifacts of BORDER_REPLICATE
    - Median flow (not mean) is robust against outlier motion regions
    - Translation-only correction — rotation adds instability for this use case
    """

    def __init__(self, smoothing_window: int = 12,
                 zoom: float = 1.06,
                 max_correction: float = 30.0):
        """
        smoothing_window  — frames of history to average (higher = smoother, more lag)
        zoom              — slight upscale to hide border artefacts (1.0 = none)
        max_correction    — maximum pixel offset applied per frame (safety clamp)
        """
        self._window     = smoothing_window
        self._zoom       = zoom
        self._max_corr   = max_correction
        self._history    = []                      # recent raw cumulative positions
        self._raw_pos    = np.array([0.0, 0.0])   # accumulated raw position
        self._prev_gray  = None

    def reset(self):
        self._history   = []
        self._raw_pos   = np.array([0.0, 0.0])
        self._prev_gray = None

    def process(self, jpeg_bytes: bytes) -> bytes:
        """
        Stabilize a JPEG frame against the previous one.
        Returns stabilized JPEG bytes.
        On first call returns the original unchanged.
        """
        arr  = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img  = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return jpeg_bytes

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        if self._prev_gray is None:
            self._prev_gray = gray
            return jpeg_bytes

        # --- Farneback dense optical flow ---
        flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray, gray, None,
            pyr_scale=0.5, levels=3, winsize=15,
            iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
        )
        # median is robust against large moving objects / texture edges
        dx = float(np.median(flow[..., 0]))
        dy = float(np.median(flow[..., 1]))

        # --- update trajectory ---
        self._raw_pos += np.array([dx, dy])
        self._history.append(self._raw_pos.copy())
        if len(self._history) > self._window:
            self._history.pop(0)

        smooth_pos = np.mean(self._history, axis=0)
        correction = smooth_pos - self._raw_pos
        correction = np.clip(correction, -self._max_corr, self._max_corr)

        # --- apply translation correction ---
        T = np.float32([[1, 0, correction[0]],
                        [0, 1, correction[1]]])
        stabilized = cv2.warpAffine(
            img, T, (w, h),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )

        # --- zoom crop to hide any residual border ---
        if self._zoom > 1.0:
            zh  = int(h / self._zoom)
            zw  = int(w / self._zoom)
            y0  = (h - zh) // 2
            x0  = (w - zw) // 2
            stabilized = stabilized[y0:y0 + zh, x0:x0 + zw]
            stabilized = cv2.resize(stabilized, (w, h), interpolation=cv2.INTER_LINEAR)

        self._prev_gray = gray

        ok, buf = cv2.imencode('.jpg', stabilized, [cv2.IMWRITE_JPEG_QUALITY, 92])
        return buf.tobytes() if ok else jpeg_bytes


# ---------------------------------------------------------------------------
# Video export stabilization — two-pass Farneback
# ---------------------------------------------------------------------------

def stabilize_video(input_path: str, output_path: str,
                    smoothing_window: int = 30,
                    zoom: float = 1.06,
                    progress_cb=None,
                    cancel_event: threading.Event = None):
    """
    Stabilize a ProRes MOV file using two-pass Farneback:
      Pass 1 — extract all frames, compute full trajectory
      Pass 2 — apply smoothed corrections, re-encode to ProRes 422HQ

    smoothing_window — larger values give smoother result for export
    progress_cb(current, total) — progress callback
    cancel_event     — set() to abort

    The input file is never modified.
    """
    with tempfile.TemporaryDirectory(prefix='suear_stab_') as tmp:
        raw_dir = os.path.join(tmp, 'raw')
        out_dir = os.path.join(tmp, 'out')
        os.makedirs(raw_dir)
        os.makedirs(out_dir)

        # --- extract frames ---
        subprocess.run([
            'ffmpeg', '-y', '-i', input_path,
            '-q:v', '1',
            os.path.join(raw_dir, 'frame_%06d.png'),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        frames = sorted(f for f in os.listdir(raw_dir) if f.endswith('.png'))
        total  = len(frames)
        if total == 0:
            raise RuntimeError("No frames extracted from video.")

        # --- pass 1: build full trajectory ---
        trajectory = []       # list of (raw_dx_cumulative, raw_dy_cumulative)
        raw_pos    = np.array([0.0, 0.0])
        prev_gray  = None

        for fname in frames:
            img  = cv2.imread(os.path.join(raw_dir, fname))
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None,
                    0.5, 3, 15, 3, 5, 1.2, 0,
                )
                raw_pos += np.array([
                    float(np.median(flow[..., 0])),
                    float(np.median(flow[..., 1])),
                ])
            trajectory.append(raw_pos.copy())
            prev_gray = gray

        # --- smooth trajectory with rolling average ---
        traj    = np.array(trajectory)
        half_w  = smoothing_window // 2
        smooth  = np.zeros_like(traj)
        for i in range(len(traj)):
            lo       = max(0, i - half_w)
            hi       = min(len(traj), i + half_w + 1)
            smooth[i] = np.mean(traj[lo:hi], axis=0)

        # --- pass 2: apply corrections ---
        h_ref, w_ref = None, None

        for i, fname in enumerate(frames):
            if cancel_event and cancel_event.is_set():
                return

            img = cv2.imread(os.path.join(raw_dir, fname))
            if h_ref is None:
                h_ref, w_ref = img.shape[:2]

            correction = smooth[i] - traj[i]
            T = np.float32([[1, 0, correction[0]],
                            [0, 1, correction[1]]])
            stabilized = cv2.warpAffine(
                img, T, (w_ref, h_ref),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_REFLECT_101,
            )

            # zoom crop
            if zoom > 1.0:
                zh = int(h_ref / zoom)
                zw = int(w_ref / zoom)
                y0 = (h_ref - zh) // 2
                x0 = (w_ref - zw) // 2
                stabilized = stabilized[y0:y0 + zh, x0:x0 + zw]
                stabilized = cv2.resize(stabilized, (w_ref, h_ref),
                                         interpolation=cv2.INTER_LINEAR)

            cv2.imwrite(os.path.join(out_dir, f'out_{i+1:06d}.png'), stabilized)

            if progress_cb:
                progress_cb(i + 1, total)

        # --- re-encode to ProRes 422HQ MOV ---
        subprocess.run([
            'ffmpeg', '-y',
            '-framerate', '30',
            '-i', os.path.join(out_dir, 'out_%06d.png'),
            '-c:v', 'prores_ks', '-profile:v', '3',
            '-vendor', 'apl0', '-pix_fmt', 'yuv422p10le',
            output_path,
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
