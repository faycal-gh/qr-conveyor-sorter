"""Local settings and persistent operator consent for the existing QR scanner."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

from .camera import validate_camera_url
from .config_loader import load_config
from .motor_controller import validate_motor_config
from .qr_motor_test import main as scan_main

LOCAL_CONFIG = Path(__file__).resolve().parents[1] / "config.local.json"
CONFIRMATION = "I CONFIRM BOTH MOTORS ARE SAFE"


def motor_fingerprint(config):
    encoded = json.dumps(
        config["motors"], sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def hardware_confirmed(config):
    acknowledgment = config.get("hardware_confirmation")
    return (
        isinstance(acknowledgment, dict)
        and acknowledgment.get("version") == 1
        and acknowledgment.get("motors_sha256") == motor_fingerprint(config)
        and all(
            config["motors"]["enabled"][name] is True for name in ("motor1", "motor2")
        )
    )


def settings():
    if LOCAL_CONFIG.exists():
        return load_config(LOCAL_CONFIG)
    config = load_config()
    config["simulation"] = True
    config["camera"]["backend"] = "ipwebcam"
    config["camera"]["url"] = ""
    return config


def save_settings(config):
    validate_motor_config(config)
    descriptor, name = tempfile.mkstemp(
        dir=LOCAL_CONFIG.parent, prefix=".qr-settings-", suffix=".tmp"
    )
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, LOCAL_CONFIG)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"[CONFIG] Saved {LOCAL_CONFIG.name}", flush=True)


def configure_url(config):
    current = config["camera"].get("url", "")
    entered = input(
        f"Enter Android IP Webcam URL [{current or 'not configured'}]: "
    ).strip()
    config["camera"]["url"] = validate_camera_url(entered or current)
    config["camera"]["backend"] = "ipwebcam"


def update_camera(config, args):
    if args.revoke_hardware:
        return
    if args.camera_url is not None:
        config["camera"]["url"] = validate_camera_url(args.camera_url)
        config["camera"]["backend"] = "ipwebcam"
    elif args.configure or (
        config["camera"]["backend"] == "ipwebcam" and not config["camera"].get("url")
    ):
        configure_url(config)
    if config["camera"]["backend"] == "ipwebcam":
        validate_camera_url(config["camera"].get("url"))


def enable_hardware(config):
    motors = config["motors"]
    print("[SAFETY] Confirm BOTH motors, including the separately checked Motor 2:")
    print(
        "  Both drivers wired correctly; coil pairs, current limits and microsteps checked."
    )
    print(
        "  ULN2803 signal interface and polarity checked; external power supply connected safely."
    )
    print(
        "  Both motors can rotate without obstruction; physical power disconnect accessible."
    )
    print(json.dumps(motors, indent=2))
    print(
        "Ctrl+C stops STEP generation; it does not necessarily remove holding current."
    )
    if input(f"Type exactly {CONFIRMATION}: ").strip() != CONFIRMATION:
        raise ValueError("Hardware confirmation declined; no hardware settings saved")
    motors["enabled"]["motor1"] = True
    motors["enabled"]["motor2"] = True
    config["simulation"] = False
    config["hardware_confirmation"] = {
        "version": 1,
        "motors_sha256": motor_fingerprint(config),
    }


def tune_motors(config, args):
    motors = config["motors"]
    previous = motor_fingerprint(config)
    if args.steps is not None:
        motors["default_steps"] = args.steps
    if args.speed is not None:
        if not math.isfinite(args.speed) or args.speed <= 0:
            raise ValueError("Speed must be finite and positive (pulses/s)")
        motors["pulse_low_seconds"] = 1 / args.speed - motors["pulse_high_seconds"]
    for name in ("motor1", "motor2"):
        invert = getattr(args, "invert_" + name)
        if invert is not None:
            motors["invert_direction"][name] = invert
    validate_motor_config(config)
    if previous != motor_fingerprint(config):
        config["simulation"] = True
        config.pop("hardware_confirmation", None)
        print(
            "[SAFETY] Motor settings changed. Simulation selected; re-enable hardware after checking."
        )


def arguments(argv):
    parser = argparse.ArgumentParser(
        description="One-command dual-motor QR scanner with saved local settings"
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--configure",
        action="store_true",
        help="Prompt for the Android stream URL, save and exit",
    )
    action.add_argument(
        "--show-config",
        action="store_true",
        help="Show effective settings without starting the camera",
    )
    action.add_argument(
        "--enable-hardware",
        action="store_true",
        help="Confirm BOTH motors once, save hardware mode and exit",
    )
    action.add_argument(
        "--revoke-hardware",
        action="store_true",
        help="Clear confirmation, disable Motor 2 and save simulation",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--simulate",
        action="store_true",
        help="Run with the real camera and no GPIO; keep saved mode",
    )
    mode.add_argument(
        "--hardware",
        action="store_true",
        help="Run hardware only with valid saved confirmation",
    )
    parser.add_argument(
        "--camera-url", help="Validate and save a new Android stream URL, then exit"
    )
    parser.add_argument(
        "--steps", type=int, help="Save pulse count per motor, then exit"
    )
    parser.add_argument(
        "--speed",
        type=float,
        help="Save nominal pulses/s, preserving active pulse duration, then exit",
    )
    for name in ("motor1", "motor2"):
        parser.add_argument(
            "--invert-" + name,
            action=argparse.BooleanOptionalAction,
            default=None,
            help=f"Save {name} direction inversion, then exit",
        )
    return parser.parse_args(argv)


def main(argv=None):
    args = arguments(argv)
    try:
        config = settings()
        validate_motor_config(config)
        editing = any(
            (
                args.configure,
                args.enable_hardware,
                args.revoke_hardware,
                args.camera_url is not None,
                args.steps is not None,
                args.speed is not None,
                args.invert_motor1 is not None,
                args.invert_motor2 is not None,
            )
        )
        if editing and (args.simulate or args.hardware):
            raise ValueError(
                "Save settings first, then start a separate scanner invocation"
            )
        if args.show_config:
            print(json.dumps(config, indent=2))
            print(f"[SAFETY] Hardware confirmation valid: {hardware_confirmed(config)}")
            return 0
        tune_motors(config, args)
        update_camera(config, args)
        if args.enable_hardware:
            enable_hardware(config)
        elif args.revoke_hardware:
            config["simulation"] = True
            config["motors"]["enabled"]["motor2"] = False
            config["motors"]["default_motor"] = "1"
            config.pop("hardware_confirmation", None)
        if editing or not LOCAL_CONFIG.exists():
            save_settings(config)
        if editing:
            print("[CONFIG] No camera or GPIO started. Run ./run_qr.sh when ready.")
            return 0
        hardware = args.hardware or (not args.simulate and not config["simulation"])
        if hardware and not hardware_confirmed(config):
            raise ValueError(
                "Hardware is not confirmed for these motor settings. Run ./run_qr.sh --enable-hardware"
            )
        options = ["--config", str(LOCAL_CONFIG)]
        options += ["--hardware", "--confirm-wiring"] if hardware else ["--simulate"]
        print(
            f"[CAMERA] Using {config['camera']['backend']}; camera loss stops the session, with manual restart.",
            flush=True,
        )
        return scan_main(options)
    except KeyboardInterrupt:
        print("\n[STOP] Configuration interrupted; no new confirmation saved.")
        return 130
    except EOFError:
        print(
            "[ERROR] Camera URL/confirmation needs a terminal. Run ./run_qr.sh --configure interactively."
        )
        return 1
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"[ERROR] {exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
