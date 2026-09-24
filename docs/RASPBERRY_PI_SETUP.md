# Raspberry Pi 5 Setup

These steps are for later, when the Raspberry Pi 5 and camera are available.

## 1. Raspberry Pi OS

Use a current 64-bit Raspberry Pi OS installation.

## 2. Install camera/GPIO packages

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-opencv python3-gpiozero python3-venv git
```

Test the camera first:

```bash
rpicam-hello -t 5000
```

## 3. Clone the repository

```bash
git clone https://github.com/faycal-gh/qr-conveyor-sorter.git
cd qr-conveyor-sorter
```

## 4. Change configuration

Edit `config.json`:

```json
"simulation": false,
"camera": {
  "backend": "picamera2",
  "index": 0,
  "width": 1280,
  "height": 720,
  "show_preview": true
}
```

## 5. Confirm motor settings before connecting the mechanics

The default step counts (`500`) and pulse delay (`0.001`) are placeholders for bench testing. They must be calibrated for:

- your exact NEMA 17 step angle
- TB6600 microstep setting
- wheel/roller diameter
- gearbox, if any
- required parcel displacement

Start testing with the mechanism unloaded and at low speed.

## 6. Run

```bash
python3 src/main.py
```

The program scans continuously. A valid QR immediately executes one motor movement, then locks until that QR leaves the camera view.
