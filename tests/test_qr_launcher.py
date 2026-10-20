import importlib.util
import json
import sys
from pathlib import Path

import pytest
from test_motor_test import gpio as gpio  # noqa: PLC0414 - pytest fixture re-export
from test_qr_motor_test import camera_feed as camera_feed  # noqa: PLC0414 - pytest fixture re-export
from test_qr_motor_test import qr_frame

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def launcher(tmp_path, monkeypatch):
    assert importlib.util.find_spec("src.qr_launcher"), (
        "Saved-settings launcher is missing"
    )
    from src import qr_launcher

    monkeypatch.setattr(qr_launcher, "LOCAL_CONFIG", tmp_path / "config.local.json")
    return qr_launcher


def test_first_configuration_preserves_verified_pins_and_is_simulation(
    launcher, monkeypatch
):
    from src.config_loader import load_config

    monkeypatch.setattr(
        "builtins.input", lambda _prompt: "http://phone.local:8080/video"
    )
    assert launcher.main(["--configure"]) == 0
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    assert saved["camera"]["backend"] == "ipwebcam"
    assert saved["camera"]["url"] == "http://phone.local:8080/video"
    assert saved["motors"] == load_config()["motors"]
    assert saved["simulation"] is True
    assert "hardware_confirmation" not in saved


@pytest.mark.parametrize("url", ["", "file:///video", "http://user:secret@phone/video"])
def test_invalid_url_never_overwrites_saved_configuration(launcher, url):
    assert launcher.main(["--camera-url", "http://phone.local:8080/video"]) == 0
    previous = launcher.LOCAL_CONFIG.read_bytes()
    assert launcher.main(["--camera-url", url]) == 1
    assert launcher.LOCAL_CONFIG.read_bytes() == previous


@pytest.mark.parametrize(
    "answer,enabled", [("yes", False), ("I CONFIRM BOTH MOTORS ARE SAFE", True)]
)
def test_both_motors_require_explicit_persistent_confirmation(
    launcher, monkeypatch, answer, enabled
):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    monkeypatch.setattr("builtins.input", lambda _prompt: answer)
    assert launcher.main(["--enable-hardware"]) == (0 if enabled else 1)
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    assert saved["simulation"] is not enabled
    assert saved["motors"]["enabled"]["motor2"] is enabled
    assert launcher.hardware_confirmed(saved) is enabled


def test_changed_motor_settings_invalidate_confirmation_and_revoke_is_persistent(
    launcher, monkeypatch
):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: "I CONFIRM BOTH MOTORS ARE SAFE"
    )
    assert launcher.main(["--enable-hardware"]) == 0
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    saved["motors"]["pins"]["motor2_dir"] = 26
    assert not launcher.hardware_confirmed(saved)
    assert launcher.main(["--steps", "100", "--speed", "50", "--invert-motor2"]) == 0
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    assert saved["simulation"] is True
    assert saved["motors"]["default_steps"] == 100
    assert saved["motors"]["pulse_high_seconds"] == 0.005
    assert saved["motors"]["pulse_low_seconds"] == pytest.approx(0.015)
    assert saved["motors"]["invert_direction"] == {"motor1": False, "motor2": True}
    assert not launcher.hardware_confirmed(saved)
    assert launcher.main(["--enable-hardware"]) == 0
    assert launcher.main(["--revoke-hardware"]) == 0
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    assert saved["simulation"] is True
    assert saved["motors"]["enabled"]["motor2"] is False
    assert not launcher.hardware_confirmed(saved)


def test_camera_url_change_does_not_revoke_checked_motor_settings(
    launcher, monkeypatch
):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: "I CONFIRM BOTH MOTORS ARE SAFE"
    )
    launcher.main(["--enable-hardware"])
    assert launcher.main(["--camera-url", "http://other-phone.local:8080/video"]) == 0
    assert launcher.hardware_confirmed(json.loads(launcher.LOCAL_CONFIG.read_text()))


def test_hand_edited_hardware_mode_cannot_bypass_acknowledgment(launcher, capsys):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    saved["simulation"] = False
    saved["motors"]["enabled"]["motor2"] = True
    launcher.LOCAL_CONFIG.write_text(json.dumps(saved))
    assert launcher.main([]) == 1
    assert "--enable-hardware" in capsys.readouterr().out


def test_show_configuration_does_not_prompt_or_open_camera(
    launcher, monkeypatch, capsys
):
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Unexpected prompt"))
    assert launcher.main(["--show-config"]) == 0
    printed = capsys.readouterr().out
    assert "motor1_step" in printed and "18" in printed
    assert "ipwebcam" in printed
    assert not launcher.LOCAL_CONFIG.exists()


@pytest.mark.parametrize(
    "args", [["--steps", "0"], ["--speed", "nan"], ["--speed", "1000"]]
)
def test_invalid_motion_settings_do_not_create_local_configuration(launcher, args):
    assert launcher.main(args) == 1
    assert not launcher.LOCAL_CONFIG.exists()


def test_missing_camera_in_noninteractive_first_run_is_clear_error(
    launcher, monkeypatch, capsys
):
    def eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert launcher.main([]) == 1
    assert "--configure" in capsys.readouterr().out


def test_revoke_does_not_require_a_valid_camera_url(launcher):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    saved["camera"]["url"] = ""
    launcher.LOCAL_CONFIG.write_text(json.dumps(saved))
    assert launcher.main(["--revoke-hardware"]) == 0
    assert json.loads(launcher.LOCAL_CONFIG.read_text())["simulation"] is True


def test_revoke_works_when_bench_default_selects_both_motors(launcher, monkeypatch):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: "I CONFIRM BOTH MOTORS ARE SAFE"
    )
    launcher.main(["--enable-hardware"])
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    saved["motors"]["default_motor"] = "both"
    launcher.LOCAL_CONFIG.write_text(json.dumps(saved))
    assert launcher.main(["--revoke-hardware"]) == 0
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    assert saved["simulation"] is True
    assert saved["motors"]["enabled"]["motor2"] is False


def test_launcher_simulation_overrides_saved_hardware_without_opening_gpio(
    launcher, monkeypatch, camera_feed, gpio
):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: "I CONFIRM BOTH MOTORS ARE SAFE"
    )
    launcher.main(["--enable-hardware"])
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    saved["camera"]["backend"] = "opencv"
    launcher.LOCAL_CONFIG.write_text(json.dumps(saved))
    camera_feed.frames = iter([qr_frame("direction:forward")])
    assert launcher.main(["--simulate"]) == 130
    assert camera_feed.released
    assert gpio[0] == []
    assert json.loads(launcher.LOCAL_CONFIG.read_text())["simulation"] is False


def test_everyday_launcher_reuses_confirmation_and_drives_both_motors(
    launcher, monkeypatch, camera_feed, gpio
):
    launcher.main(["--camera-url", "http://phone.local:8080/video"])
    monkeypatch.setattr(
        "builtins.input", lambda _prompt: "I CONFIRM BOTH MOTORS ARE SAFE"
    )
    launcher.main(["--enable-hardware"])
    saved = json.loads(launcher.LOCAL_CONFIG.read_text())
    saved["camera"]["backend"] = "opencv"
    launcher.LOCAL_CONFIG.write_text(json.dumps(saved))
    monkeypatch.setattr(
        "builtins.input", lambda _: pytest.fail("Persistent confirmation was lost")
    )
    for _ in range(2):
        camera_feed.frames = iter([qr_frame("direction:left")])
        assert launcher.main([]) == 130
    assert gpio[0].count((18, "on")) == gpio[0].count((24, "on")) == 400
    assert (23, "value", True) in gpio[0]
    assert (25, "value", False) in gpio[0]
    assert all(device.closed for device in gpio[1])
