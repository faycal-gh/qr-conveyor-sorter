from __future__ import annotations

import ipaddress
import re
import threading
import time
from typing import Protocol
from urllib.parse import urlsplit


def validate_camera_url(url):
    if not isinstance(url, str) or not url or any(char.isspace() or ord(char) < 32 for char in url):
        raise ValueError('Enter a complete HTTP(S) IP Webcam video URL without whitespace')
    try:
        parsed = urlsplit(url)
        port = parsed.port
        hostname = parsed.hostname
        if (parsed.scheme not in ('http', 'https') or not hostname or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment or port == 0):
            raise ValueError
        try:
            ipaddress.ip_address(hostname)
        except ValueError:
            labels = hostname.encode('idna').decode('ascii').rstrip('.').split('.')
            if (len(hostname) > 253 or all(char in '0123456789.' for char in hostname)
                    or any(not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label) for label in labels)):
                raise ValueError
    except (ValueError, UnicodeError):
        raise ValueError('Use an HTTP(S) video URL with a valid host/port and no credentials, query or fragment') from None
    return url


class Camera(Protocol):
    def read(self): ...
    def close(self) -> None: ...


class OpenCVCamera:
    def __init__(self, index: int, width: int, height: int):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required: sudo apt install python3-opencv; "
                "use a venv with --system-site-packages (Windows: pip install opencv-python)."
            ) from exc

        self.cv2 = cv2
        self.cap = cv2.VideoCapture(index)
        try:
            if not self.cap.isOpened():
                raise RuntimeError(
                    f"Could not open webcam index {index}. Check /dev/video*, permissions, "
                    "and camera.index in config.json; stop other camera applications."
                )
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        except BaseException:
            self.close()
            raise

    def read(self):
        ok, frame = self.cap.read()
        if not ok or frame is None or frame.size == 0:
            raise RuntimeError("Webcam disconnected or failed to read a frame; check USB and restart scanning.")
        return frame

    def close(self) -> None:
        self.cap.release()


class IPCamera:
    """Continuously drain the stream; hand consumers only the latest fresh frame."""

    require_clear = True
    WARMUP_SECONDS = 1.0

    def __init__(self, url):
        validate_camera_url(url)
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError('IP Webcam needs OpenCV: sudo apt install python3-opencv') from exc
        self.condition = threading.Condition()
        self.cv2 = cv2
        self.stopping = threading.Event()
        self.latest = None
        self.sequence = 0
        self.consumed = 0
        self.consumed_at = None
        self.error = None
        try:
            self.cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG, [
                cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000,
                cv2.CAP_PROP_READ_TIMEOUT_MSEC, 2000,
            ])
        except cv2.error:
            raise RuntimeError('IP Webcam could not open; check URL, phone and OpenCV FFmpeg support') from None
        if not self.cap.isOpened():
            self.cap.release()
            raise RuntimeError('IP Webcam could not open; check saved URL, phone server and Wi-Fi, then restart')
        self.worker = threading.Thread(target=self._capture, name='ip-webcam', daemon=True)
        try:
            self.worker.start()
        except BaseException:
            self.cap.release()
            raise

    def _capture(self):
        ready_at = time.monotonic() + self.WARMUP_SECONDS
        try:
            while not self.stopping.is_set():
                ok, frame = self.cap.read()
                if not ok or frame is None or frame.size == 0:
                    raise RuntimeError('Stream ended')
                captured_at = time.monotonic()
                if captured_at < ready_at:
                    continue
                with self.condition:
                    self.sequence += 1
                    self.latest = (captured_at, frame)
                    self.condition.notify_all()
        except (self.cv2.error, OSError, RuntimeError):
            # Signal third-party decoder failures to the main thread without logging URLs.
            with self.condition:
                self.error = 'IP Webcam disconnected; check phone/Wi-Fi and manually restart scanning'
                self.latest = None
                self.condition.notify_all()
        finally:
            self.cap.release()

    def read(self):
        with self.condition:
            available = self.condition.wait_for(
                lambda: self.error or self.stopping.is_set() or self.sequence > self.consumed,
                timeout=3,
            )
            if self.error:
                raise RuntimeError(self.error)
            if not available or self.stopping.is_set() or time.monotonic() - self.latest[0] > 1:
                raise RuntimeError('IP Webcam has no fresh frame; check phone/Wi-Fi and manually restart scanning')
            self.consumed = self.sequence
            self.consumed_at = self.latest[0]
            return self.latest[1]

    def check_health(self):
        with self.condition:
            if self.error:
                raise RuntimeError(self.error)
            if (self.stopping.is_set() or self.consumed_at is None
                    or time.monotonic() - self.consumed_at > 1):
                raise RuntimeError('IP Webcam command frame is stale; manually restart scanning')

    def close(self):
        self.stopping.set()
        with self.condition:
            self.condition.notify_all()
        # Only the capture thread releases VideoCapture; concurrent read/release is unsafe.
        self.worker.join(timeout=3)
        if self.worker.is_alive():
            raise RuntimeError('IP Webcam decoder did not stop within its timeout; exit and restart the application')


class Picamera2Camera:
    def __init__(self, width: int, height: int, index: int = 0):
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "Picamera2 is required on Raspberry Pi. Install it with: "
                "sudo apt install python3-picamera2"
            ) from exc

        try:
            self.picam2 = Picamera2(camera_num=index)
        except Exception as exc:
            raise RuntimeError(
                f"Could not open CSI camera {index}: {exc}. Run rpicam-hello --list-cameras; "
                "check the ribbon cable with Pi power off and stop other camera applications."
            ) from exc
        try:
            config = self.picam2.create_video_configuration(
                main={"size": (width, height), "format": "RGB888"}, queue=False
            )
            self.picam2.configure(config)
            self.picam2.start()
        except BaseException:
            self.close()
            raise

    def read(self):
        # Picamera2's RGB888 format returns BGR-ordered bytes for OpenCV.
        try:
            frame = self.picam2.capture_array(wait=5)
        except Exception as exc:
            raise RuntimeError(f"CSI camera frame capture failed: {exc}; check camera and restart scanning.") from exc
        if frame is None or frame.size == 0:
            raise RuntimeError("CSI camera returned an empty frame; check camera and restart scanning.")
        return frame

    def close(self) -> None:
        self.picam2.close()


def build_camera(config: dict) -> Camera:
    camera_cfg = config["camera"]
    backend = camera_cfg.get("backend", "opencv").lower()
    width = camera_cfg.get("width", 1280)
    height = camera_cfg.get("height", 720)
    index = camera_cfg.get("index", 0)
    if any(type(size) is not int or size <= 0 for size in (width, height)):
        raise ValueError("Camera width and height must be positive integers")
    if type(index) is not int or index < 0:
        raise ValueError("Camera index must be a nonnegative integer")

    if backend == "opencv":
        return OpenCVCamera(
            index=index,
            width=width,
            height=height,
        )

    if backend == "picamera2":
        return Picamera2Camera(width=width, height=height, index=index)

    if backend == 'ipwebcam':
        return IPCamera(camera_cfg.get('url'))

    raise ValueError(f"Unsupported camera backend: {backend}")
