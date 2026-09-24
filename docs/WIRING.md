# Wiring Plan

## Raspberry Pi 5 GPIO assignment

| Function | BCM GPIO |
|---|---:|
| Motor 1 STEP / TB6600 PUL | GPIO18 |
| Motor 1 DIR / TB6600 DIR | GPIO23 |
| Motor 2 STEP / TB6600 PUL | GPIO24 |
| Motor 2 DIR / TB6600 DIR | GPIO25 |

The camera connects to a Raspberry Pi CSI camera connector using the correct ribbon cable.

## Power separation

- Raspberry Pi 5: dedicated USB-C 5 V / 5 A supply.
- NEMA 17 motors: separate DC motor power supply through the TB6600 drivers.
- Never power the NEMA 17 motors from Raspberry Pi GPIO or its 5 V rail.

## TB6600 input warning

TB6600-style drivers are sold in several electrical variants. Do not assume the Raspberry Pi 3.3 V GPIO can be connected directly to `PUL`, `DIR`, or `ENA` on every board.

Before final wiring, check the exact TB6600 model/label/manual and use a suitable 3.3 V-compatible interface if its opto-isolated inputs require it.

## NEMA 17 coils

A 4-wire stepper has two coils:

- one coil -> `A+` / `A-`
- the other coil -> `B+` / `B-`

Do not rely only on wire colors; identify each coil pair using the motor documentation or a multimeter continuity/resistance check.

## Mechanical note

The code currently drives two motors as a differential pair. A conventional four-wheel mecanum platform requires four independently driven motors for true lateral strafing.
