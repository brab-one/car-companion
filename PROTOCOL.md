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
| `config_patch` | `name`, `data` | Like `config_set` for some fields only (nested objects are merged): the rest of the file stays as written, without the defaults filled in. Answer: `config_result`, to this client. |
| `image_put` | `name` (e.g. `"kastelruth.png"`), `png_base64` | Stores a place picture: a 128 × 128 PNG, at most 300 kB. Answer: `image_result`, to this client; everyone gets `images`. |
| `clip_put` | `name` (e.g. `"wheel.png"`), `part`, `parts`, `data` (base64) | Stores a clip or a place's video, sent in parts of at most 384 kB: one tall PNG, 128 wide, frames of 128 × 128 under each other, at most 300 frames and 8 MB. Answer to each part: `clip_result`, to this client; after the last part everyone gets `clip_files`. |
| `clip_play` | `id` | Shows a clip from clips.json now ("Play now"). |
| `play` | `name`, or `steps` | Plays an animation from animations.json, or unsaved steps (a preview while editing). Example: `{"type": "play", "steps": [{"mood": "happy", "ms": 300, "hold_ms": 2500}]}` |
| `ask` | `text`, optional `lang` (`"en"`, `"de"`) | A question, typed or heard. Without `lang` the language is guessed from the words. Answer: `answer`, to everyone. |
| `board_info` | | What the board is doing. Answer: `board`, to this client. The Board tab asks every 2 s while it shows. |
| `voice` | `state`: `"listening"` or `"idle"` | From the voice pipeline on the board: the wake word was heard, or no question followed. His face shows that he listens. |
| `location` | `lat`, `lon` | The phone's GPS position. Later also `speed_kmh`, `acc_m` and `time` (to set the board's clock). |
| `sim_car` | any car fields: `ignition`, `speed_kmh`, `rpm`, `oil_c`, `coolant_c`, `g_long`, `g_lat` | Simulator only: sets values on the simulated car, and stops a running scenario. |
| `sim_scenario` | `name` | Simulator only: plays a scripted drive (names in `state.scenarios`). |
| `sim_motion` | `g`, `s` | Simulator only: pretends the Modulino Movement measures `g` for `s` seconds ("Shake the board"). |

Planned: `sim_clock` (fake time of day for testing night dimming).

## Companion → app

| type | Fields | When |
|---|---|---|
| `state` | `version`, `config`, `config_errors`, `config_source`, `scene`, `status`, `car`, `scenarios`, `images`, `clip_files`, `log` | Answer to `hello`: everything the app needs to draw itself. `config` holds every config file by name; `config_errors` lists problems by file (only files that have some); `config_source` says where each file's data came from (see `config_error`); `log` holds the recent `log` messages. |
| `config` | `name`, `data`, `source` | A config file was loaded (saved from the app, or edited on disk), or answer to `config_get`. Settings arrive completed with their defaults. |
| `config_error` | `name`, `errors`, `source` | A config file on disk has problems, e.g. `faces.json: moods.happy.h: expected a number, got "tall"`. `source` says what is used instead: `last_good` or `defaults`. |
| `config_result` | `name`, `ok`, `errors`, `warnings` | Answer to `config_set`. With errors nothing was saved. Warnings are names the file uses that other files do not have (an unknown mood, a missing picture); it was saved anyway. |
| `image_result` | `name`, `ok`, `error` | Answer to `image_put`. |
| `images` | `names` | The place pictures there are now. |
| `clip_result` | `name`, `ok`, `done`, `error` | Answer to each part of `clip_put`; `done` once the whole clip is stored. |
| `clip_files` | `names` | The clip files there are now. |
| `scene` | `scene`, `t` | What the displays show now. Sent only when it changes. `t` is when the board made it (seconds, its own clock): a page shows scenes that much apart, so a bumpy Wi-Fi does not make the face stutter (assets/scene_player.js). See [Scenes](#scenes). |
| `status` | `mood`, `animation`, `rules`, `place`, `location`, `clip`, `assistant`, `asleep`, `brightness` | Sent when one of its fields changes. `mood` is the mood chosen by the rules; `animation` the one playing, or null; `rules` the ids of the active rules; `place` the id of the place we are in, or null; `location` `{lat, lon}` or null; `clip` the id of the clip on the display, or null; `assistant` `"idle"`, `"listening"`, `"thinking"` or `"speaking"`. |
| `car` | car fields, `scenario`, `motion_g`, `sensor` | Current car data, at most 5 times a second. `motion_g` is null without motion data; `sensor` says whether it comes from a real Modulino Movement. |
| `board` | `on_board`, `cpu` (`cur_mhz`, `max_mhz`, `hw_max_mhz`, `governor`, `freqs_mhz`, `governors`, `cores`), `temp_c`, `memory_mb` (`used`, `total`), `load`, `uptime_s`, `helper` | Answer to `board_info`. `on_board` is false in the PC simulator (then the values are the PC's). `helper` is what the board helper last did (config/.board_applied.json), or null when it is not installed. |
| `answer` | `question`, `text`, `lang`, `source` | His answer to `ask`. `source`: `"data"` (exact, from the car and the map), `"model"` (the AI model) or `"none"` (he could not answer). Shown in the bubble, and read aloud where there is a speaker. |
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
- `{"kind": "clip", "file": "wheel.png", "frame": 3, "frames": 16, "brightness": 1.0}`:
  frame `frame` of a clip from `assets/clips/` (from clips.json, or a place's
  video), i.e. rows `frame * 128` to `frame * 128 + 127` of its tall PNG, in
  RGB565. The companion picks the frame, so renderers only draw.
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
