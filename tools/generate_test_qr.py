from pathlib import Path


OUTPUT = Path(__file__).resolve().parents[1] / "test_qr_codes"


def generate(output=OUTPUT):
    import cv2
    import qrcode

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for direction in ("forward", "left", "right"):
        payload = f"direction: {direction}"
        code = qrcode.QRCode(box_size=16, border=4)
        code.add_data(payload)
        code.make(fit=True)
        path = output / f"qr_{direction}.png"
        code.make_image(fill_color="black", back_color="white").save(path)
        decoded, _, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(str(path)))
        if decoded != payload:
            raise RuntimeError(f"Generated QR failed decode verification: {path}")
        print(f"Created and verified {path} -> {decoded}")


if __name__ == "__main__":
    generate()
