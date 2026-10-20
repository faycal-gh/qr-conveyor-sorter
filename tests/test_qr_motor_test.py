import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_motor_test import config as config  # noqa: PLC0414 - pytest fixture re-export
from test_motor_test import controller
from test_motor_test import gpio as gpio  # noqa: PLC0414 - pytest fixture re-export

from src import camera as camera_module
from src import motor_controller


@pytest.mark.parametrize("directions,levels", [
    (("forward", "forward"), (True, True)),
    (("forward", "reverse"), (True, False)),
    (("reverse", "forward"), (False, True)),
])
def test_two_directions_share_each_pulse_interval(config, gpio, directions, levels):
    config["motors"]["enabled"]["motor2"] = True
    config["motors"]["invert_direction"]["motor2"] = True
    controller(config, hardware=True).run_two(*directions, steps=2, speed=50)
    events, devices = gpio
    assert (23, "value", levels[0]) in events
    assert (25, "value", not levels[1]) in events
    first_on = events.index((18, "on"))
    second_on = events.index((24, "on"))
    first_off = events.index((18, "off"), first_on)
    assert first_on < second_on < events.index(("sleep", 0.005)) < first_off
    assert events.count((18, "on")) == events.count((24, "on")) == 2
    assert events.count(("sleep", 0.015)) == 2
    assert all(device.closed and not device.value for device in devices)


def test_disabled_second_motor_rejects_whole_hardware_movement(config, gpio):
    with pytest.raises(ValueError, match="motor2 is disabled"):
        controller(config, hardware=True).run_two("forward", "reverse")
    assert gpio[0] == []


def test_two_motor_interruption_releases_all_gpio(config, gpio, monkeypatch):
    config["motors"]["enabled"]["motor2"] = True
    def sleep(seconds):
        if seconds == 0.005:
            raise KeyboardInterrupt
    monkeypatch.setattr(motor_controller.time, "sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        controller(config, hardware=True).run_two("forward", "reverse")
    assert all(device.closed and not device.value for device in gpio[1])
    assert ("factory", "close") in gpio[0]


def qr_frame(payload):
    import numpy as np
    import qrcode
    return np.array(qrcode.make(payload).convert("RGB"))[:, :, ::-1].copy()


@pytest.fixture
def camera_feed(monkeypatch):
    class Capture:
        def __init__(self, index):
            self.frames = iter([])
            self.opened = True
            self.released = False
        def set(self, key, number):
            pass
        def isOpened(self):
            return self.opened
        def read(self):
            frame = next(self.frames, KeyboardInterrupt())
            if isinstance(frame, BaseException):
                raise frame
            return frame is not None, frame
        def release(self):
            self.released = True
    import cv2
    capture = Capture(0)
    monkeypatch.setattr(cv2, "VideoCapture", lambda index: capture)
    monkeypatch.setattr(cv2, "imshow", lambda *args: pytest.fail("Headless scanning opened a window"))
    return capture


def run_scanner(config, tmp_path, args=()):
    from src.qr_motor_test import main
    config["camera"] = {"backend": "opencv", "index": 0, "width": 640, "height": 480}
    config["qr"] = {"clear_frames_required": 2}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return main(["--config", str(path), *args])


def test_real_decoding_lockout_and_consecutive_clear_frames(config, gpio, camera_feed, tmp_path, capsys):
    import numpy as np
    clear = np.full((480, 640, 3), 255, dtype=np.uint8)
    forward = qr_frame("direction: forward")
    invalid = qr_frame("unsupported")
    camera_feed.frames = iter([
        invalid, forward, forward, clear, invalid, clear,
        qr_frame("direction: right"), clear, clear,
        qr_frame(" Direction: Left "), clear, clear, qr_frame("direction:right"),
    ])
    config["simulation"] = False  # File alone cannot opt into GPIO.
    assert run_scanner(config, tmp_path, ["--simulate"]) == 130
    output = capsys.readouterr().out
    assert output.count("[EXECUTION] Starting") == 3
    assert "[COMMAND] FORWARD\n[MOTOR 1] FORWARD\n[MOTOR 2] FORWARD" in output
    assert "[COMMAND] LEFT\n[MOTOR 1] FORWARD\n[MOTOR 2] REVERSE" in output
    assert "[COMMAND] RIGHT\n[MOTOR 1] REVERSE\n[MOTOR 2] FORWARD" in output
    assert gpio[0] == []
    assert camera_feed.released


@pytest.mark.parametrize("args", [[], ["--hardware"], ["--hardware", "--confirm-wiring"]])
def test_default_simulation_and_hardware_gates(config, gpio, camera_feed, tmp_path, args):
    config["simulation"] = False
    camera_feed.frames = iter([qr_frame("direction: forward")])
    status = run_scanner(config, tmp_path, args)
    assert status == (130 if not args else 1)
    assert gpio[0] == []


@pytest.mark.parametrize("failure", ["startup", "disconnect"])
def test_camera_fault_returns_error_and_releases_capture(config, gpio, camera_feed, tmp_path, capsys, failure):
    camera_feed.opened = failure != "startup"
    camera_feed.frames = iter([None])
    assert run_scanner(config, tmp_path) == 1
    assert "[ERROR]" in capsys.readouterr().out
    assert camera_feed.released
    assert gpio[0] == []


def test_picamera_start_failure_closes_camera(monkeypatch):
    closed = []
    class PiCamera:
        def __init__(self, camera_num):
            pass
        def create_video_configuration(self, **kwargs):
            return kwargs
        def configure(self, config):
            pass
        def start(self):
            raise RuntimeError("camera busy")
        def close(self):
            closed.append(True)
    monkeypatch.setitem(sys.modules, "picamera2", SimpleNamespace(Picamera2=PiCamera))
    with pytest.raises(RuntimeError, match="camera busy"):
        camera_module.Picamera2Camera(640, 480)
    assert closed == [True]


@pytest.mark.parametrize("direction,levels", [
    ("forward", (True, True)), ("left", (True, False)), ("right", (False, True)),
])
def test_hardware_scanner_does_not_acquire_frames_during_movement(config, gpio, camera_feed, tmp_path, monkeypatch, direction, levels):
    config["motors"]["enabled"]["motor2"] = True
    camera_feed.frames = iter([qr_frame(f"direction: {direction}")])
    reads = []
    original_read = camera_feed.read
    def read():
        reads.append(True)
        return original_read()
    camera_feed.read = read
    def sleep(seconds):
        assert reads == [True]
        if seconds == 0.005:
            raise KeyboardInterrupt
    monkeypatch.setattr(motor_controller.time, "sleep", sleep)
    assert run_scanner(config, tmp_path, ["--hardware", "--confirm-wiring"]) == 130
    assert camera_feed.released
    assert (23, "value", levels[0]) in gpio[0]
    assert (25, "value", levels[1]) in gpio[0]
    assert all(device.closed and not device.value for device in gpio[1])


@pytest.mark.parametrize("decode_error", [False, True])
def test_binary_qr_is_ignored_and_scanning_continues(config, gpio, camera_feed, tmp_path, capsys, monkeypatch, decode_error):
    if decode_error:
        import cv2
        detector = cv2.QRCodeDetector()
        class Decoder:
            first_frame = True
            def detectAndDecode(self, frame):
                if self.first_frame:
                    self.first_frame = False
                    raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid byte")
                return detector.detectAndDecode(frame)
            def detect(self, frame):
                return detector.detect(frame)
        monkeypatch.setattr(cv2, "QRCodeDetector", Decoder)
    camera_feed.frames = iter([qr_frame(b"\xff\xfe"), qr_frame("direction: left")])
    assert run_scanner(config, tmp_path) == 130
    output = capsys.readouterr().out
    assert "[COMMAND] LEFT" in output
    assert gpio[0] == []


def test_second_driver_initialization_failure_sends_no_steps(config, gpio, monkeypatch):
    config["motors"]["enabled"]["motor2"] = True
    original = sys.modules["gpiozero"].OutputDevice
    def output(pin, **kwargs):
        if pin == 25:
            raise RuntimeError("second driver unavailable")
        return original(pin, **kwargs)
    monkeypatch.setattr(sys.modules["gpiozero"], "OutputDevice", output)
    with pytest.raises(RuntimeError, match="second driver unavailable"):
        controller(config, hardware=True).run_two("reverse", "forward")
    assert not any(event[-1] == "on" for event in gpio[0])
    assert all(device.closed and not device.value for device in gpio[1])


@pytest.mark.parametrize("payload,points", [("", object()), ("unsupported", object())])
def test_undecodable_or_invalid_visible_qr_cannot_unlock(config, gpio, camera_feed, tmp_path, monkeypatch, payload, points, capsys):
    import cv2
    responses = iter([
        ("direction: forward", object(), None), ("", None, None),
        (payload, points, None), ("", None, None),
        ("direction: left", object(), None),
    ])
    monkeypatch.setattr(cv2, "QRCodeDetector", lambda: SimpleNamespace(detectAndDecode=lambda frame: next(responses)))
    camera_feed.frames = iter([qr_frame("anything")] * 5)
    assert run_scanner(config, tmp_path) == 130
    assert capsys.readouterr().out.count("[EXECUTION] Starting") == 1


@pytest.mark.parametrize("backend", ["opencv", "picamera2"])
def test_missing_camera_library_has_installation_hint(monkeypatch, backend):
    monkeypatch.setitem(sys.modules, "cv2" if backend == "opencv" else "picamera2", None)
    with pytest.raises(RuntimeError, match="sudo apt install"):
        camera_module.build_camera({"camera": {"backend": backend}})


@pytest.mark.parametrize("failure", [None, RuntimeError("disconnected")])
def test_picamera_frame_timeout_or_success_closes_camera(monkeypatch, failure):
    import numpy as np
    closed = []
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    class PiCamera:
        def __init__(self, camera_num):
            assert camera_num == 1
        def create_video_configuration(self, **kwargs):
            assert kwargs["queue"] is False
            return kwargs
        def configure(self, config):
            pass
        def start(self):
            pass
        def capture_array(self, wait):
            assert wait == 5
            if failure:
                raise failure
            return frame
        def close(self):
            closed.append(True)
    monkeypatch.setitem(sys.modules, "picamera2", SimpleNamespace(Picamera2=PiCamera))
    camera = camera_module.build_camera({"camera": {"backend": "picamera2", "index": 1}})
    try:
        if failure:
            with pytest.raises(RuntimeError, match="restart scanning"):
                camera.read()
        else:
            assert camera.read() is frame
    finally:
        camera.close()
    assert closed == [True]


def test_generated_and_committed_qr_images_decode_exact_payloads(tmp_path):
    import cv2

    from tools.generate_test_qr import generate
    generate(tmp_path)
    expected = {f"qr_{direction}.png": f"direction: {direction}"
                for direction in ("forward", "left", "right")}
    assert {path.name for path in tmp_path.glob("*.png")} == set(expected)
    for folder in (tmp_path, Path(__file__).resolve().parents[1] / "test_qr_codes"):
        for filename, payload in expected.items():
            frame = cv2.imread(str(folder / filename))
            assert frame is not None
            assert cv2.QRCodeDetector().detectAndDecode(frame)[0] == payload


def test_overlapping_motor_command_is_rejected_without_extra_pulses(config, gpio, monkeypatch):
    import threading
    config['motors']['enabled']['motor2'] = True
    motors = controller(config, hardware=True)
    started = threading.Event()
    release = threading.Event()
    errors = []
    def sleep(seconds):
        if threading.current_thread() is worker and seconds == 0.005:
            started.set()
            assert release.wait(3)
    def move():
        try:
            motors.run_two('forward', 'reverse', steps=1)
        except BaseException as exc:  # noqa: BLE001 - report every worker failure in the test thread
            errors.append(exc)
    worker = threading.Thread(target=move)
    monkeypatch.setattr(motor_controller.time, 'sleep', sleep)
    worker.start()
    try:
        assert started.wait(2)
        before = len(gpio[1])
        with pytest.raises(RuntimeError, match='already'):
            motors.run_two('reverse', 'forward', steps=1)
        assert len(gpio[1]) == before
    finally:
        release.set()
        worker.join(timeout=3)
    assert not errors
    motors.run_two('forward', 'forward', steps=1)
    assert all(device.closed for device in gpio[1])
