from __future__ import annotations

from typing import Protocol


class Camera(Protocol):
    def read(self): ...
    def close(self) -> None: ...


class OpenCVCamera:
    def __init__(self, index: int, width: int, height: int):
        import cv2

        self.cv2 = cv2
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open webcam index {index}. Try another camera index in config.json."
            )

    def read(self):
        ok, frame = self.cap.read()
        if not ok:
            raise RuntimeError("Failed to read a frame from the webcam.")
        return frame

    def close(self) -> None:
        self.cap.release()


class Picamera2Camera:
    def __init__(self, width: int, height: int):
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError(
                "Picamera2 is required on Raspberry Pi. Install it with: "
                "sudo apt install python3-picamera2"
            ) from exc

        self.picam2 = Picamera2()
        config = self.picam2.create_video_configuration(
            main={"size": (width, height), "format": "RGB888"}
        )
        self.picam2.configure(config)
        self.picam2.start()

    def read(self):
        # Picamera2's RGB888 format returns BGR-ordered bytes for OpenCV.
        return self.picam2.capture_array()

    def close(self) -> None:
        self.picam2.stop()


def build_camera(config: dict) -> Camera:
    camera_cfg = config["camera"]
    backend = camera_cfg.get("backend", "opencv").lower()
    width = int(camera_cfg.get("width", 1280))
    height = int(camera_cfg.get("height", 720))

    if backend == "opencv":
        return OpenCVCamera(
            index=int(camera_cfg.get("index", 0)),
            width=width,
            height=height,
        )

    if backend == "picamera2":
        return Picamera2Camera(width=width, height=height)

    raise ValueError(f"Unsupported camera backend: {backend}")
