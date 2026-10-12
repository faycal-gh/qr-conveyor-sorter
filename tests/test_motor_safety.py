import builtins
import json
import sys

import pytest

from test_motor_test import config, gpio, controller
from src import motor_controller
from src.motor_test import main


def test_interruption_stops_steps_before_changing_direction(config, gpio, monkeypatch):
    count = 0
    def sleep(seconds):
        nonlocal count
        count += 1
        gpio[0].append(("sleep", seconds))
        if count == 2:
            raise KeyboardInterrupt
    monkeypatch.setattr(motor_controller.time, "sleep", sleep)
    with pytest.raises(KeyboardInterrupt):
        controller(config, hardware=True).run("1", "forward", 10)
    events = gpio[0]
    step_off = events.index((18, "off"), events.index((18, "on")))
    assert step_off < events.index((23, "off"))
    assert ("sleep", 0.01) in events[step_off + 1:events.index((23, "off"))]


def test_gpio_backend_error_prints_error_and_releases_partial_outputs(config, gpio, tmp_path, monkeypatch, capsys):
    class BackendError(Exception):
        pass
    original = sys.modules["gpiozero"].OutputDevice
    def output(pin, **kwargs):
        if pin == 23:
            raise BackendError("GPIO unavailable")
        return original(pin, **kwargs)
    monkeypatch.setattr(sys.modules["gpiozero"], "OutputDevice", output)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["--config", str(path), "--hardware", "--confirm-wiring", "--motor", "1"]) == 1
    assert "[ERROR] GPIO unavailable" in capsys.readouterr().out
    assert all(device.closed for device in gpio[1])


@pytest.mark.parametrize("bad_config", [[], {"simulation": "false", "motors": {}}])
def test_malformed_config_is_reported_without_gpio(bad_config, gpio, tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad_config), encoding="utf-8")
    assert main(["--config", str(path), "--motor", "1"]) == 1
    assert "[ERROR]" in capsys.readouterr().out
    assert gpio[0] == []


def test_menu_custom_command_and_disabled_motor_recovery(config, gpio, tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    answers = iter(["3", "6", "1", "reverse", "4", "50", "7"])
    monkeypatch.setattr(builtins, "input", lambda prompt: next(answers))
    assert main(["--config", str(path)]) == 0
    output = capsys.readouterr().out
    assert "motor2 is disabled" in output
    assert "4 STEP pulses" in output and "50.00 pulses/s" in output
    assert gpio[0] == []


def test_config_hardware_flag_alone_stays_simulated(config, gpio, tmp_path, capsys):
    config["simulation"] = False
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["--config", str(path), "--motor", "1", "--steps", "1"]) == 0
    assert "SIMULATION" in capsys.readouterr().out
    assert gpio[0] == []
