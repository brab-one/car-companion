# Protocol

Everything between the app (the browser simulator now, the Android app later)
and the companion is a small JSON message with a `"type"` field.

## Transport

| Where | How |
|---|---|
| Board | Arduino WebUI (socket.io) on port 7000. One event name, `msg`, in both directions. Python: `ui.send_message("msg", msg, sid)`; JavaScript: `ui.send_message('msg', msg)`. |
| PC (`tools/run_pc.py`) | Same messages. Companion → app as Server-Sent Events named `msg` on `GET /events?id=<client>`; app → companion as `POST /send?id=<client>` with body `{"name": "msg", "data": <message>}`. `tools/pc_webui.js` hides this behind the same `WebUI` API. |
| Later: BLE | The same JSON messages. The phone will probably not want every `scene`; add a `subscribe` message then. Pictures (`image_put`) will need splitting into chunks. |

Rules:

- A message with an unknown `type` is logged as a warning and ignored. A bad
  message never stops the companion.
- Add fields instead of renaming them, so older apps keep working.
  `version` in `hello` and `state` is the protocol version (now 1).
- Messages from the app are queued and handled in the companion's next tick,
  in the order they arrived. Answers marked "to this client" go only to the
  app that asked.

## App → companion

| type | Fields | What it does |
|---|---|---|
| `hello` | `client` (`"sim"`, `"android"`), `version` | First message after connecting. Answer: `state`, to this client. |
| `config_get` | `name` | Asks for one config file. Answer: `config`, to this client. |
| `config_set` | `name`, `data` | Replaces a whole config file. It is checked, saved atomically and applied at once. Answer: `config_result`, to this client; everyone gets the new `config`. |
| `image_put` | `name` (e.g. `"kastelruth.png"`), `png_base64` | Stores a place picture: a 128 × 128 PNG, at most 300 kB. Answer: `image_result`, to this client; everyone gets `images`. |
| `play` | `name`, or `steps` | Plays an animation from animations.json, or unsaved steps (a preview while editing). Example: `{"type": "play", "steps": [{"mood": "happy", "ms": 300, "hold_ms": 2500}]}` |
| `location` | `lat`, `lon` | The phone's GPS position. Later also `speed_kmh`, `acc_m` and `time` (to set the board's clock). |
| `sim_car` | any car fields: `ignition`, `speed_kmh`, `rpm`, `oil_c`, `coolant_c`, `g_long`, `g_lat` | Simulator only: sets values on the simulated car, and stops a running scenario. |
| `sim_scenario` | `name` | Simulator only: plays a scripted drive (names in `state.scenarios`). |
| `sim_motion` | `g`, `s` | Simulator only: pretends the Modulino Movement measures `g` for `s` seconds ("Shake the board"). |

Planned: `chat` (a question; answer `chat_reply`), `sim_clock` (fake time of
day for testing night dimming).

## Companion → app

| type | Fields | When |
|---|---|---|
| `state` | `version`, `config`, `config_errors`, `config_source`, `scene`, `status`, `car`, `scenarios`, `images`, `log` | Answer to `hello`: everything the app needs to draw itself. `config` holds every config file by name; `config_errors` lists problems by file (only files that have some); `config_source` says where each file's data came from (see `config_error`); `log` holds the recent `log` messages. |
| `config` | `name`, `data`, `source` | A config file was loaded (saved from the app, or edited on disk), or answer to `config_get`. Settings arrive completed with their defaults. |
| `config_error` | `name`, `errors`, `source` | A config file on disk has problems, e.g. `faces.json: moods.happy.h: expected a number, got "tall"`. `source` says what is used instead: `last_good` or `defaults`. |
| `config_result` | `name`, `ok`, `errors`, `warnings` | Answer to `config_set`. With errors nothing was saved. Warnings are names the file uses that other files do not have (an unknown mood, a missing picture); it was saved anyway. |
| `image_result` | `name`, `ok`, `error` | Answer to `image_put`. |
| `images` | `names` | The place pictures there are now. |
| `scene` | `scene` | What the displays show now. Sent only when it changes. See [Scenes](#scenes). |
| `status` | `mood`, `animation`, `rules`, `place`, `location`, `asleep`, `brightness` | Sent when one of its fields changes. `mood` is the mood chosen by the rules; `animation` the one playing, or null; `rules` the ids of the active rules; `place` the id of the place we are in, or null; `location` `{lat, lon}` or null. |
| `car` | car fields, `scenario`, `motion_g`, `sensor` | Current car data, at most 5 times a second. `motion_g` is null without motion data; `sensor` says whether it comes from a real Modulino Movement. |
| `say` | `text`, `source` | The companion says a line; `source` is what made him say it, e.g. `rule cold_oil_rev` or `place kastelruth`. |
| `log` | `level` (`info`, `warn`, `error`, `say`), `source`, `text` | Something happened: a rule turned on or off, a place was entered, a config problem. |

Planned: `chat_reply`, `matrix` (the LED matrix frame, step 6).

## Scenes

The logic decides what the displays show; renderers only draw it. Renderers
today: the simulator canvas (`assets/render_canvas.js`). Later: the LED
matrix and the OLED, both in the sketch.

```json
{"kind": "eyes", "brightness": 1.0, "displays": [{"shapes": [
  {"x": 39, "y": 64, "w": 36, "h": 44, "r": 10, "color": "#00E5FF", "slant": 0, "cut": 0, "inner": "right"},
  {"x": 89, "y": 64, "w": 36, "h": 44, "r": 10, "color": "#00E5FF", "slant": 0, "cut": 0, "inner": "left"}
]}]}
```

- `displays`: one entry per physical display (`settings.displays`). With two
  displays each one holds one eye; display 1 is on the viewer's left.
- `brightness`: 0 to 1. The OLED applies it to the whole panel.
- Shapes are in whole pixels on a 128 × 128 display:
  - `x`, `y`: centre. `w`, `h`: size. `r`: corner radius, never more than half of `w` or `h`.
  - `color`: `"#RRGGBB"`. The OLED stores it as RGB565 (5 bits red, 6 green, 5 blue).
  - `slant`: how many pixels lower the top edge is at the inner side. Negative: lower at the outer side.
  - `cut`: how many pixels an ellipse takes off the bottom (happy eyes).
  - `inner`: `"left"` or `"right"`, the side facing the other eye.

Drawing rule (the sketch must draw exactly like `insideEye()` in
`render_canvas.js`). A pixel is lit when its centre `(px + 0.5, py + 0.5)` is:

1. inside the rectangle (on the edge counts);
2. inside the rounded corners: in a corner, within `r` of the corner circle's centre;
3. not above the top edge, which lies `drop` pixels below the rectangle's top,
   with `t` going from 0 at the outer side to 1 at the inner side:
   `drop = slant * t` when `slant >= 0`, else `drop = -slant * (1 - t)`;
4. outside the cut ellipse, centred at `(x, y + h - cut)` with radii `0.75 * w` and `0.5 * h`
   (its top touches the eye `cut` pixels above the bottom edge).

A display can also have a `visor`, drawn over its eyes (only while it is
down, at least partly):

```json
{"shapes": [...], "visor": {"x": 64, "y": 62, "w": 124, "h": 44, "r": 12,
                            "color": "#0B1E3A", "alpha": 0.82, "shine": "#9CC8FF", "glint": 0.2}}
```

`x`, `y`, `w`, `h`, `r` place a rounded rectangle as for an eye (no slant, no
cut). While it slides down, `y` goes from just above the display to its
place; it moves with the eyes. Drawing rule (`fillVisor()` in `render_canvas.js`): for each pixel of
the rectangle, with `left = x - w/2`, `top = y - h/2` and
`s = (px + 0.5 - left) + (py + 0.5 - top)` (the distance along a "/" diagonal):

- reflection where `g <= s < g + 5` or `g + 9 <= s < g + 11`, with `g = glint * w`:
  `shine` mixed over the pixel at 0.9 (`glint` moves the stripes across the visor);
- everywhere else: `color` mixed over the pixel at `alpha`
  (`new = color * alpha + old * (1 - alpha)`, per colour channel).

Any scene can have a speech `bubble`, drawn last, on the first display only:

```json
"bubble": {"x": 64, "y": 111, "w": 110, "h": 28, "r": 5, "color": "#FFFFFF", "tail": [64, 91],
           "text": {"x": 14, "y": 102, "w": 101, "h": 16, "bits": "<base64>"}}
```

- The box: a rounded rectangle as for an eye. Pixels inside it but not
  inside the same box 1 px smaller on every side (`w - 2`, `h - 2`, `r - 1`)
  are the outline, in `color`; the rest of the box is black.
- The tail: the triangle with its tip at `tail` and its base on the box's top
  edge, 4 px each side of the tip's x at the edge (half-width
  `4 * (py - tip_y) / (top - tip_y)`), filled with `color`.
- The text: a 1-bit picture of `w` x `h` pixels at (`x`, `y`). `bits` is
  base64; each row takes `ceil(w / 8)` bytes, the first pixel is the highest
  bit. Set bits are drawn in `color`. Python wraps the text and draws it
  with its 5 x 7 font (`python/companion/font.py`), so renderers need no font.

Other kinds:

- `{"kind": "image", "image": "schlern.png", "caption": "Schlern", "brightness": 1.0}`:
  a place picture from `assets/images/`, 128 × 128, shown in RGB565. The
  caption is not drawn yet (the OLED needs a pixel font first).
- `{"kind": "off"}`: the display is off (a while after the ignition was turned off).
- Planned: `value` with `label`, `value`, `unit` (a big number such as the oil temperature).

## Bridge (Python ↔ sketch)

| Call | Direction | What |
|---|---|---|
| `accel(x, y, z)` | sketch → Python, notify | One Modulino Movement sample in g, about 20 per second. |
| `motion_sensor(found)` | sketch → Python, notify | Sent every 5 s while no Modulino Movement is found on the Qwiic connector. |

Planned (step 6): `matrix_draw(bytes[104])` for the LED matrix (8 rows × 13
columns, values 0–7), and `bridge_bench(bytes)` to measure throughput before
deciding how scenes reach the OLED.
