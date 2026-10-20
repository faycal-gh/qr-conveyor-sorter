# Raspberry Pi 5 setup over SSH

Target: Raspberry Pi 5, Raspberry Pi OS 64-bit (Debian Trixie), Python 3.13, OpenCV/FFmpeg and gpiozero/lgpio. Android IP Webcam is the primary camera; CSI and USB remain supported. Everything runs headlessly over SSH. Keep the mechanism unloaded for initial checks.

## Installation

For the existing checkout, run as `pi`, without wrapping setup in sudo:

```bash
cd ~/qr-conveyor-sorter
git pull --ff-only
./setup_pi.sh
./run_qr.sh --show-config
./run_qr.sh --simulate
```

Adjust the checkout path if necessary. Setup checks installed OS packages first; apt update/install runs only for missing `python3-venv`, `python3-opencv`, `python3-gpiozero`, `python3-lgpio` or `util-linux`. It creates/reuses `.venv` with system site packages and checks OpenCV's FFmpeg backend. It opens no GPIO or camera and retains existing `config.local.json`. It never invokes the Wi-Fi installer, systemd, hostname configuration or SSH configuration. The venv approach follows [Raspberry Pi's Python guidance](https://www.raspberrypi.com/documentation/computers/os.html).

Optional developer tests and QR-image regeneration need additional packages:

```bash
sudo apt install -y python3-pytest python3-qrcode python3-pil
.venv/bin/python -m pytest -q
.venv/bin/python tools/generate_test_qr.py
```

Tests decode real QR images and mock GPIO/camera faults. They do not verify motors, the Samsung phone or electrical signals. On Windows use `.venv/Scripts/python -m pytest -q` after installing `requirements-windows.txt`.

## Android IP Webcam and saved settings

1. Connect the Samsung phone and Pi to the same reachable Wi-Fi. Start the IP Webcam app's video server. Use the address displayed by the phone, with its video endpoint `/video`; the phone's address may change after switching networks.
2. On first setup, paste the full video URL at `Enter Android IP Webcam URL:`. Only HTTP(S) URLs with valid hosts/ports are accepted; embedded login credentials, queries, fragments, file paths and whitespace are rejected. No phone address is built into source or tracked defaults.
3. Keep the app running and use a moderate resolution/frame rate that your Wi-Fi and Pi can decode. Android battery/background restrictions or a stopped server will terminate the scanner session.
4. Start `./run_qr.sh --simulate`. Remove every QR until `[STATE] QR cleared` appears, then show a supported QR. Verify both printed logical directions before hardware use.

`config.local.json` is ignored by Git, written atomically with private permissions on Linux, and contains the complete effective settings. Do not commit it. The launcher initially copies the verified motor configuration unchanged from `config.json`, sets the camera to `ipwebcam`, and selects simulation. To change the phone address later:

```bash
./run_qr.sh --configure
# Or replace PHONE_HOST with the phone's current address:
./run_qr.sh --camera-url 'http://PHONE_HOST:8080/video'
./run_qr.sh --show-config
```

Configuration commands save and exit without opening GPIO or a camera. Camera URL changes retain hardware consent; motor settings changes invalidate it. Revocation selects simulation, disables Motor 2 and resets the bench default selector to Motor 1. The exact [movement table, tuning commands and hardware consent procedure](../README.md#live-qr-scanning-over-ssh) are in the README. Both GPIO pairs, polarity and direction settings remain explicit; Motor 1's verified behavior does not certify Motor 2.

### Camera loss and restart policy

The FFmpeg stream has five-second open and two-second read timeouts, supplied as [OpenCV open-time properties](https://docs.opencv.org/4.10.0/d4/d15/group__videoio__flags__base.html). A capture thread drains frames throughout motor movement and retains only its latest frame. The scanner consumes each captured sequence at most once, rejects locally stale frames older than one second, and discards a one-second startup warmup. It rechecks stream health and the command frame's age after QR decoding, before starting movement. These timestamps measure local capture, not an authenticated phone timestamp; network/server latency cannot be proven from MJPEG alone.

Any capture failure or three-second wait without a fresh frame terminates scanning. There is no automatic reconnect or movement after Wi-Fi restoration. An already-started finite movement may finish before camera failure is observed; press Ctrl+C to interrupt it. Close/reopen the stream by running `./run_qr.sh` after restoring the phone/network. Every IP-camera session begins locked and requires eight consecutive QR-free detections before any command, even if a valid QR remains visible from the previous session. Invalid/undecodable visible QRs cannot rearm it.

If provisioning switches the Pi into setup mode, restore normal client Wi-Fi using the existing provisioning workflow, connect the phone to that network, and restart the scanner manually. No QR application command changes provisioning or starts motors on reconnection.

## Camera checks and troubleshooting

For a CSI camera, check detection and capture over SSH:

```bash
sudo apt install -y --no-install-recommends python3-picamera2 rpicam-apps
rpicam-hello --list-cameras
rpicam-still --nopreview --timeout 2000 --output /tmp/camera-check.jpg
python3 -m src.qr_motor_test --simulate
```

The [official camera guide](https://www.raspberrypi.com/documentation/computers/camera_software.html) describes these tools. If no camera is listed, power off before checking the ribbon and Pi 5 cable. Set `camera.backend` to `picamera2` and `camera.index` to the detected camera number in `config.local.json` to use it through `./run_qr.sh`. The direct `src.qr_motor_test` command above uses the original `config.json` CSI defaults.

For USB, set `camera.backend` to `opencv` in `config.local.json`, check `ls -l /dev/video*`, and set `camera.index`. Width/height request a device resolution; IP Webcam resolution is configured on the phone instead. Check device permissions and `id`; if necessary add your user to `video` and reconnect. No OpenCV preview window is opened.

| Error / symptom | Action |
|---|---|
| Missing Picamera2 or OpenCV | Run the apt commands above; ensure the active venv uses system site packages |
| Could not open CSI/webcam device | Check backend/index, cabling and permissions; close other camera apps |
| Camera capture failure/disconnection | Scanner stops and releases resources; reconnect/check the camera and restart. CSI capture has a five-second frame timeout |
| IP Webcam cannot open or disconnects | Check the saved URL, phone server, shared reachable Wi-Fi and OpenCV FFmpeg support. Restart manually; no automatic motor resumption |
| Phone/Pi cannot communicate | Check whether guest Wi-Fi or client isolation blocks peer traffic. Keep the phone server active; reconnect both devices to normal Wi-Fi after provisioning recovery |
| QR detected but no movement command | Check the exact payload against the README table; increase QR size, improve focus/lighting, avoid phone glare, preserve its white border |
| Command executed once, then ignored | Remove every QR until `[STATE] QR cleared` appears; default is eight consecutive QR-free frames |
| Hardware session reports disabled motor | Finish checking both drivers and enable both motors in the config; simulation does not require connected motors |
| Hardware confirmation invalid | Inspect `./run_qr.sh --show-config`, verify the changed motor settings, then run `./run_qr.sh --enable-hardware` again |
| Another QR launcher is running | Stop the previous launcher. Do not delete/recreate its lock file while running, or run another GPIO tool concurrently |

Show one QR at a time. Simulation prints both intended motor directions without opening GPIO. The exact differential mapping and committed PNG links are in [live QR scanning](../README.md#live-qr-scanning-over-ssh). Regenerate them with `python3 tools/generate_test_qr.py`; every output is decoded and verified.

After both drivers pass [wiring checks](WIRING.md):

```bash
./run_qr.sh --enable-hardware
./run_qr.sh
```

The first command records explicit consent and enables Motor 2 locally; the second starts scanning in the saved hardware mode. Clear the IP camera view first, then show a valid QR to trigger both motors. Use Ctrl+C to stop, including during movement. Revoke consent with `./run_qr.sh --revoke-hardware`. The bench menu and legacy sorter remain separate entry points with their original per-run flags.

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
