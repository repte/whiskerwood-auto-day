# Auto Day v0.1.0

First Windows release. Auto Day confirms Whiskerwood's regular end-of-day prompt
using the game's normal NextDay action. Its native mod setting is enabled by
default, with English and German labels and English fallback.

## Installation

Download `AutoDay-v0.1.0.zip`, close the game, and extract its `AutoDay` folder
into `%LOCALAPPDATA%\Whiskerwood\Saved\mods\`. Use one installation only; remove
any Workshop copy before installing locally.

## Behavior and Limits

- Checks about once per second and waits while a window is open, the HUD is not
  ready, or the game reports saving or pending victory.
- Makes one attempt per calendar day per load, with no automatic retries.
  Manual confirmation remains available.
- Leaves normal daytime pauses alone. At the end-of-day stop, the normal NextDay
  action may also clear an overlapping manual pause.
