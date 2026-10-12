from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import legacy_motor_controller as motor_controller
from legacy_motor_controller import (
    RPiTB6600Controller,
    SimulationMotorController,
    _StepperPins,
    build_motor_controller,
)


class _Output:
    def __init__(self):
        self.value = 0

    def on(self):
        self.value = 1

    def off(self):
        self.value = 0


def test_step_outputs_return_low_if_pulse_loop_raises():
    controller = RPiTB6600Controller.__new__(RPiTB6600Controller)
    controller.m1 = _StepperPins(step=18, direction=23)
    controller.m2 = _StepperPins(step=24, direction=25)
    controller.m1_step = _Output()
    controller.m1_dir = _Output()
    controller.m2_step = _Output()
    controller.m2_dir = _Output()
    controller.step_delay = 0.001

    with patch.object(
        motor_controller.time,
        "sleep",
        side_effect=[None, RuntimeError("pulse failure")],
    ):
        try:
            controller._run_two(True, True, 2)
        except RuntimeError as error:
            assert str(error) == "pulse failure"
        else:
            raise AssertionError("pulse failure should propagate")

    assert controller.m1_step.value == 0
    assert controller.m2_step.value == 0


def test_step_outputs_return_low_on_keyboard_interrupt():
    controller = RPiTB6600Controller.__new__(RPiTB6600Controller)
    controller.m1 = _StepperPins(step=18, direction=23)
    controller.m2 = _StepperPins(step=24, direction=25)
    controller.m1_step = _Output()
    controller.m1_dir = _Output()
    controller.m2_step = _Output()
    controller.m2_dir = _Output()
    controller.step_delay = 0.001

    with patch.object(
        motor_controller.time,
        "sleep",
        side_effect=[None, KeyboardInterrupt()],
    ):
        try:
            controller._run_two(True, True, 2)
        except KeyboardInterrupt:
            pass
        else:
            raise AssertionError("keyboard interrupt should propagate")

    assert controller.m1_step.value == 0
    assert controller.m2_step.value == 0


def test_windows_simulation_selects_print_only_motor_controller():
    config = {
        "simulation": True,
        "motors": {
            "movement_steps": {"forward": 10, "left": 20, "right": 30},
        },
    }
    controller = build_motor_controller(config)
    assert isinstance(controller, SimulationMotorController)
