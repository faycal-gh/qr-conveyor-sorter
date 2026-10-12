from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


class MotorController(Protocol):
    def execute(self, direction: str) -> None: ...
    def close(self) -> None: ...


class SimulationMotorController:
    """Windows/development controller: prints what the real motors would do."""

    def __init__(self, movement_steps: dict[str, int]):
        self.movement_steps = movement_steps

    def execute(self, direction: str) -> None:
        steps = self.movement_steps[direction]
        mapping = {
            "forward": "M1 FORWARD + M2 FORWARD",
            "left": "M1 REVERSE + M2 FORWARD",
            "right": "M1 FORWARD + M2 REVERSE",
        }
        print(f"[SIM MOTOR] {direction.upper():7s} | {mapping[direction]} | {steps} steps")

    def close(self) -> None:
        pass


@dataclass
class _StepperPins:
    step: int
    direction: int
    invert_direction: bool = False


class RPiTB6600Controller:
    """Raspberry Pi GPIO controller for two STEP/DIR TB6600 drivers.

    GPIO Zero is imported only when this class is constructed, so the project
    remains runnable on Windows in simulation mode.
    """

    def __init__(
        self,
        *,
        motor1: _StepperPins,
        motor2: _StepperPins,
        movement_steps: dict[str, int],
        step_delay_seconds: float,
    ):
        try:
            from gpiozero import OutputDevice
        except ImportError as exc:
            raise RuntimeError(
                "gpiozero is required on Raspberry Pi. Install it with: "
                "sudo apt install python3-gpiozero"
            ) from exc

        self._OutputDevice = OutputDevice
        self.m1 = motor1
        self.m2 = motor2
        self.movement_steps = movement_steps
        self.step_delay = step_delay_seconds

        self.m1_step = OutputDevice(motor1.step, initial_value=False)
        self.m1_dir = OutputDevice(motor1.direction, initial_value=False)
        self.m2_step = OutputDevice(motor2.step, initial_value=False)
        self.m2_dir = OutputDevice(motor2.direction, initial_value=False)

    def _set_dir(self, output, logical_forward: bool, invert: bool) -> None:
        physical_value = logical_forward ^ invert
        output.value = 1 if physical_value else 0

    def _run_two(self, m1_forward: bool, m2_forward: bool, steps: int) -> None:
        try:
            self._set_dir(self.m1_dir, m1_forward, self.m1.invert_direction)
            self._set_dir(self.m2_dir, m2_forward, self.m2.invert_direction)

            # Give the driver direction input a moment to settle before stepping.
            time.sleep(0.01)

            for _ in range(steps):
                self.m1_step.on()
                self.m2_step.on()
                time.sleep(self.step_delay)
                self.m1_step.off()
                self.m2_step.off()
                time.sleep(self.step_delay)
        finally:
            try:
                self.m1_step.off()
            finally:
                self.m2_step.off()

    def execute(self, direction: str) -> None:
        steps = int(self.movement_steps[direction])

        # Two-motor differential mapping.
        # This is NOT true 4-wheel mecanum strafing.
        if direction == "forward":
            self._run_two(True, True, steps)
        elif direction == "left":
            self._run_two(False, True, steps)
        elif direction == "right":
            self._run_two(True, False, steps)
        else:
            raise ValueError(f"Unsupported direction: {direction}")

    def close(self) -> None:
        for device in (self.m1_step, self.m1_dir, self.m2_step, self.m2_dir):
            device.close()


def build_motor_controller(config: dict) -> MotorController:
    motor_cfg = config["motors"]

    if config.get("simulation", True):
        return SimulationMotorController(motor_cfg["movement_steps"])

    pins = motor_cfg["pins"]
    invert = motor_cfg.get("invert_direction", {})

    return RPiTB6600Controller(
        motor1=_StepperPins(
            step=int(pins["motor1_step"]),
            direction=int(pins["motor1_dir"]),
            invert_direction=bool(invert.get("motor1", False)),
        ),
        motor2=_StepperPins(
            step=int(pins["motor2_step"]),
            direction=int(pins["motor2_dir"]),
            invert_direction=bool(invert.get("motor2", False)),
        ),
        movement_steps=motor_cfg["movement_steps"],
        step_delay_seconds=float(motor_cfg["step_delay_seconds"]),
    )
