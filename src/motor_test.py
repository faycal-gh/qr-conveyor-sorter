from __future__ import annotations

import argparse

if __package__:
    from .config_loader import load_config
    from .motor_controller import build_motor_controller, validate_motor_config
else:
    from config_loader import load_config
    from motor_controller import build_motor_controller, validate_motor_config


def _menu(controller):
    while True:
        print("\n========== MOTOR TEST ==========\n"
              "1. Motor 1 forward\n2. Motor 1 reverse\n"
              "3. Motor 2 forward\n4. Motor 2 reverse\n"
              "5. Both motors forward\n6. Custom steps and speed\n"
              "7. Stop / exit\n================================")
        choice = input("Select: ").strip()
        if choice == "7":
            return
        try:
            if choice == "6":
                motor = input("Motor (1/2/both): ").strip()
                direction = input("Direction (forward/reverse): ").strip()
                steps = int(input("STEP pulses: "))
                speed = float(input("Speed (pulses/s): "))
                controller.run(motor, direction, steps, speed)
            elif choice in ("1", "2", "3", "4", "5"):
                motor, direction = {
                    "1": ("1", "forward"), "2": ("1", "reverse"),
                    "3": ("2", "forward"), "4": ("2", "reverse"),
                    "5": ("both", "forward"),
                }[choice]
                controller.run(motor, direction)
            else:
                print("Select a number from 1 to 7.")
        except ValueError as exc:
            print(f"[ERROR] {exc}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Standalone STEP/DIR motor bench test")
    parser.add_argument("--config", help="JSON configuration path")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--hardware", action="store_true", help="Explicitly select GPIO hardware mode")
    mode.add_argument("--simulate", action="store_true", help="Force simulation")
    parser.add_argument("--confirm-wiring", action="store_true", help="Confirm interface, polarity, coils and current limit checked")
    parser.add_argument("--motor", choices=("1", "2", "both"))
    parser.add_argument("--direction", choices=("forward", "reverse"), default="forward")
    parser.add_argument("--steps", type=int, help="STEP pulses, not revolutions")
    parser.add_argument("--speed", type=float, help="Pulses/s; preserves configured high width")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        validate_motor_config(config)
        # Hardware must be selected on each invocation, even if the file says false.
        config["simulation"] = not args.hardware
        controller = build_motor_controller(config, wiring_confirmed=args.confirm_wiring)
        print(f"Mode: {'SIMULATION' if controller.simulation else 'HARDWARE'}; no automatic motion.")
        if args.motor is not None or args.steps is not None or args.speed is not None or args.direction != "forward":
            controller.run(args.motor or config["motors"]["default_motor"], args.direction, args.steps, args.speed)
        else:
            _menu(controller)
    except KeyboardInterrupt:
        print("\n[STOP] Interrupted; pulses stopped and GPIO released. Holding current may remain.")
        return 130
    except EOFError:
        print("\n[STOP] Terminal closed; GPIO released.")
        return 0
    # GPIO backends have their own exception classes; report failure at the CLI boundary.
    except Exception as exc:
        print(f"[ERROR] {exc}")
        return 1
    print("[STOP] Motor test finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
