# QR camera control and NEMA 17 motor bench test

Run `./run_qr.sh` over SSH to scan Android IP Webcam video and control both NEMA17 motors through their TB6600-style **STEP/DIR drivers**. The existing controller, CSI/USB camera support and motor-only bench menu remain available. Target: Raspberry Pi 5 / Raspberry Pi OS 64-bit Trixie / Python 3.13.

Simulation is the default. Motor 2 remains disabled until you explicitly confirm both motors' hardware checks. The ULN2803 switches driver input signals; the microstep drivers supply motor winding current. Existing GPIO assignments, Motor 1 polarity and timing are preserved.

## Install on Raspberry Pi

```bash
ssh pi@qr-conveyor.local
cd ~/qr-conveyor-sorter
git pull --ff-only
./setup_pi.sh
./run_qr.sh
```

Start the IP Webcam server on your Samsung phone first and connect it to the same reachable network as the Pi. Setup prompts for the phone's full HTTP(S) video URL. It installs only missing OS packages and creates/reuses a venv with system site packages; no daily activation command is needed. It does not change Wi-Fi, SSH, hostname or provisioning services. See [Pi setup](docs/RASPBERRY_PI_SETUP.md) for Android setup, optional cameras, tests and diagnostics.

## Live QR scanning over SSH

Everyday execution uses saved settings. To force real-camera scanning with simulated motors:

```bash
./run_qr.sh --simulate
```

No desktop or preview window is required. Simulation never opens GPIO. Show one of these committed images on another display or print it; the Samsung phone is the camera:

| Image / exact payload | Motor 1 | Motor 2 |
|---|---|---|
| [qr_forward.png](test_qr_codes/qr_forward.png): `direction: forward` | FORWARD | FORWARD |
| [qr_left.png](test_qr_codes/qr_left.png): `direction: left` | FORWARD | REVERSE |
| [qr_right.png](test_qr_codes/qr_right.png): `direction: right` | REVERSE | FORWARD |

LEFT/RIGHT are differential commands. Case and whitespace are normalized; unsupported payloads do not move motors. Valid JSON payloads from the existing parser remain supported. The terminal prints `[CAMERA] Camera initialized`, decoded payloads, both logical motor directions, execution start/completion, pulse count and nominal speed. Defaults are 200 pulses per motor at 100 pulses/s. Logical directions still respect each motor's configured inversion.

Each valid QR executes once. Remove every QR for `qr.clear_frames_required` consecutive frames (default 8) to rearm. IP-camera sessions also require this removal at startup, including after a manual restart. Changing to a different QR while locked cannot move motors. Visible invalid or undecodable codes reset the clear-frame count. Detection can miss a badly lit code, so the gate is based on detection, not physical presence. Decoding pauses during movement; background IP capture keeps draining and retains only its newest frame. Commands cannot overlap.

Local settings are stored in ignored `config.local.json`, copied initially from the existing motor configuration. Change the camera URL interactively with `./run_qr.sh --configure`, or use `./run_qr.sh --camera-url 'http://PHONE_HOST:8080/video'` (replace PHONE_HOST). View settings with `./run_qr.sh --show-config`. CSI and USB remain supported; see the [camera guide](docs/RASPBERRY_PI_SETUP.md#camera-checks-and-troubleshooting).

Camera loss, decode failure or missing fresh frames stops the session with an error; it never automatically reconnects or starts a new movement. An already-running finite motor command can finish before the scanner observes camera loss. Restore the phone/network, run `./run_qr.sh` again, and remove all QRs before presenting a new command. The Pi/phone must rejoin normal Wi-Fi if provisioning recovery has activated the setup hotspot.

Regenerate and verify the three black-on-white PNGs:

```bash
sudo apt install -y python3-qrcode python3-pil
.venv/bin/python tools/generate_test_qr.py
```

The script saves exactly the three named QR images above with a four-module quiet zone and decodes each back to its exact payload, failing if verification fails. Keep the full white border visible when displaying or printing them.

After completing [both drivers' wiring checks](docs/WIRING.md), explicitly enable hardware once:

```bash
./run_qr.sh --enable-hardware
./run_qr.sh
```

Type the requested phrase only after checking **both** motors, drivers, ULN2803, supply and mechanism. This saves acknowledgment and enables Motor 2 locally; subsequent launches need no repeated prompt. Confirmation is bound to the complete motor configuration: changed motor settings require confirmation again. `./run_qr.sh --revoke-hardware` clears it, disables Motor 2 and saves simulation. All four GPIO outputs must initialize before any STEP pulses. Both motors pulse in the same coordinated loop with independent DIR levels. The original `python3 -m src.qr_motor_test --hardware --confirm-wiring` interface retains its per-invocation checks.

To save a different pulse count, nominal rate or direction inversion (configuration only; no motion):

```bash
./run_qr.sh --steps 100 --speed 50
./run_qr.sh --invert-motor2
# Undo a direction inversion:
./run_qr.sh --no-invert-motor2
```

These motor changes select simulation until hardware is confirmed again. The active pulse width stays unchanged when setting speed. Do not run the bench tester or another GPIO application alongside the scanner; the shell launcher also prevents duplicate launcher sessions.

Press **Ctrl+C** to stop scanning or interrupt motion. Errors stop the session with `[ERROR]` and exit status 1; Ctrl+C returns 130. Camera and allocated GPIO resources are released. Stopping STEP does not remove holding current. See [camera troubleshooting](docs/RASPBERRY_PI_SETUP.md#camera-checks-and-troubleshooting) and [electrical safety](docs/WIRING.md).

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

The bench tester and direct scanner use `config.json` or `--config /path/to/config.json`; the one-command launcher uses ignored `config.local.json`. Edit the local file for advanced settings (such as GPIO chip or camera backend), then view it with `./run_qr.sh --show-config`. Any motor edit invalidates launcher hardware confirmation. Do not store device-specific addresses or credentials in tracked configuration files. The old sorter settings remain in `config-sorter.json`.

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
python -m src.qr_launcher --configure
python -m src.qr_launcher --simulate
python -m pytest -q
```

`run_windows.ps1` performs this installation and launches the motor menu.

## Preserved QR sorter

The former entry point and controller are preserved in `src/legacy_sorter.py` and `src/legacy_motor_controller.py`; the former configuration is `config-sorter.json` (simulation true). The new scanner uses `config.json` and the reviewed bench controller.

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

## Automatic Wi-Fi provisioning

Optional, independent Raspberry Pi Wi-Fi setup and recovery:
[deployment commands](docs/WIFI_DEPLOYMENT.md) · [architecture and troubleshooting](docs/WIFI_PROVISIONING.md).
Installation does not start or enable the service; activation is explicit.
