import platform
import queue
import re
import socket
import subprocess
import threading

from suear_mirror import SuearClient
from config import CAMERA_IP, QUEUE_MAXSIZE, STREAM_RECV_PORT, BATTERY_POLL_MS

# SetLed command — payload byte: 0x01 = on, 0x00 = off
_LED_ON  = b'\xee\xff\xee\xff\x52\x00\x0a\x00\x03\x00\x00\x00\x11\x01\x64'
_LED_OFF = b'\xee\xff\xee\xff\x52\x00\x0a\x00\x03\x00\x00\x00\x11\x00\x00'


def _get_gateway_candidates():
    """Return all active default gateway IPs from the routing table."""
    candidates = []
    try:
        if platform.system() == 'Windows':
            out = subprocess.check_output(['route', 'print', '0.0.0.0'], text=True, timeout=3)
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0] == '0.0.0.0' and parts[1] == '0.0.0.0':
                    ip = parts[2]
                    if ip != '0.0.0.0' and ip not in candidates:
                        candidates.append(ip)
        else:
            out = subprocess.check_output(['ip', 'route', 'show'], text=True, timeout=3)
            for line in out.splitlines():
                m = re.search(r'(?:default|0\.0\.0\.0/0) via (\S+)', line)
                if m and m.group(1) not in candidates:
                    candidates.append(m.group(1))
    except Exception:
        pass
    return candidates


def _probe_suear(ip, timeout=1.0):
    """Send GetDeviceInfo to ip:10005, return True if response has Suear magic."""
    msg = b'\xee\xff\xee\xff\x00\x00\x01\x00\x01\x00\x00\x00'
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        sock.sendto(msg, (ip, 10005))
        data, _ = sock.recvfrom(256)
        sock.close()
        return data[:4] == b'\xee\xff\xee\xff'
    except Exception:
        return False


def detect_camera_ip():
    """Probe all gateways; return first that responds as Suear device."""
    for ip in _get_gateway_candidates():
        if _probe_suear(ip):
            return ip
    return CAMERA_IP


class StreamThread(threading.Thread):
    """
    Connects to SuearClient, delivers JPEG frames via frame_queue.
    Battery is polled on a background timer, not per-frame.

    Public state (read from GUI thread):
      .status   -- human-readable connection state
      .battery  -- last known battery %, or None
      .device   -- (vendor, model, fw_version) tuple, or None
      .error    -- last exception string, or None
    """

    def __init__(self):
        super().__init__(daemon=True)
        self.frame_queue = queue.Queue(maxsize=QUEUE_MAXSIZE)
        self.status  = "Disconnected"
        self.battery = None
        self.device  = None
        self.error   = None
        self._stop_event  = threading.Event()
        self._client      = None
        self._recorder    = None
        self._cmd_lock    = threading.Lock()  # guards command_sock for concurrent sends

    def set_recorder(self, recorder):
        self._recorder = recorder

    def set_led(self, on: bool):
        """Send LED on/off command. Safe to call from any thread."""
        if self._client is None or not self._client._connected:
            return
        msg = _LED_ON if on else _LED_OFF
        with self._cmd_lock:
            try:
                self._client.send_command(msg)
            except Exception:
                pass

    def _battery_poll_loop(self):
        """Polls battery on BATTERY_POLL_MS interval; stops when stream stops."""
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=BATTERY_POLL_MS / 1000)
            if self._stop_event.is_set():
                break
            if self._client is not None and self._client._connected:
                with self._cmd_lock:
                    try:
                        self.battery = self._client.battery_level
                    except Exception:
                        pass

    def stop(self):
        self._stop_event.set()
        if self._client is not None:
            try:
                self._client.disconnect()
            except Exception:
                pass

    def run(self):
        try:
            self.status = "Connecting..."
            ip = detect_camera_ip()
            self._client = SuearClient(server=ip)
            SuearClient.STREAM_RECV_PORT = STREAM_RECV_PORT  # override default 22785
            self._client.connect()
            self._client.open_video()

            info         = self._client.device_info(update=True)
            self.battery = int(info.battery)
            self.device  = (info.vendor, info.product_id, info.fw_version)
            self.status  = "Connected"

            # start battery poller as separate daemon thread
            threading.Thread(target=self._battery_poll_loop, daemon=True).start()

            while not self._stop_event.is_set():
                frame = self._client.get_frame()
                if frame is None:
                    continue

                jpeg_bytes = bytes(frame.data)

                if self._recorder is not None:
                    self._recorder.write_frame(jpeg_bytes)

                if self.frame_queue.full():
                    try:
                        self.frame_queue.get_nowait()
                    except queue.Empty:
                        pass
                self.frame_queue.put_nowait(jpeg_bytes)

        except Exception as exc:
            self.error  = str(exc)
            self.status = f"Error: {exc}"
        finally:
            if self._client is not None:
                try:
                    self._client.disconnect()
                except Exception:
                    pass
            if self.status == "Connected":
                self.status = "Disconnected"
