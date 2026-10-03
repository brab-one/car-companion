# Car Companion

A small companion for the dashboard of a Subaru BRZ, running on an Arduino
UNO Q. It shows an animated face on a 128 × 128 OLED and is configured from a
phone app. Later it will react to driving data and show pictures when you
drive into certain places.

Until the hardware arrives, a browser simulator stands in for the OLED, the
phone app, the car and the GPS.

**Progress**

- [x] 1. App skeleton and simulator showing the eyes from `faces.json`
- [ ] 2. Animation player and `animations.json`
- [ ] 3. Car panel and `rules.json`
- [ ] 4. Places and location panel
- [ ] 5. Editing settings and config from the app, with live reload
- [ ] 6. LED matrix output on the board

## Run it on your PC

```bash
python3 tools/run_pc.py
```

Then open http://localhost:7000. Only Python 3 is needed, nothing to install.
With `--lan` you can also open it on your phone (same Wi-Fi, your PC's address).

## Run it on the board

Connect the board to this PC with its USB-C cable, then:

```bash
tools/deploy.sh
```

It copies the app over the cable (adb, no Wi-Fi or password needed), restarts
it on the board and makes the board's page available at http://localhost:7001.
When the board is on your Wi-Fi, the page is also at `http://<board's IP>:7000`,
for example on your phone. Config files already on the board are kept; add
`--config` to overwrite them with yours. The app also shows up in App Lab as
**Car Companion**.

The board's log:

```bash
adb shell arduino-app-cli app logs /home/arduino/ArduinoApps/car-companion
```

## Tests

```bash
python3 -m unittest
```

The logic in `python/companion/` has no Arduino imports, so the tests run on any PC.

## How it fits together

```
 simulator / phone app ──┐                 ┌──────────────┐  scene  ┌─ simulator canvas
 car (simulated, later OBD) ──  messages ─▶│  Companion   │────────▶├─ LED matrix (step 6)
 GPS (simulated, later phone) ─┘           │  python/     │         └─ OLED (later)
                                           └──────┬───────┘
                                     config/*.json (applied live)
```

| Path | What it is |
|---|---|
| `config/` | All data: faces, settings (later animations, rules, places). |
| `python/main.py` | Board glue: WebUI and (later) Bridge, connected to the Companion. |
| `python/companion/` | The logic, plain Python. `core.py` is the place to start. |
| `assets/` | The simulator page, served by the board or by `run_pc.py`. |
| `tools/` | `run_pc.py`, `deploy.sh`, and the PC stand-in for Arduino's `arduino.js`. |
| `tests/` | Unit tests for the logic. |
| `PROTOCOL.md` | Every message between app and companion, and the scene format. |

## Config files

All behaviour lives in JSON files in `config/`. Edit them by hand, in the
simulator (step 5) or later from the phone; changes apply within a second.

When a file has a problem, the log and the phone panel say exactly where, for
example `faces.json: moods.happy.h: expected a number, got "tall"`, and the
companion keeps running on the last good version (`config/.good/`), or on the
built-in defaults if there is none.

### settings.json

Settings you leave out use the defaults in `python/companion/defaults.py`.

| Field | Meaning |
|---|---|
| `displays` | 1: both eyes on one OLED. 2: one OLED per eye. |
| `fps` | Scene updates per second. |
| `brightness.mode` | `"manual"`, or `"auto"` to follow sunrise and sunset (step 4). |
| `brightness.manual` | Brightness in percent for manual mode. |
| `layout.look_x_px`, `layout.look_y_px` | How far the eyes move when looking fully sideways or up/down. |
| `layout.dual_scale` | How much bigger the eyes are with two displays. |

## Add a mood

Add an entry to `moods` in `config/faces.json`. A mood inherits everything
from the default mood (`neutral`) and only lists what changes:

```json
"sad": {"h": 30, "slant": -14, "color": "#5AA0FF"}
```

| Field | Meaning (pixels on the 128 × 128 display) |
|---|---|
| `w`, `h` | Eye width and height. |
| `r` | Corner radius. |
| `color` | `"#RRGGBB"`. |
| `slant` | Top edge lower at the inner side (angry), or with a negative value at the outer side (sad, worried). |
| `cut` | Pixels cut from the bottom by a curve, for happy ^ ^ eyes. |
| `gap` | Space between the eyes. |
| `blink_s` | `[min, max]` seconds between blinks (from step 2), or `null` for no blinking. |
| `left`, `right` | Change one eye only, e.g. `"left": {"h": 18}`. |

Save the file and the new mood button appears in the simulator.

## Add an animation, a rule, a place

These sections arrive with steps 2, 3 and 4.

## Where the next parts plug in

- **OLED**: a renderer in the sketch that draws scenes by the rules in
  PROTOCOL.md; `python/main.py` forwards scenes over Bridge. The logic does not change.
- **BLE to the phone**: a second transport in `python/main.py` carrying the same messages.
- **OBD dongle**: replaces the simulated car (step 3) behind the same interface.
- **AI chat**: the chat handler (step 3) answers from local data until then.
- **Voice**: speaks the `say` messages.
