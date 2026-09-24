from __future__ import annotations

from contextlib import ExitStack

import cv2

from camera import build_camera
from config_loader import load_config
from motor_controller import build_motor_controller
from qr_parser import parse_qr_payload


def main() -> None:
    config = load_config()
    show_preview = bool(config["camera"].get("show_preview", True))
    clear_frames_required = int(config["qr"].get("clear_frames_required", 8))

    with ExitStack() as cleanup:
        camera = build_camera(config)
        cleanup.callback(camera.close)
        motors = build_motor_controller(config)
        cleanup.callback(motors.close)
        detector = cv2.QRCodeDetector()

        qr_locked = False
        empty_frame_count = 0
        last_payload = None

        conveyor = config.get("conveyor", {})
        length = float(conveyor.get("length_m", 0.8))
        speed = float(conveyor.get("speed_mps", 0.141))
        travel_time = length / speed if speed > 0 else 0.0

        print("=" * 62)
        print("QR CONVEYOR SORTER")
        print(f"Mode: {'SIMULATION' if config.get('simulation', True) else 'RASPBERRY PI GPIO'}")
        print(f"Conveyor: {length:.2f} m @ {speed:.3f} m/s (~{travel_time:.2f} s full length)")
        print("Valid commands: direction:left | direction:right | direction:forward")
        print("No IR sensor: motor command starts immediately after a valid QR scan.")
        print("Press Q in the preview window to quit.")
        print("=" * 62)

        try:
            while True:
                frame = camera.read()
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                payload, points, _ = detector.detectAndDecode(gray)
                qr_visible = points is not None or bool(payload)

                if qr_visible:
                    empty_frame_count = 0
                    if not payload:
                        if last_payload != "":
                            print("[QR] Ignored empty or undecodable QR payload.")
                        last_payload = ""
                    else:
                        command = parse_qr_payload(payload)
                        if command is not None:
                            if not qr_locked:
                                print(
                                    f"[QR] payload={command.raw_payload!r} "
                                    f"direction={command.direction.upper()}"
                                )
                                if command.order_id:
                                    print(f"[QR] order_id={command.order_id}")

                                motors.execute(command.direction)

                                last_payload = command.raw_payload
                                qr_locked = True
                                print("[STATE] Executed once. Waiting for QR to leave the camera view...")
                        elif payload != last_payload:
                            print(f"[QR] Ignored unsupported payload: {payload!r}")
                            last_payload = payload

                    if points is not None and show_preview:
                        pts = points.astype(int).reshape(-1, 2)
                        for i in range(len(pts)):
                            p1 = tuple(pts[i])
                            p2 = tuple(pts[(i + 1) % len(pts)])
                            cv2.line(frame, p1, p2, (255, 255, 255), 2)
                else:
                    last_payload = None
                    if qr_locked:
                        empty_frame_count += 1
                        if empty_frame_count >= clear_frames_required:
                            qr_locked = False
                            empty_frame_count = 0
                            print("[STATE] QR cleared. Ready for the next parcel.")

                if show_preview:
                    cv2.imshow("QR Conveyor Sorter - press Q to quit", frame)
                    if (cv2.waitKey(1) & 0xFF) == ord("q"):
                        break

        except KeyboardInterrupt:
            pass
        finally:
            cv2.destroyAllWindows()

    print("Sorter stopped safely.")


if __name__ == "__main__":
    main()
