from __future__ import annotations

from contextlib import ExitStack
import math
import time


def _integer(name, number, minimum, maximum):
    if type(number) is not int or not minimum <= number <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")


def _duration(name, seconds):
    if (type(seconds) not in (int, float) or not math.isfinite(seconds)
            or not 0.001 <= seconds <= 1):
        raise ValueError(f"{name} must be finite and between 0.001 and 1 second")


def validate_motor_config(config):
    try:
        if type(config["simulation"]) is not bool:
            raise ValueError("simulation must be true or false")
        motors = config["motors"]
        pins = []
        for name in ("motor1", "motor2"):
            for field in ("enabled", "invert_direction"):
                if type(motors[field][name]) is not bool:
                    raise ValueError(f"{field}.{name} must be true or false")
            for signal in ("step", "dir"):
                pin = motors["pins"][f"{name}_{signal}"]
                _integer(f"{name}_{signal} BCM GPIO", pin, 0, 27)
                pins.append(pin)
        if len(set(pins)) != len(pins):
            raise ValueError("STEP and DIR GPIO assignments must all be distinct")
        if type(motors["pulse_active_high"]) is not bool:
            raise ValueError("pulse_active_high must be true or false")
        _integer("gpiochip", motors["gpiochip"], 0, 255)
        _integer("max_steps", motors["max_steps"], 1, 1000000)
        _integer("default_steps", motors["default_steps"], 1, motors["max_steps"])
        for field in ("pulse_high_seconds", "pulse_low_seconds", "direction_setup_seconds"):
            _duration(field, motors[field])
        _selected_motors(motors, motors["default_motor"])
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Missing or malformed motor configuration: {exc}") from exc


def _selected_motors(config, motor):
    if motor not in ("1", "2", "both"):
        raise ValueError("motor must be 1, 2 or both")
    selected = ("motor1", "motor2") if motor == "both" else (f"motor{motor}",)
    for name in selected:
        if not config["enabled"][name]:
            raise ValueError(f"{name} is disabled; enable it in config.json first")
    return selected


class StepperController:
    def __init__(self, config):
        self.config = config["motors"]
        self.simulation = config["simulation"]

    def run(self, motor, direction, steps=None, speed=None):
        selected = _selected_motors(self.config, motor)
        if direction not in ("forward", "reverse"):
            raise ValueError("direction must be forward or reverse")
        steps = self.config["default_steps"] if steps is None else steps
        _integer("steps", steps, 1, self.config["max_steps"])
        high = self.config["pulse_high_seconds"]
        low = self.config["pulse_low_seconds"]
        if speed is not None:
            if type(speed) not in (int, float) or not math.isfinite(speed) or speed <= 0:
                raise ValueError("speed must be finite and positive (pulses/s)")
            low = 1 / speed - high
            _duration("low duration at requested speed", low)
        for name in selected:
            pins = self.config["pins"]
            level = (direction == "forward") ^ self.config["invert_direction"][name]
            print(f"{name}: STEP=GPIO{pins[name + '_step']} DIR=GPIO{pins[name + '_dir']} "
                  f"direction={direction} DIR={'HIGH' if level else 'LOW'} | {steps} STEP pulses | "
                  f"{1 / (high + low):.2f} pulses/s (high={high:g}s low={low:g}s)")
        if self.simulation:
            polarity = "HIGH/LOW" if self.config["pulse_active_high"] else "LOW/HIGH"
            print(f"[SIMULATION] Would set DIR, wait {self.config['direction_setup_seconds']:g}s, "
                  f"then repeat STEP {polarity} {steps} times per selected motor. No GPIO opened.")
            print("[SIMULATION] Complete; no physical motion verified.")
            return
        print("[HARDWARE] Running; Ctrl+C stops pulses.")
        self._run_pulses(selected, direction, steps, (high, low))
        print("[HARDWARE] Complete; GPIO released. Holding current may remain.")

    def _run_pulses(self, selected, direction, steps, timing):
        try:
            from gpiozero import OutputDevice
            from gpiozero.pins.lgpio import LGPIOFactory
        except ImportError as exc:
            raise RuntimeError("Hardware mode needs python3-gpiozero and python3-lgpio") from exc
        with ExitStack() as cleanup:
            factory = LGPIOFactory(chip=self.config["gpiochip"])
            cleanup.callback(factory.close)
            step_outputs = []
            for name in selected:
                for signal in ("step", "dir"):
                    output = OutputDevice(
                        self.config["pins"][f"{name}_{signal}"], initial_value=False,
                        active_high=self.config["pulse_active_high"] if signal == "step" else True,
                        pin_factory=factory,
                    )
                    cleanup.callback(output.close)
                    cleanup.callback(output.off)
                    if signal == "step":
                        step_outputs.append(output)
                    else:
                        output.value = (direction == "forward") ^ self.config["invert_direction"][name]
            try:
                time.sleep(self.config["direction_setup_seconds"])
                # shortcut: Python sleeps have jitter; use hardware pulses for precision or loaded motion.
                for _ in range(steps):
                    for output in step_outputs:
                        output.on()
                    time.sleep(timing[0])
                    for output in step_outputs:
                        output.off()
                    time.sleep(timing[1])
            finally:
                for output in step_outputs:
                    output.off()
                # DIR must remain stable after the final STEP edge, even on Ctrl+C.
                time.sleep(self.config["direction_setup_seconds"])


def build_motor_controller(config, *, wiring_confirmed=False):
    validate_motor_config(config)
    if not config["simulation"] and not wiring_confirmed:
        raise ValueError("Hardware mode requires --confirm-wiring after checking docs/WIRING.md")
    return StepperController(config)
