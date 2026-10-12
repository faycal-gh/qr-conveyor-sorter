import builtins
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import motor_controller


@pytest.fixture
def config():
    return {
        "simulation": True,
        "motors": {
            "enabled": {"motor1": True, "motor2": False},
            "pins": {"motor1_step": 18, "motor1_dir": 23,
                     "motor2_step": 24, "motor2_dir": 25},
            "invert_direction": {"motor1": False, "motor2": False},
            "pulse_active_high": True,
            "default_motor": "1", "default_steps": 200, "max_steps": 10000,
            "pulse_high_seconds": 0.005, "pulse_low_seconds": 0.005,
            "direction_setup_seconds": 0.01, "gpiochip": 0,
        },
    }


@pytest.fixture
def gpio(monkeypatch):
    events = []
    devices = []

    class Output:
        def __init__(self, pin, *, initial_value, active_high=True, pin_factory):
            self.pin = pin
            self._value = initial_value
            self.closed = False
            self.active_high = active_high
            devices.append(self)
            events.append((pin, "open", initial_value, active_high))

        @property
        def value(self):
            return self._value

        @value.setter
        def value(self, level):
            self._value = level
            events.append((self.pin, "value", level))

        def on(self):
            self.value = True
            events.append((self.pin, "on"))

        def off(self):
            self.value = False
            events.append((self.pin, "off"))

        def close(self):
            self.closed = True
            events.append((self.pin, "close"))

    class Factory:
        def __init__(self, chip):
            events.append(("factory", chip))

        def close(self):
            events.append(("factory", "close"))

    monkeypatch.setitem(sys.modules, "gpiozero", SimpleNamespace(OutputDevice=Output))
    monkeypatch.setitem(sys.modules, "gpiozero.pins.lgpio", SimpleNamespace(LGPIOFactory=Factory))
    monkeypatch.setattr(motor_controller.time, "sleep", lambda seconds: events.append(("sleep", seconds)))
    return events, devices


def controller(config, hardware=False):
    config = copy.deepcopy(config)
    config["simulation"] = not hardware
    return motor_controller.build_motor_controller(config, wiring_confirmed=hardware)


@pytest.mark.parametrize("motor,direction,invert,level", [
    ("1", "forward", False, True), ("1", "reverse", False, False),
    ("1", "forward", True, False), ("2", "reverse", False, False),
    ("2", "reverse", True, True),
    ("both", "forward", False, True),
])
def test_selected_motor_receives_direction_then_exact_pulses(config, gpio, motor, direction, invert, level):
    config["motors"]["enabled"]["motor2"] = True
    config["motors"]["invert_direction"] = {"motor1": invert, "motor2": invert}
    events, devices = gpio
    motors = controller(config, hardware=True)
    assert devices == []  # Startup never opens GPIO.
    motors.run(motor, direction, 3)
    selected = [1, 2] if motor == "both" else [int(motor)]
    assert {device.pin for device in devices} == {
        pin for number in selected for pin in ((18, 23) if number == 1 else (24, 25))
    }
    for number in selected:
        step, direction_pin = (18, 23) if number == 1 else (24, 25)
        assert events.count((step, "on")) == 3
        assert events.index((direction_pin, "value", level)) < events.index(("sleep", 0.01)) < events.index((step, "on"))
    assert all(device.closed and not device.value for device in devices)
    assert ("factory", "close") in events


@pytest.mark.parametrize("failure", [KeyboardInterrupt, RuntimeError])
def test_pulse_failure_releases_every_output_and_factory(config, gpio, monkeypatch, failure):
    events, devices = gpio
    def sleep(seconds):
        if seconds == 0.005:
            raise failure("interrupted pulse")
    monkeypatch.setattr(motor_controller.time, "sleep", sleep)
    with pytest.raises(failure):
        controller(config, hardware=True).run("1", "forward", 10)
    assert events.count((18, "on")) == 1
    assert all(device.closed and not device.value for device in devices)
    assert ("factory", "close") in events


def test_partial_gpio_initialization_is_cleaned_up(config, gpio, monkeypatch):
    events, devices = gpio
    original = sys.modules["gpiozero"].OutputDevice
    def output(pin, **kwargs):
        if pin == 23:
            raise RuntimeError("pin unavailable")
        return original(pin, **kwargs)
    monkeypatch.setattr(sys.modules["gpiozero"], "OutputDevice", output)
    with pytest.raises(RuntimeError, match="pin unavailable"):
        controller(config, hardware=True).run("1", "forward", 2)
    assert devices[0].closed and not devices[0].value
    assert ("factory", "close") in events


@pytest.mark.parametrize("motor,direction,steps,speed", [
    ("2", "forward", 2, None), ("both", "forward", 2, None),
    ("3", "forward", 2, None), ("1", "left", 2, None),
    ("1", "forward", 0, None), ("1", "forward", -2, None),
    ("1", "forward", 10001, None), ("1", "forward", True, None),
    ("1", "forward", 1.5, None), ("1", "forward", 2, 0),
    ("1", "forward", 2, float("nan")), ("1", "forward", 2, 1000),
])
def test_invalid_or_disabled_command_never_opens_gpio(config, gpio, motor, direction, steps, speed):
    with pytest.raises(ValueError):
        controller(config, hardware=True).run(motor, direction, steps, speed)
    assert gpio[0] == []


@pytest.mark.parametrize("key,bad", [
    ("enabled", {"motor1": "false", "motor2": False}),
    ("pins", {"motor1_step": 18, "motor1_dir": 18, "motor2_step": 24, "motor2_dir": 25}),
    ("pins", {"motor1_step": 40, "motor1_dir": 23, "motor2_step": 24, "motor2_dir": 25}),
    ("pulse_high_seconds", 0), ("pulse_low_seconds", float("inf")),
    ("direction_setup_seconds", -1), ("max_steps", 0), ("default_steps", 10001),
    ("default_motor", "2"), ("pulse_active_high", "true"), ("gpiochip", -1),
])
def test_invalid_config_is_rejected_before_gpio(config, gpio, key, bad):
    config["motors"][key] = bad
    with pytest.raises(ValueError):
        controller(config, hardware=True)
    assert gpio[0] == []


def test_hardware_requires_explicit_wiring_confirmation(config, gpio):
    config["simulation"] = False
    with pytest.raises(ValueError, match="wiring"):
        motor_controller.build_motor_controller(config)
    assert gpio[0] == []


def test_simulation_describes_pins_direction_pulses_and_speed_without_gpio(config, gpio, capsys):
    controller(config).run("1", "reverse", 4, 50)
    output = capsys.readouterr().out
    assert "GPIO18" in output and "GPIO23" in output
    assert "reverse" in output and "4 STEP pulses" in output
    assert "50.00 pulses/s" in output and "SIMULATION" in output
    assert gpio[0] == []


def test_active_low_step_returns_to_inactive(config, gpio):
    config["motors"]["pulse_active_high"] = False
    controller(config, hardware=True).run("1", "forward", 1)
    assert (18, "open", False, False) in gpio[0]
    assert all(device.closed and not device.value for device in gpio[1])


def test_speed_changes_low_time_and_keeps_high_width(config, gpio):
    controller(config, hardware=True).run("1", "forward", 2, 50)
    assert gpio[0].count(("sleep", 0.005)) == 2
    assert gpio[0].count(("sleep", 0.015)) == 2


def test_motor_one_can_be_disabled_while_motor_two_runs(config, gpio):
    config["motors"]["enabled"] = {"motor1": False, "motor2": True}
    config["motors"]["default_motor"] = "2"
    motors = controller(config, hardware=True)
    with pytest.raises(ValueError, match="motor1 is disabled"):
        motors.run("1", "forward", 1)
    assert gpio[0] == []
    motors.run("2", "forward", 1)
    assert {device.pin for device in gpio[1]} == {24, 25}


@pytest.mark.parametrize("steps", [None, 1, 5])
def test_default_and_limit_step_counts_are_executed(config, gpio, steps):
    config["motors"]["default_steps"] = 3
    config["motors"]["max_steps"] = 5
    controller(config, hardware=True).run("1", "forward", steps)
    assert gpio[0].count((18, "on")) == (3 if steps is None else steps)


def test_cli_hardware_gate_and_interrupt_status(config, gpio, tmp_path, monkeypatch, capsys):
    from src.motor_test import main
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    args = ["--config", str(path), "--hardware", "--motor", "1"]
    assert main(args) == 1
    assert gpio[0] == []
    monkeypatch.setattr(motor_controller.time, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt()))
    assert main(args + ["--confirm-wiring"]) == 130
    assert "Interrupted" in capsys.readouterr().out
    assert all(device.closed and not device.value for device in gpio[1])


def test_menu_exit_does_not_open_gpio(config, gpio, tmp_path, monkeypatch):
    from src.motor_test import main
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(builtins, "input", lambda prompt: "7")
    assert main(["--config", str(path), "--hardware", "--confirm-wiring"]) == 0
    assert gpio[0] == []


def test_imports_and_primary_entry_point_need_no_camera_or_gpio():
    script = """
import sys
sys.modules['cv2'] = None
sys.modules['picamera2'] = None
sys.modules['gpiozero'] = None
import src.main, src.motor_test, src.motor_controller
raise SystemExit(src.main.main(['--motor', '1', '--steps', '2']))
"""
    result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "SIMULATION" in result.stdout
