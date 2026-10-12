# Raspberry Pi 5 setup over SSH

Target: Raspberry Pi OS 64-bit (Debian Trixie), Python 3.13, gpiozero with lgpio. No camera, display or sensor is needed. Keep the motor mechanism unloaded for the initial tests.

## Installation

Use the [README installation commands](../README.md#install-on-raspberry-pi) for a fresh clone. For an existing checkout, obtain the motor-test changes first, then:

```bash
cd ~/qr-conveyor-sorter
sudo apt update
sudo apt install -y python3-venv python3-gpiozero python3-lgpio
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python3 -m pip install -r requirements-pi.txt
python3 --version
python3 -c "import gpiozero, lgpio; print('GPIO packages available')"
python3 -m pytest -q
python3 -m src.motor_test --simulate --motor 1 --steps 200
```

The `~/qr-conveyor-sorter` path assumes cloning into your home directory; adjust it if needed. If you already created a venv without system packages, edit its `pyvenv.cfg` to set `include-system-site-packages = true`, then reactivate. Do not install pip packages into the system Python with `sudo pip` or `--break-system-packages`. The venv approach follows [Raspberry Pi's Python guidance](https://www.raspberrypi.com/documentation/computers/os.html).

Expected simulation output includes GPIO18, GPIO23, 200 STEP pulses and 100.00 pulses/s. Tests run against simulated GPIO and fake camera decoding; they do not test real electrical signals.

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
