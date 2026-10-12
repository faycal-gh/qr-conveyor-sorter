# Raspberry Pi 5 setup over SSH

Target: Raspberry Pi OS 64-bit (Debian Trixie), Python 3.13, Picamera2/OpenCV, gpiozero with lgpio. QR scanning uses a real camera and works over SSH without a display. Motor-only testing needs no camera. Keep the motor mechanism unloaded for initial tests.

## Installation

Use the [README installation commands](../README.md#install-on-raspberry-pi) for a fresh clone. For an existing clean checkout, update the current branch, then:

```bash
cd ~/qr-conveyor-sorter
git pull --ff-only
sudo apt update
sudo apt install -y python3-venv python3-gpiozero python3-lgpio
sudo apt install -y python3-opencv python3-qrcode python3-pil rpicam-apps
sudo apt install -y --no-install-recommends python3-picamera2
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements-pi.txt
python3 --version
python3 -c "import gpiozero, lgpio; print('GPIO packages available')"
python3 -c "import cv2, picamera2, qrcode, PIL; print('Camera and QR packages available')"
python3 -m pytest -q
python3 -m src.motor_test --simulate --motor 1 --steps 200
```

The `~/qr-conveyor-sorter` path assumes cloning into your home directory; adjust it if needed. If you already created a venv without system packages, edit its `pyvenv.cfg` to set `include-system-site-packages = true`, then reactivate. Do not install pip packages into the system Python with `sudo pip` or `--break-system-packages`. The venv approach follows [Raspberry Pi's Python guidance](https://www.raspberrypi.com/documentation/computers/os.html).

Expected motor-test simulation output includes GPIO18, GPIO23, 200 STEP pulses and 100.00 pulses/s. Tests include real OpenCV decoding of generated PNGs and simulated camera/GPIO faults. They do not test physical cameras or electrical signals. OpenCV and qrcode are available for Trixie through [Debian OpenCV](https://packages.debian.org/trixie/python3-opencv) and [Debian qrcode](https://packages.debian.org/trixie/python3-qrcode); install Picamera2 from Raspberry Pi OS apt rather than pip.

## Camera checks and troubleshooting

For a CSI camera, check detection and capture over SSH:

```bash
rpicam-hello --list-cameras
rpicam-still --nopreview --timeout 2000 --output /tmp/camera-check.jpg
python3 -m src.qr_motor_test --simulate
```

The [official camera guide](https://www.raspberrypi.com/documentation/computers/camera_software.html) describes these camera tools. `--list-cameras` should list a camera and sensor modes. If no camera is listed, power off the Pi before checking ribbon orientation, connector seating and the correct Pi 5 camera cable. Stop other processes using the camera. Set `camera.backend` to `picamera2` and `camera.index` to the detected camera number in `config.json`.

For USB, set `camera.backend` to `opencv`, check `ls -l /dev/video*`, and choose the corresponding device index. Check device permissions and `id`; add your user to the device's `video` group if required, then log out and reconnect. No OpenCV preview window is opened by the QR scanner.

| Error / symptom | Action |
|---|---|
| Missing Picamera2 or OpenCV | Run the apt commands above; ensure the active venv uses system site packages |
| Could not open CSI/webcam device | Check backend/index, cabling and permissions; close other camera apps |
| Camera capture failure/disconnection | Scanner stops and releases resources; reconnect/check the camera and restart. CSI capture has a five-second frame timeout |
| QR detected but no movement command | Check the exact payload against the README table; increase QR size, improve focus/lighting, avoid phone glare, preserve its white border |
| Command executed once, then ignored | Remove every QR until `[STATE] QR cleared` appears; default is eight consecutive QR-free frames |
| Hardware session reports disabled motor | Finish checking both drivers and enable both motors in the config; simulation does not require connected motors |

Show one QR at a time. Simulation prints both intended motor directions without opening GPIO. The exact differential mapping and committed PNG links are in [live QR scanning](../README.md#live-qr-scanning-over-ssh). Regenerate them with `python3 tools/generate_test_qr.py`; every output is decoded and verified.

After both drivers pass [wiring checks](WIRING.md) and both enabled switches are true:

```bash
python3 -m src.qr_motor_test --hardware --confirm-wiring
```

This immediately starts scanning and a valid QR triggers both motors. Use Ctrl+C to stop, including during movement. The motor bench menu and legacy sorter remain separate entry points.

## GPIO chip and permissions

The application explicitly constructs [LGPIOFactory](https://gpiozero.readthedocs.io/en/stable/api_pins.html) using `motors.gpiochip`. The default is 0 for this Trixie setup. Chip numbering can differ between OS/kernel versions; verify the header GPIO controller before hardware mode. Do not blindly copy an older Pi 5 `gpiochip4` example.

```bash
ls -l /dev/gpiochip*
id
# Optional read-only GPIO diagnostics:
sudo apt install -y gpiod
gpiodetect
gpioinfo
```

Identify the RP1 GPIO header controller by its label/line names (e.g. GPIO18, GPIO23, GPIO24 and GPIO25) and put its `/dev/gpiochipN` number in `motors.gpiochip`. Check that your SSH user has read/write permission for that device. If its group is `gpio` and your user is not a member:

```bash
sudo usermod -aG gpio "$USER"
```

Log out and reconnect over SSH for group changes to take effect. Do not run the application as root to mask permission or chip-selection errors. Stop another application that has claimed these pins. Hardware errors return status 1 and never silently switch to simulation.

## Initial hardware command

Keep Motor 2 disabled. Complete the [wiring checks](WIRING.md) with driver power off, then energize the checked setup and deliberately run:

```bash
source .venv/bin/activate
python3 -m src.motor_test --hardware --confirm-wiring --motor 1 --direction forward --steps 200
python3 -m src.motor_test --hardware --confirm-wiring --motor 1 --direction reverse --steps 200
```

Use [README motor commands](../README.md#enable-hardware-deliberately) for the menu, Motor 2 and both. Use Ctrl+C during motion; select 7 while idle. Avoid abruptly killing the process, losing SSH, or shutting down the Pi with driver power on. Software cannot guarantee cleanup after SIGKILL, power loss or hardware faults; the interface's idle bias and a physical driver-power disconnect are required.

## If the motor vibrates without rotating

1. Switch off driver power and wait for discharge before touching motor wiring. Identify and recheck the two coil pairs; mixing wires from different coils is a common cause.
2. Verify the driver's enable state and configured current limit against its manual and the exact motor datasheet. Check peak/RMS labels; do not assume a current value from the model name alone.
3. Check motor supply voltage at the driver, terminal tightness, cable continuity and whether the motor shaft is mechanically blocked.
4. Verify the signal interface delivers the required optocoupler current and polarity. Check STEP edges and stable DIR at the driver with suitable measuring equipment. An LED or the software's completion message does not prove the driver receives valid pulses.
5. Reduce the nominal rate for an unloaded test:

   ```bash
   python3 -m src.motor_test --hardware --confirm-wiring --motor 1 --steps 100 --speed 50
   ```

6. Check the DIP switches for microstepping: a small command at a high subdivision may produce very little visible motion. Recalculate pulses/revolution as explained in the README.

If problems persist, stop and check the exact driver/motor manuals and interface wiring before increasing speed or current. This application does not implement acceleration or closed-loop confirmation.
