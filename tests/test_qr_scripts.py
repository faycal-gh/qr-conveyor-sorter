import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BASH = (
    shutil.which("bash")
    if not (Path("C:/Program Files/Git/bin/bash.exe").exists())
    else "C:/Program Files/Git/bin/bash.exe"
)


@pytest.mark.parametrize("name", ["setup_pi.sh", "run_qr.sh"])
def test_pi_scripts_have_lf_shebang_and_valid_syntax(name):
    path = ROOT / name
    assert path.exists(), f"{name} launcher is missing"
    assert b"\r" not in path.read_bytes()
    assert path.read_bytes().startswith(b"#!/bin/bash\n")
    if BASH:
        subprocess.run([BASH, "-n", str(path)], check=True, capture_output=True)


def test_run_launcher_works_outside_checkout_and_preserves_arguments(tmp_path):
    path = ROOT / "run_qr.sh"
    assert path.exists(), "Launcher is missing"
    if not BASH:
        pytest.skip("Bash is unavailable")
    checkout = tmp_path / "checkout with spaces"
    checkout.mkdir()
    shutil.copyfile(path, checkout / path.name)
    binaries = checkout / ".venv" / "bin"
    binaries.mkdir(parents=True)
    python = binaries / "python"
    python.write_text(
        '#!/bin/bash\nprintf "%s\\n" "$PWD" "$@"\n', encoding="utf-8", newline="\n"
    )
    python.chmod(0o755)
    environment = os.environ.copy()
    if os.name == "nt":
        # Mock the Linux OS lock boundary; the real flock is exercised on Linux separately.
        (binaries / "flock").write_text(
            "#!/bin/bash\nexit 0\n", encoding="utf-8", newline="\n"
        )
        environment["PATH"] = str(binaries) + os.pathsep + environment["PATH"]
    completed = subprocess.run(
        [
            BASH,
            str(checkout / path.name),
            "--camera-url",
            "http://phone.local:8080/video",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    lines = completed.stdout.splitlines()
    assert lines[-5:] == [
        "-u",
        "-m",
        "src.qr_launcher",
        "--camera-url",
        "http://phone.local:8080/video",
    ]
    assert lines[0].endswith("/checkout with spaces")


def test_repeat_setup_skips_installed_packages_and_preserves_local_settings(tmp_path):
    if not BASH or (os.name != "nt" and os.geteuid() == 0):
        pytest.skip("Setup is a normal-user Bash workflow")
    checkout = tmp_path / "existing checkout"
    binaries = checkout / ".venv" / "bin"
    binaries.mkdir(parents=True)
    shutil.copyfile(ROOT / "setup_pi.sh", checkout / "setup_pi.sh")
    (checkout / ".venv" / "pyvenv.cfg").write_text(
        "include-system-site-packages = true\n", newline="\n"
    )
    settings = checkout / "config.local.json"
    settings.write_text('{"simulation": true}\n', newline="\n")
    previous = settings.read_bytes()
    scripts = {
        "dpkg-query": '#!/bin/bash\necho "install ok installed"\n',
        "sudo": '#!/bin/bash\necho "Unexpected OS mutation" >&2\nexit 99\n',
        "python3": '#!/bin/bash\necho "Unexpected venv recreation" >&2\nexit 99\n',
        "python": "#!/bin/bash\nexit 0\n",
    }
    for name, content in scripts.items():
        path = binaries / name
        path.write_text(content, newline="\n")
        path.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
    }
    for _ in range(2):
        completed = subprocess.run(
            [BASH, str(checkout / "setup_pi.sh")],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert "skipping apt" in completed.stdout
    assert settings.read_bytes() == previous
