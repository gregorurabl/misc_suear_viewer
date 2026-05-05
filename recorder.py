import datetime
import os
import subprocess
import threading


class Recorder:
    def __init__(self, output_path):
        self.output_path = output_path
        self._proc      = None
        self._lock      = threading.Lock()
        self.recording  = False
        self.error      = None

    def start(self):
        cmd = [
            'ffmpeg', '-y',
            '-f', 'image2pipe',
            '-framerate', '30',
            '-vcodec', 'mjpeg',
            '-i', 'pipe:0',
            '-c:v', 'prores_ks',
            '-profile:v', '3',        # 422 HQ
            '-vendor', 'apl0',
            '-pix_fmt', 'yuv422p10le',
            self.output_path
        ]
        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self.recording = True

    def write_frame(self, jpeg_bytes):
        if not self.recording or self._proc is None:
            return
        with self._lock:
            try:
                self._proc.stdin.write(jpeg_bytes)
            except (BrokenPipeError, OSError) as exc:
                self.error     = str(exc)
                self.recording = False

    def stop(self):
        self.recording = False
        if self._proc is not None:
            try:
                self._proc.stdin.close()
                self._proc.wait(timeout=15)
            except Exception:
                self._proc.kill()
            self._proc = None

    @staticmethod
    def make_output_path(directory=None):
        ts    = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        fname = f'suear_{ts}.mov'
        return os.path.join(directory, fname) if directory else fname
