# Motor Test Implementation Plan

**Goal:** Test one or two STEP/DIR motors over SSH without camera dependencies.

**Architecture:** Preserve the sorter and its configuration as explicit legacy files. Refactor the existing pulse controller for selected motors and use the same validation in simulation and hardware. The new terminal entry point defaults to simulation and gates hardware with wiring confirmation.

**Tech Stack:** Python standard library, gpiozero/lgpio on Pi, pytest.

1. Add failing tests for selection, pulse counts, direction, configuration, hardware gating and cleanup. Run with `python -m pytest tests/test_motor_test.py -q`.
2. Preserve `src/main.py`, `src/motor_controller.py` and `config.json` as legacy files; retarget existing regression tests. Stub only the camera library boundary so those tests run without OpenCV.
3. Refactor `src/motor_controller.py`, add `src/motor_test.py`, replace `src/main.py` with the motor entry point, and update `config.json`. Reuse the STEP/DIR pulse loop; initialize GPIO only after a validated command.
4. Update README, Pi setup, wiring, requirements and Windows launcher. Document signal-interface polarity, floating pins after release, holding current, current limits, microstepping and troubleshooting.
5. Run all hardware-independent tests and CLI simulation examples, review the code and documentation, and report exact Pi commands. Do not claim physical testing or push changes.
