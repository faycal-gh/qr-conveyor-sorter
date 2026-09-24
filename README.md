# QR Conveyor Sorter

A Raspberry Pi 5 project that scans a QR code on a moving parcel and immediately commands two TB6600-driven NEMA 17 stepper motors according to the QR direction.

Supported QR payloads:

- `direction:left`
- `direction:right`
- `direction:forward`
- JSON, for example: `{"order_id":"ORD001","direction":"left"}`

## Important mechanical note

This repository currently implements a **two-motor differential profile**:

- `forward`: both motors run forward
- `left`: motor 1 reverse, motor 2 forward
- `right`: motor 1 forward, motor 2 reverse

With a normal 4-wheel mecanum platform, true sideways LEFT/RIGHT strafing requires **4 independently driven motors**. If your final mechanical sorter uses another two-motor mecanum/roller arrangement, update the movement mapping in `src/motor_controller.py`.

## How the control logic works

There is **no IR sensor** in this version.

1. Camera continuously reads frames.
2. QR code is decoded.
3. Direction is validated.
4. Motors start immediately.
5. The same visible QR is locked out so it cannot trigger the motors repeatedly every frame.
6. After the QR disappears for several frames, the system is ready for the next parcel.

## Windows development first

You can develop and test the project without a Raspberry Pi.

On Windows the project runs in simulation mode and can use your PC webcam. Motor commands are printed instead of GPIO signals being sent.

### Requirements

- Python 3.11+ recommended
- Git
- Optional: GitHub CLI (`gh`) for one-command repository creation/push
- A webcam if you want to test QR scanning now

### Quick start on Windows

Open PowerShell inside the project folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-windows.txt
python src\main.py
```

Show a QR containing one of the supported commands to your webcam.

Press `Q` to quit the preview.

## Generate test QR images

```powershell
python tools\generate_test_qr.py
```

The generated files will appear in `test_qr_codes/`.

## Raspberry Pi installation later

See:

- [`docs/RASPBERRY_PI_SETUP.md`](docs/RASPBERRY_PI_SETUP.md)
- [`docs/WIRING.md`](docs/WIRING.md)

## Configuration

Edit `config.json`.

For Windows keep:

```json
"simulation": true,
"backend": "opencv"
```

Later on Raspberry Pi use:

```json
"simulation": false,
"backend": "picamera2"
```

## Conveyor data

Current project assumptions:

- conveyor length: `0.80 m`
- conveyor speed: `0.141 m/s`
- theoretical full-length travel time: about `5.67 s`

Because this version acts immediately after QR detection, that travel time is informational rather than being used as a motor-start delay.

## GitHub

The included `push_to_github.ps1` can initialize Git and create/push the repository with GitHub CLI.

```powershell
.\push_to_github.ps1
```

Default GitHub owner: `faycal-gh`

Default repository name: `qr-conveyor-sorter`
