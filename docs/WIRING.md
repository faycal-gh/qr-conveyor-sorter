# Motor test wiring and electrical safety

Hardware mode is intentionally opt-in. The bench tester/direct scanner require `--hardware --confirm-wiring` each time. The one-command QR launcher instead requires `./run_qr.sh --enable-hardware` and an explicit phrase confirming both motors, then persists that consent for the checked motor settings. Revoke with `./run_qr.sh --revoke-hardware`. Software cannot inspect wiring. Configure everything with driver power off before the first test.

## GPIO assignments

All code pin numbers are **BCM GPIO**, not physical header numbers.

Use the [official Raspberry Pi GPIO reference](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#gpio-and-the-40-pin-header) and `pinout` on the Pi to check header orientation and 3.3 V logic levels.

| Signal | BCM GPIO | Physical 40-pin header pin |
|---|---:|---:|
| Motor 1 STEP / PUL interface | 18 | 12 |
| Motor 1 DIR interface | 23 | 16 |
| Motor 2 STEP / PUL interface | 24 | 18 |
| Motor 2 DIR interface | 25 | 22 |
| Pi-side ground, if required by interface | GND | 6 (one possible GND pin) |

Motor 2 is disabled by default. Motor 1 bench testing does not allocate Motor 2 GPIO or require its driver/motor. The QR scanner uses a camera and requires both motors enabled for hardware movement; simulation previews both without GPIO. No ENA pin or physical presence sensor is used.

## Installed ULN2803 signal interface

The project uses a ULN2803 between the Pi GPIO outputs and the two STEP/DIR microstep drivers. Its open-collector outputs sink signal current and invert the output voltage relative to the Pi-side input. The TB6600-style drivers, not the ULN2803, supply the motor winding currents from the external 24 V supply. Do not connect motor windings directly to this signal-interface module.

Motor 1 has been tested by the operator with the existing GPIO18/GPIO23 configuration. This change preserves it: `pulse_active_high=true`, 5 ms active/inactive pulse timing and the existing direction inversion defaults. A low ULN2803 collector can activate a driver's optocoupler in an appropriate common-anode interface, so its voltage inversion is not a reason to blindly flip GPIO pulse polarity. Check the actual signal path and driver input requirements before changing anything.

Motor 2 retains GPIO24/GPIO25, with its own ULN2803 channels and separate microstep driver. The repository does not establish module channel numbers, exact wiring, current DIP settings or physical rotation direction. Verify those independently before confirming hardware. Use `./run_qr.sh --invert-motor1` or `--invert-motor2` to reverse a logical mapping without rewiring; this invalidates launcher consent until you check and confirm the new motor settings.

## Power

- Pi 5: separate 27 W USB-C supply.
- Drivers: separate Weidmuller 24 V / 10 A supply, connected to each driver's documented DC power terminals. Verify each actual driver's input range and power-terminal polarity against its label/manual.
- **Never connect 12 V, 24 V, 5 V signal power, or driver motor terminals to a Pi GPIO. GPIO is 3.3 V and is not a motor power output.**
- Protect and fuse driver branches for the wiring and equipment used. Keep mains terminals enclosed and use appropriate earthing for the supply's documented requirements. Have mains work checked by a qualified person if needed.
- Never connect/disconnect motor coils or change DIP switches while energized. Switch off the motor supply and wait for its documented discharge time first.

The Pi's and driver's supplies are separate. Ground connections depend on the signal interface topology; a shared ground is not a universal requirement for a truly isolated interface.

## STEP/DIR interface: verify the actual driver

TB6600-style modules vary. A 9-42 V power-input label does **not** specify the PUL/DIR/ENA signal voltage, current or polarity. No exact manual was supplied for this driver, so these are interface options, not a verified schematic for your board.

Read the exact label/manual to establish signal supply voltage, optocoupler input current, any internal resistor, allowed common-anode/common-cathode wiring, active pulse edge, DIR polarity, minimum pulse widths, DIR setup/hold, and ENA behavior. Do not assume direct 3.3 V GPIO compatibility. Select and verify an appropriate interface before hardware testing.

Possible stages:

- **Transistor current sink**, if the manual permits common-anode inputs: use one suitably rated NPN transistor or logic-level MOSFET channel per STEP/DIR signal. GPIO drives the transistor through an appropriately sized base/gate network; an external resistor biases it off when GPIO floats. The transistor sinks the driver's negative signal terminal and the positive terminal uses the manual's required signal supply. Size current limiting from the specified input current and existing internal resistance. The Pi connects only to the low-voltage control side. For this non-isolated stage, connect Pi ground to the transistor emitter/source and the signal supply return as the designed circuit requires; do not assume that means connecting to motor-power negative.
- **Optocoupler/isolated interface**, designed for 3.3 V logic: GPIO drives only the Pi-side LED circuit with suitable current limiting. The isolated output side uses its specified supply and the driver's specified input arrangement. Verify bandwidth, propagation delay and output current. Preserve isolation rather than bridging the two grounds.

Do not directly source a driver's required optocoupler current from GPIO unless its specification and the Pi limits explicitly permit it. A generic bidirectional logic-level board is not automatically an appropriate optocoupler driver. Choose component values and wiring from the exact electrical specifications, rather than guessing a resistor or signal supply.

Check polarity across the **whole** interface: a transistor may invert voltage while making the driver's optocoupler active. `motors.pulse_active_high=true` means GPIO idle LOW and HIGH pulses; false means GPIO idle HIGH and LOW pulses. Select the setting that leaves the verified driver STEP input inactive at idle and creates one counted driver edge per cycle. `invert_direction` compensates for the interface/coil mapping of each DIR signal. Forward does not guarantee clockwise from any particular viewing side.

## Coil pairs and current limit

For the 4-wire NEMA 17 42HS48-1684AC:

1. Turn off driver power, wait for discharge, and disconnect all four motor wires from the driver.
2. Use a multimeter on resistance/continuity. Two wires with a finite low resistance form one winding. The other two form the second winding. There should be no continuity between windings; do not rely on wire colors.
3. Connect the first pair to `A+ / A-` and the second to `B+ / B-` according to the driver's terminal labels. A different coil-end orientation can reverse rotation; compensate with per-motor direction inversion after verifying the pairing.
4. **Set the driver current limit before energizing the motor.** Obtain the exact motor's per-phase rating and the driver's current DIP table, including whether values are peak or RMS. Choose a limit appropriate for that rating and cooling; do not derive the limit from the 24 V / 10 A supply capacity. Monitor driver/motor temperature during short unloaded tests.
5. Set and record microstepping using the driver's own DIP table. Pulses/revolution depend on full-step angle and subdivision, as explained in the [README](../README.md#configuration).

## Timing and stopped state

Defaults are 5 ms STEP active, 5 ms inactive (nominal 100 pulses/s), and 10 ms DIR setup/hold. Verify that these exceed your driver's specified minima, accounting for interface delays. Software timing has jitter; this is for slow unloaded bench tests.

Before pulses, DIR is set and held for the configured setup delay. STEP outputs start inactive. After the last pulse or interruption, STEP is made inactive, DIR is held for the configured delay, then DIR is reset to GPIO LOW and allocated devices and the lgpio factory are closed. On active-low STEP, inactive means GPIO HIGH. On errors during initialization, any successfully allocated outputs are reset and released.

**Released pins are inputs and may float; software does not maintain their voltage after close, during boot, or after a crash.** Provide external bias at the interface so floating/released GPIO keeps STEP inactive (pull down for GPIO-active-high STEP, pull up to Pi-side 3.3 V for GPIO-active-low STEP). Check startup, shutdown and polarity with driver power off first. GPIO LOW on DIR has no universal mechanical meaning. Remove driver power before powering down the Pi or modifying wiring.

Ctrl+C stops software pulses and releases resources, but does **not** disable the driver or remove motor holding current. ENA is not wired or controlled by this application; verify its idle behavior and use the driver's documented disable circuit or safely disconnect driver power when required. Have an accessible hardware power disconnect; SSH and Ctrl+C are not safety-rated emergency stops. No cleanup is guaranteed after SIGKILL, power loss or GPIO faults.
