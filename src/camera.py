from __future__ import annotations

from typing import Protocol


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

    raise ValueError(f"Unsupported camera backend: {backend}")
