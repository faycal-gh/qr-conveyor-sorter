# QR motor scanning implementation plan

**Goal:** Scan real CSI/USB camera frames over SSH and execute one differential two-motor command per QR presentation, with simulation by default.

**Architecture:** Reuse camera acquisition, payload parsing, motor validation and the existing shared STEP loop. Add independent directions to the controller and a blocking headless scanner; movement must finish before further frames are read. Keep the bench menu and legacy sorter entry points.

**Scope:** `src/camera.py`, `src/motor_controller.py`, new `src/qr_motor_test.py`, `config.json`, QR generator and committed PNGs, dependency files, README and Pi setup, new hardware-independent tests. Preserve disabled Motor 2 in the bench defaults. Hardware QR commands require both motors enabled before camera startup or GPIO acquisition.

1. Add failing tests for differential direction levels, synchronized pulse events, disabled-motor rejection and interruption cleanup. Extend the shared execution loop and run old/new motor tests.
2. Add failing tests using real QR image frames for parsing, mapping, lockout/reset, simulation, hardware gates and camera failures. Implement the scanner and harden camera lifecycle handling. Run scanner/camera tests.
3. Test generation and exact decoding of the three required PNGs. Update the generator, remove the image ignore rule, generate and decode repository assets.
4. Update existing usage/setup docs and dependencies. Verify CLI help and documented settings against source and official Pi camera guidance.
5. Run the complete suite and compilation. Review code, tests, docs and generated assets; explicitly stage the feature, commit and push the current branch without force.

**Validation:** `.venv/Scripts/python.exe -m pytest -q`; `.venv/Scripts/python.exe -m compileall -q src tools tests`; `.venv/Scripts/python.exe tools/generate_test_qr.py`. Physical camera, driver signals and movement still need Raspberry Pi verification.
