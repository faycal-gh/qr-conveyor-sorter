from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from qr_parser import parse_qr_payload


def test_simple_left():
    cmd = parse_qr_payload("direction:left")
    assert cmd is not None
    assert cmd.direction == "left"


def test_simple_right():
    cmd = parse_qr_payload("direction:right")
    assert cmd is not None
    assert cmd.direction == "right"


def test_simple_forward():
    cmd = parse_qr_payload("direction:forward")
    assert cmd is not None
    assert cmd.direction == "forward"


def test_simple_case_insensitive():
    cmd = parse_qr_payload(" Direction:RIGHT ")
    assert cmd is not None
    assert cmd.direction == "right"


def test_simple_direction_trims_whitespace_and_case():
    cmd = parse_qr_payload("  direction:  LEFT  ")
    assert cmd is not None
    assert cmd.direction == "left"


def test_json_command():
    cmd = parse_qr_payload('{"order_id":"ORD42","direction":"forward"}')
    assert cmd is not None
    assert cmd.direction == "forward"
    assert cmd.order_id == "ORD42"


def test_reject_invalid_direction():
    assert parse_qr_payload("direction:backward") is None


def test_reject_random_text():
    assert parse_qr_payload("hello") is None


def test_reject_empty_payload():
    assert parse_qr_payload("") is None
    assert parse_qr_payload("  \n ") is None


def test_reject_malformed_json():
    assert parse_qr_payload('{"direction":"left"') is None
