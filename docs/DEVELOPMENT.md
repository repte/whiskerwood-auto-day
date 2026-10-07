# Auto Day Development

Standalone Whiskerwood mod, version `0.1.0-preview`. The native mod setting is
**enabled by default**. English and German labels are provided, with English as
the fallback for other game languages.

## Runtime

Two loader Blueprints use the game's native functions, with no external runtime
or native DLL. `BP_MainMenuLoad` registers the setting; `BP_MapLoad` checks native
HUD and initialization state and calls `HandleHudAction("startNewDay")`. A
real-time gate runs during the end-of-day pause and checks about once per second.
It waits while a view is open, the HUD is not ready, or the game reports saving
or pending victory. It makes one request per calendar day and loaded session,
with no automatic retries. Loading resets its attempt state.

Runtime assets live under `/Game/Mods/AutoDay`. `PAL_AutoDay` is an editor-only
label that assigns the assets to an isolated cook chunk.

Normal manual pauses during the day are unaffected. At the end-of-day stop,
Auto Day uses the game's normal NextDay action. This may also clear a manual
pause that coincides with the end-of-day stop. The public API does not expose
those two pause reasons separately. The manual next-day control stays available.

## Build

Copy this repository's `Content/Mods/AutoDay` and `Automation/AutoDay` into the
corresponding directories of a compatible Whiskerwood modkit before building.
The custom Whiskerwood engine is required. Run these commands from the repository
root; the example assumes the modkit is the sibling `Modkit` directory:

```powershell
& 'D:\WWEngine\Engine\Binaries\Win64\UnrealEditor-Cmd.exe' '..\Modkit\Whiskerwood.uproject' "-ExecutePythonScript=$PWD\Automation\AutoDay\generate_mod.py" -unattended -nullrhi -nosound
& .\Automation\AutoDay\Build-Mod.ps1 -EngineRoot 'D:\WWEngine' -ProjectRoot '..\Modkit'
```

`EngineRoot` and `ProjectRoot` can point to other locations. The build prepares
and validates Auto Day's chunk, runs only Auto Day's tests, cooks the modkit, and
lists and verifies the resulting pak once. A reported error in the editor, cook,
or pak logs fails verification even when the process exits with code 0. The
assigned chunk is read from `Saved/AutoDay-PackageSetup.json`.

Each build has a separate output directory under the modkit:

```text
Saved/AutoDayBuilds/<build-id>/
  Delivery/AutoDay/AutoDay.pak
  Delivery/AutoDay/AutoDay.uplugin
  package-verification.json
  Logs/
```

Only the two files in `Delivery/AutoDay` are the mod package. Package validation
accepts the two Auto Day entry assets and their cooked sidecar files. The
editor-only label, scripts, other mods, and unrelated files are rejected. The
build stages the package only; it does not install or publish it.

To inspect an existing cooked package:

```powershell
& .\Automation\AutoDay\Test-Package.ps1 -PakPath '<path-to-AutoDay.pak>' -EngineRoot 'D:\WWEngine' -ProjectRoot '..\Modkit'
```

## Local Installation

Close Whiskerwood, then pass the exact `Delivery/AutoDay` directory to the local
installer. It rejects a running game, existing local Auto Day packages, extra
delivery files, and invalid pak contents. It copies only the verified pak and
descriptor into `%LOCALAPPDATA%/Whiskerwood/Saved/mods/AutoDay` and does not start
the game. Remove any separate Workshop copy before using a local copy.

```powershell
& .\Automation\AutoDay\Install-Local.ps1 -PackageDirectory '<build>/Delivery/AutoDay' -EngineRoot 'D:\WWEngine' -ProjectRoot '..\Modkit'
```

Auto Day is enabled by default. The native mod settings switch can disable it.

## Manual Validation

The automated checks exercise the compiled actor with native HUD fixtures, not
the full running game. In-game validation is pending and is performed by the user.

1. Confirm the setting appears once and starts on for a fresh setting.
2. With no window open, let the day end. The next day should start within about a second.
3. Pause during the day, then test an open window at the end of the day: neither should be bypassed.
4. Test a manual pause coinciding with the end-of-day stop; confirm the documented NextDay behavior.
5. Disable Auto Day and reload a save: manual day confirmation must remain usable.

The shipped game's HUD timing and view behavior still require this gameplay test.

## Publication Preparation

The source repository is `repte/whiskerwood-auto-day`. Workshop text and change notes are
drafted under `workshop/`; the same unchanged image is used for the README and
the prepared Workshop preview. No existing mod's Workshop item ID is reused.

Source code is provided under the MIT license. Whiskerwood and third-party game
assets remain the property of their respective owners.
