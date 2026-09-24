from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import main as sorter_main


class _Camera:
    def __init__(self, count):
        self.frames = iter(range(count))
        self.closed = False

    def read(self):
        try:
            return next(self.frames)
        except StopIteration:
            raise KeyboardInterrupt

    def close(self):
        self.closed = True


class _Detector:
    def __init__(self, responses):
        self.responses = iter(responses)

    def detectAndDecode(self, _frame):
        return next(self.responses)


class _Motors:
    def __init__(self):
        self.directions = []
        self.closed = False

    def execute(self, direction):
        self.directions.append(direction)

    def close(self):
        self.closed = True


def test_visible_qr_stays_locked_through_decode_misses_and_empty_qr_is_logged():
    points = object()
    responses = [
        ("direction:backwards", points, None),
        ("", points, None),  # Detected QR with no decodable payload.
        ("direction:left", points, None),
        *[("", points, None)] * 9,  # Decode misses do not mean the QR disappeared.
        ("direction:left", points, None),  # Same QR must not execute again.
        *[("", None, None)] * 8,  # Actual disappearance rearms the sorter.
        ("direction:right", points, None),  # Next parcel executes immediately.
    ]
    config = {
        "simulation": True,
        "camera": {"show_preview": False},
        "qr": {
            "clear_frames_required": 8,
            "minimum_trigger_interval_seconds": 1.5,
        },
        "conveyor": {"length_m": 1.0, "speed_mps": 1.0},
    }
    camera = _Camera(len(responses))
    motors = _Motors()
    detector = _Detector(responses)
    output = StringIO()

    with (
        patch.object(sorter_main, "load_config", return_value=config),
        patch.object(sorter_main, "build_camera", return_value=camera),
        patch.object(sorter_main, "build_motor_controller", return_value=motors),
        patch.object(sorter_main.cv2, "QRCodeDetector", return_value=detector),
        patch.object(sorter_main.cv2, "cvtColor", side_effect=lambda frame, _code: frame),
        patch.object(sorter_main.cv2, "destroyAllWindows"),
        patch.object(time, "monotonic", side_effect=[10.0, 12.0, 12.1]),
        redirect_stdout(output),
    ):
        sorter_main.main()

    assert motors.directions == ["left", "right"]
    assert "Ignored unsupported payload: 'direction:backwards'" in output.getvalue()
    assert "Ignored empty or undecodable QR payload" in output.getvalue()
    assert camera.closed
    assert motors.closed
