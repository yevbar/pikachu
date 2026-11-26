# Switch 2 bot setup: findings (2026-10-16)

Notes from getting an Asahi Linux Mac mini to watch and control a Nintendo Switch 2 running Mario Kart World, as groundwork for an autonomous bot.

## Hardware and software

| Part | Detail |
|---|---|
| Host | Mac mini, Asahi Linux (Fedora 42, aarch64), 8 cores, 7.4 GB RAM (about 2 GB free in use), no usable ML accelerator |
| Video in | MacroSilicon USB3.0 Video capture card (`345f:2131`) at `/dev/video0` |
| Control out | nxbt 0.1.4 emulating a Pro Controller over the Mac's built-in Bluetooth |
| Python | 3.13, venv at `.venv` with `--system-site-packages` |

## Results

### Video capture

- The card offers YUYV and MJPEG at up to 2560x1600. At 1920x1080 and 1280x720 it runs at 60 fps in MJPEG.
- **Starting ffmpeg for every frame:** about 1–2 s per frame. Not usable for a bot.
- **OpenCV with its built-in decoding:** 20 fps at 1080p, and it crashed on the occasional empty frame the card sends.
- **OpenCV giving raw JPEG bytes, decoded on demand (what `pikachu.FrameGrabber` does):** **60 fps** with no frames dropped.

JPEG decode time per frame:

| Source | Full size | 1/2 | 1/4 |
|---|---|---|---|
| 1920x1080 | 6.5 ms | 2.8 ms (960x540) | 2.4 ms (480x270) |
| 1280x720 | 4.8 ms | 1.2 ms (640x360) | 1.0 ms (320x180) |

### Policy loop

- `pikachu.run()` runs at **~60 Hz**, one decision per frame.
- About **9 ms** from the card delivering a frame to the input being sent to the bridge, at scale 2 (960x540) with a do-nothing policy.

### Button press to screen change

Measured with `examples/latency.py 30`. It moves the cursor up and down in System → Controllers and times each press to the first frame where the highlight has moved.

- **Median 148 ms**, min 132, max 186, with all 30 presses detected.
- All times in ms: 133, 148, 149, 165, 183, 136, 148, 133, 132, 132, 132, 148, 165, 136, 165, 136, 148, 186, 170, 135, 132, 148, 167, 186, 153, 165, 132, 165, 148, 135.
- Our code is under 10 ms of that. The rest is Bluetooth, the Switch registering the input and drawing it, and the capture card's own delay. This setup can't split those apart.
- A first try with `press_test.py` on the Change Grip/Order screen measured 517 ms, but that includes the menu-closing animation, so it isn't a true delay.
- **Detection threshold:** the Switch's animated highlight border changes up to 0.46% of pixels with no press at all, while a cursor move changes about 1.1%. The detector counts a press when more than 0.6% of pixels change by more than 40 (at 480x270).

What this means for a bot: about 150 ms is roughly 9 frames at 60 fps. Steering has to anticipate a little. Recorded human play should shift inputs by about 150 ms so each frame lines up with the input that produced it. Re-measure during an actual race, because gameplay may add a frame or two compared with a menu.

### Controller emulation

- **The Switch 2 accepts nxbt's emulated Pro Controller.** It paired from Change Grip/Order and took player slot 1, and A, B, HOME and the D-pad all worked.
- nxbt's direct-input mode (`set_controller_input`) holds whatever state it's given and resends it about 132 times a second until it changes. That makes analogue steering possible, which button-press macros can't do.

### OCR

- After `sudo dnf install tesseract`, Tesseract 5.5.0 is available.
- On a whole 1080p title-screen frame it read the prompt as "Press + (3 to:start". It misreads the L and R button icons and also returns noise from the scenery. It works better on cropped, cleaned-up regions of the screen.
- With no ML accelerator, OCR runs on the CPU. RapidOCR (onnxruntime) is a candidate if Tesseract struggles with game fonts.

## Problems hit and fixes

| Problem | Fix |
|---|---|
| nxbt's pinned dependencies (Flask 1.1.2, eventlet 0.31, dbus-python 1.2.16 …) won't build on Python 3.13 | Installed nxbt with `--no-deps`, then current versions of its dependencies; used the system `python3-dbus` through `--system-site-packages` |
| nxbt crashed with "hciconfig is not available" | `sudo dnf install bluez-deprecated` (provides `hciconfig` and `hcitool`) |
| nxbt needs root, and sudo here needs a password | The user runs `nxbridge.py` with sudo in a separate terminal; the bot talks to it over a Unix socket |
| Shrunken copy of the screen pasted into the top-left of frames | OpenCV reuses the same buffer for each raw frame, so a new frame overwrote bytes still being decoded. Each frame is now copied first |
| `import pikachu` failed from `examples/` | Added `pyproject.toml` and ran `pip install -e .` |

## What's been built

- `pikachu/controls.py`
  - `Button`: all Pro Controller buttons, combinable with `|`.
  - `Action`: the buttons held plus analogue sticks from −1 to 1.
  - `KartAction`: 11 fixed Mario Kart actions (accelerate, steer, drift, hop, item, brake).
- `pikachu/capture.py`: `FrameGrabber` reads the card in a background thread, keeps the newest frame, decodes on request at full, 1/2, 1/4 or 1/8 size, and returns RGB numpy arrays or PIL images.
- `pikachu/controller.py`: `Controller` sends held controller state to the bridge and resends it in the background. It also has `press()` and `macro()` for menus.
- `pikachu/policy.py`: the `Policy` base class (`act(image) -> Action | KartAction`) and the `run()` loop.
- `nxbridge.py`: the bridge that runs as root. It owns the nxbt controller, takes commands on `/tmp/pikachu-ctl.sock`, writes status to `/tmp/pikachu-status.json`, and logs to `/tmp/nxbt.log`. A 250 ms watchdog releases all inputs if the bot stops sending.
- `examples/press_test.py`, `examples/latency.py`, `examples/steer_demo.py`.

Running it:

```
sudo /home/zucc/pikachu/.venv/bin/python /home/zucc/pikachu/nxbridge.py   # separate terminal
.venv/bin/python examples/latency.py 30
```

## Open issues and next steps

1. **Reconnecting after a restart.** Every bridge restart currently needs Change Grip/Order opened on the Switch. nxbt looks for a previously paired device named "Nintendo Switch", but BlueZ kept no record of the Switch (`bluetoothctl devices` is empty), and a Switch 2 may report a different name. Fix: record the Switch's address when it connects and pass it to nxbt as `reconnect_address`.
2. **Screen classifier.** Identify the current screen: title, main menu, mode select, character or kart select, course select, loading, racing, results, HOME, popups.
3. **Menu navigation and reset.** Get from any screen to the start of a Time Trial on its own.
4. **HUD readers.** Read position, lap, coins and the item slot from fixed regions of the screen.
5. **Recording play for imitation learning.** Pass a gamepad's inputs through to the Switch and log frames and inputs with timestamps.
6. **Save results.** `latency.py` and `run()` currently only print results; they should also append them to a file.

Constraints: CPU only on this machine, so any heavy model should run elsewhere over the network. The game runs in real time only, so plain trial-and-error reinforcement learning would be slow. Keep the bot offline (Time Trials or VS against the computer), because using one online breaks Nintendo's terms.
