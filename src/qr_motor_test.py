from __future__ import annotations

import argparse
from contextlib import ExitStack

from .camera import build_camera
from .config_loader import load_config
from .motor_controller import build_motor_controller
from .qr_parser import parse_qr_payload


MOTOR_DIRECTIONS = {
    "forward": ("forward", "forward"),
    "left": ("forward", "reverse"),
    "right": ("reverse", "forward"),
}


def decode_qr(detector, frame):
    try:
        return detector.detectAndDecode(frame)
    except UnicodeDecodeError:
        # Binary QR data is unsupported, but its presence must still prevent unlocking.
        _, points = detector.detect(frame)
        return "", points, None


def scan(camera, motors, clear_frames_required):
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "QR decoding needs OpenCV: sudo apt install python3-opencv; "
            "use a venv with --system-site-packages (Windows: pip install opencv-python)."
        ) from exc
    detector = cv2.QRCodeDetector()
    locked = False
    empty_frames = 0
    last_payload = None
    while True:
        frame = camera.read()
        payload, points, _ = decode_qr(detector, frame)
        if points is None and not payload:
            last_payload = None
            if locked:
                empty_frames += 1
                if empty_frames >= clear_frames_required:
                    locked = False
                    print("[STATE] QR cleared. Ready for the next command.", flush=True)
            continue
        empty_frames = 0
        if payload != last_payload:
            print(f"[QR] QR code detected\n[QR] Payload: {payload!r}", flush=True)
            last_payload = payload
        command = parse_qr_payload(payload)
        if command is None:
            continue
        if locked:
            continue
        directions = MOTOR_DIRECTIONS[command.direction]
        print(f"[COMMAND] {command.direction.upper()}\n"
              f"[MOTOR 1] {directions[0].upper()}\n[MOTOR 2] {directions[1].upper()}", flush=True)
        locked = True
        print("[EXECUTION] Starting motor command", flush=True)
        # Blocking execution prevents overlap and counts clearing frames only after movement.
        motors.run_two(*directions)
        print("[EXECUTION] Completed. Remove every QR from view to unlock.", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Headless live QR scanning with two STEP/DIR motors")
    parser.add_argument("--config", help="JSON configuration path (default: config.json)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--simulate", action="store_true", help="Real camera, simulated motors (default)")
    mode.add_argument("--hardware", action="store_true", help="Explicitly enable physical motor pulses")
    parser.add_argument("--confirm-wiring", action="store_true", help="Confirm both driver interfaces and current limits")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        config["simulation"] = not args.hardware
        motors = build_motor_controller(config, wiring_confirmed=args.confirm_wiring)
        if args.hardware:
            for name in ("motor1", "motor2"):
                if not config["motors"]["enabled"][name]:
                    raise ValueError(f"{name} is disabled; QR hardware movement requires both motors enabled")
        clear_frames = config.get("qr", {}).get("clear_frames_required", 8)
        if type(clear_frames) is not int or clear_frames < 1:
            raise ValueError("qr.clear_frames_required must be a positive integer")
        print(f"Mode: {'SIMULATION' if motors.simulation else 'HARDWARE'}; Ctrl+C stops scanning.", flush=True)
        with ExitStack() as cleanup:
            camera = build_camera(config)
            cleanup.callback(camera.close)
            print("[CAMERA] Camera initialized", flush=True)
            scan(camera, motors, clear_frames)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted; camera closed and GPIO released. Holding current may remain.", flush=True)
        return 130
    except Exception as exc:
        print(f"[ERROR] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
