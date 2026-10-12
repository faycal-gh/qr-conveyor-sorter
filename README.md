# NEMA 17 motor bench test

The primary application now tests TB6600-style **STEP/DIR stepper drivers** from an SSH terminal. It needs no camera, QR scanner, conveyor or sensors. It is not a PWM servo controller. Raspberry Pi 5 / Raspberry Pi OS 64-bit Trixie / Python 3.13 is the target hardware environment; simulation also runs on Windows.

Simulation is the default. Motor 1 is enabled; Motor 2 is disabled and need not be connected. Launching the menu does not open GPIO or move a motor.

## Install on Raspberry Pi

```bash
sudo apt update
sudo apt install -y git python3-venv python3-gpiozero python3-lgpio
git clone https://github.com/faycal-gh/qr-conveyor-sorter.git
cd qr-conveyor-sorter
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements-pi.txt
python3 -m pytest -q
```

These commands assume the motor-test changes are present in your checkout. See [Pi setup](docs/RASPBERRY_PI_SETUP.md) for an existing checkout and GPIO diagnostics. Runtime simulation uses only Python's standard library; pytest is for tests. The venv exposes the apt-installed GPIO packages, following [GPIO Zero's installation guidance](https://gpiozero.readthedocs.io/en/latest/installing.html).

## Run through SSH

Interactive menu:

```bash
python3 -m src.motor_test
```

Menu choices test Motor 1 forward/reverse, Motor 2 forward/reverse, both forward, custom steps/speed, or exit. Forward/reverse are logical directions: physical clockwise depends on wiring and viewing side. Set `invert_direction.motor1` or `.motor2` to swap the logical mapping.

One command, in simulation:

```bash
python3 -m src.motor_test --motor 1 --direction forward --steps 200
python3 -m src.motor_test --motor 1 --direction reverse --steps 200
python3 -m src.motor_test --motor 1 --steps 100 --speed 50
```

Each prints the motor, BCM pins, requested direction, physical GPIO DIR level, pulse count, nominal pulse rate, high/low durations, mode and result. Simulation prints the STEP/DIR sequence without sleeping or opening GPIO. `python3 -m src.main` and `python3 src/main.py` use the same motor menu.

## Enable hardware deliberately

First read [wiring and electrical safety](docs/WIRING.md). Confirm the driver manual, signal interface, pulse polarity, coil pairs, current limit, microstep switches and unloaded mechanism before energizing it.

Only after those checks:

```bash
python3 -m src.motor_test --hardware --confirm-wiring --motor 1 --direction forward --steps 200
python3 -m src.motor_test --hardware --confirm-wiring --motor 1 --direction reverse --steps 200
python3 -m src.motor_test --hardware --confirm-wiring
```

Hardware mode requires both flags on each invocation. Changing `simulation` to `false` in the file alone never enables the CLI's GPIO mode. `--simulate` forces simulation and is mutually exclusive with `--hardware`.

For Motor 2, set `motors.enabled.motor2` to `true` in `config.json`, connect and check its driver, then run:

```bash
python3 -m src.motor_test --hardware --confirm-wiring --motor 2 --direction forward --steps 200
python3 -m src.motor_test --hardware --confirm-wiring --motor 2 --direction reverse --steps 200
python3 -m src.motor_test --hardware --confirm-wiring --motor both --steps 200
```

Both motors receive interleaved pulses in the same loop; this is a bench test, not precision synchronized motion. A disabled motor or invalid command produces `[ERROR]` before GPIO opens; e.g. Motor 2 initially reports `motor2 is disabled; enable it in config.json first`. Both selection requires both enabled.

## Configuration

Edit `config.json`, or use `--config /path/to/config.json`. The old sorter settings are preserved separately in `config-sorter.json`.

| Field under `motors` | Default / purpose |
|---|---|
| `enabled` | Motor 1 true, Motor 2 false; independent switches |
| `pins` | Motor 1 STEP 18, DIR 23; Motor 2 STEP 24, DIR 25; BCM numbering |
| `invert_direction` | False for each motor; forward normally means GPIO DIR high |
| `pulse_active_high` | True: STEP idle low, pulses high; false: idle high, pulses low; match the verified interface |
| `default_motor` | `"1"`; used by a one-shot command without `--motor` |
| `default_steps` | 200 STEP pulses per menu movement |
| `max_steps` | 10000 per command, per motor; configurable from 1 to 1000000 |
| `pulse_high_seconds` | 0.005 |
| `pulse_low_seconds` | 0.005; nominal rate = 1 / (high + low) = 100 pulses/s |
| `direction_setup_seconds` | 0.01; DIR setup and final hold time |
| `gpiochip` | 0; verify against the Pi's GPIO header chip |

Durations must be finite and between 0.001 and 1 second. `--steps` overrides the default count within `max_steps`. `--speed` is pulses/s and changes only low duration; it must leave that duration within the same range. For example 50 pulses/s gives 5 ms high and 15 ms low. Verify all timings against the exact driver manual; increase durations if its requirements are longer.

Constant slow speed is intentional for unloaded tests. Python/Linux scheduling adds jitter and overhead; the printed rate is nominal, not measured. There is no acceleration ramp or calibrated position feedback.

**200 pulses are not necessarily one revolution.** Pulses/revolution = full steps/revolution from the motor datasheet × driver microstep factor. If a verified 1.8-degree motor has 200 full steps and the driver is set to 1/8 microstepping, it needs 1600 pulses/revolution. Use the driver's DIP table; some labels already give pulses/revolution.

## Stop

Select 7 while idle or press Ctrl+C during motion (exit code 130). Motion blocks menu input, so use Ctrl+C to stop a running command. Normal completion, errors and interruption release allocated GPIO resources. STEP is made inactive before DIR is reset low, then pins are released; the interface must provide a safe idle bias when GPIO floats. A successful command only means the software completed its pulse loop.

Stopping STEP does **not** remove holding current. ENA is not controlled here. Use the driver's documented enable circuit or safely switch off the driver supply to remove current. Ctrl+C is software control, not an emergency-stop circuit. See the wiring document for power and shutdown details.

## Windows simulation

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-windows.txt
python -m src.motor_test
python -m pytest -q
```

`run_windows.ps1` performs this installation and launches the motor menu.

## Preserved QR sorter

Camera, parser, QR images and generator remain in the repository. The former entry point and controller are preserved in `src/legacy_sorter.py` and `src/legacy_motor_controller.py`; the former configuration is `config-sorter.json` (simulation true).

To run the old camera-based simulation deliberately, install its optional dependencies separately:

```bash
# Raspberry Pi only, if restoring the CSI camera path:
sudo apt install -y python3-opencv python3-picamera2
# QR image generator only:
python3 -m pip install 'qrcode[pil]>=8,<9'
python3 -m src.legacy_sorter
```

For Windows legacy camera simulation install `opencv-python>=4.10,<5` in the venv. Choose `opencv` or `picamera2` in `config-sorter.json` as appropriate. The archived controller retains the old differential movement mapping and is not the motor bench test. Do not use its unreviewed hardware path for these initial tests; keep its simulation flag true. Restoring sorter hardware needs its own wiring, GPIO-backend and motion review.

No physical Raspberry Pi, driver or motor verification has been performed by this repository change.
