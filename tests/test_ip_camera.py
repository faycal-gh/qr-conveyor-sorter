import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import camera as camera_module


@pytest.mark.parametrize(
    "url",
    [
        "",
        None,
        "file:///etc/passwd",
        "ftp://phone/video",
        "http://user:secret@phone/video",
        "http://phone:99999/video",
        "http://phone/video?token=secret",
        "http://phone/video\n",
        "http:///video",
        "http://bad host/video",
    ],
)
def test_invalid_stream_url_is_rejected_before_camera_access(url):
    validate = getattr(camera_module, "validate_camera_url", None)
    assert validate is not None, "URL validation is missing"
    with pytest.raises(ValueError):
        validate(url)


@pytest.mark.parametrize(
    "url",
    [
        "http://phone.local:8080/video",
        "https://camera.example/mjpeg",
        "http://[::1]:8080/video",
    ],
)
def test_valid_stream_url_is_preserved(url):
    validate = getattr(camera_module, "validate_camera_url", None)
    assert validate is not None, "URL validation is missing"
    assert validate(url) == url


def test_ip_stream_failure_releases_capture_and_never_returns_buffered_frame(
    monkeypatch,
):
    import cv2
    import numpy as np

    camera_class = getattr(camera_module, "IPCamera", None)
    assert camera_class is not None, "IP camera is missing"
    released = threading.Event()
    requests = []

    class Capture:
        def __init__(self, *args):
            requests.append(args)
            self.reads = 0

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            return (
                (True, np.zeros((16, 16, 3), dtype=np.uint8))
                if self.reads == 1
                else (False, None)
            )

        def release(self):
            released.set()

    monkeypatch.setattr(cv2, "VideoCapture", Capture)
    camera = camera_module.build_camera(
        {"camera": {"backend": "ipwebcam", "url": "http://phone.local:8080/video"}}
    )
    try:
        assert released.wait(2)
        with pytest.raises(RuntimeError, match="restart"):
            camera.read()
        with pytest.raises(RuntimeError, match="restart"):
            camera.check_health()
        assert requests[0][1] == cv2.CAP_FFMPEG
        assert cv2.CAP_PROP_READ_TIMEOUT_MSEC in requests[0][2]
    finally:
        camera.close()


def test_manual_ip_camera_restart_requires_removal_before_any_movement(monkeypatch):
    import cv2

    from src.qr_motor_test import scan

    executed = []
    responses = [
        ("direction:forward", object(), None),
        ("", None, None),
        ("", None, None),
        ("direction:left", object(), None),
        ("direction:right", object(), None),
    ]

    class Feed:
        require_clear = True

        def __init__(self):
            self.frames = iter(responses)

        def read(self):
            return next(self.frames)

    monkeypatch.setattr(
        cv2,
        "QRCodeDetector",
        lambda: SimpleNamespace(detectAndDecode=lambda frame: frame),
    )
    for _ in range(2):
        with pytest.raises(StopIteration):
            scan(
                Feed(),
                SimpleNamespace(
                    run_two=lambda *directions: executed.append(directions)
                ),
                2,
            )
    assert executed == [("forward", "reverse"), ("forward", "reverse")]


def test_capture_drains_during_movement_and_delivers_only_newest_frame(monkeypatch):
    import queue

    import cv2
    import numpy as np

    deliveries = queue.Queue()
    clock = [100.0]
    monkeypatch.setattr(camera_module.time, "monotonic", lambda: clock[0])
    released = threading.Event()

    class Capture:
        def __init__(self, *_args):
            pass

        def isOpened(self):
            return True

        def read(self):
            return deliveries.get(timeout=2)

        def release(self):
            released.set()

    monkeypatch.setattr(cv2, "VideoCapture", Capture)
    monkeypatch.setattr(camera_module.IPCamera, "WARMUP_SECONDS", 0)
    camera = camera_module.IPCamera("http://phone.local:8080/video")
    frames = [np.full((16, 16, 3), index, dtype=np.uint8) for index in range(3)]
    try:
        deliveries.put((True, frames[0]))
        assert camera.read() is frames[0]
        # The scanner can spend time in a motor command while the stream keeps draining.
        clock[0] = 102.0
        deliveries.put((True, frames[1]))
        deliveries.put((True, frames[2]))
        with camera.condition:
            assert camera.condition.wait_for(lambda: camera.sequence == 3, timeout=2)
        with pytest.raises(RuntimeError, match="stale"):
            camera.check_health()
        assert camera.read() is frames[2]
        camera.check_health()
    finally:
        deliveries.put((False, None))
        camera.close()
    assert released.is_set()


def test_stream_failure_during_decoding_cannot_start_a_motor_command(monkeypatch):
    import cv2

    from src.qr_motor_test import scan

    executed = []

    class Feed:
        reads = 0

        def read(self):
            self.reads += 1
            if self.reads > 1:
                raise StopIteration
            return object()

        def check_health(self):
            raise RuntimeError("IP Webcam disconnected; manually restart scanning")

    monkeypatch.setattr(
        cv2,
        "QRCodeDetector",
        lambda: SimpleNamespace(
            detectAndDecode=lambda frame: ("direction:forward", object(), None)
        ),
    )
    with pytest.raises(RuntimeError, match="restart"):
        scan(
            Feed(),
            SimpleNamespace(run_two=lambda *directions: executed.append(directions)),
            2,
        )
    assert executed == []
