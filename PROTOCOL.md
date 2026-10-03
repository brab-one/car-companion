# Protocol

Everything between the app (the browser simulator now, the Android app later)
and the companion is a small JSON message with a `"type"` field.

## Transport

| Where | How |
|---|---|
| Board | Arduino WebUI (socket.io) on port 7000. One event name, `msg`, in both directions. Python: `ui.send_message("msg", msg, room=sid)`; JavaScript: `ui.send_message('msg', msg)`. |
| PC (`tools/run_pc.py`) | Same messages. Companion → app as Server-Sent Events named `msg` on `GET /events?id=<client>`; app → companion as `POST /send?id=<client>` with body `{"name": "msg", "data": <message>}`. `tools/pc_webui.js` hides this behind the same `WebUI` API. |
| Later: BLE | The same JSON messages. The phone will probably not want every `scene`; add a `subscribe` message then. |

Rules:

- A message with an unknown `type` is logged as a warning and ignored. A bad
  message never stops the companion.
- Add fields instead of renaming them, so older apps keep working.
  `version` in `hello` and `state` is the protocol version (now 1).
- Messages from the app are queued and handled in the companion's next tick,
  in the order they arrived.

## App → companion

| type | Fields | Since | What it does |
|---|---|---|---|
| `hello` | `client` (`"sim"`, `"android"`), `version` | step 1 | First message after connecting. The companion answers with `state`, to this client only. |
| `config_get` | `name` | step 1 | Asks for one config file. Answer: `config`, to this client only. |
| `play` | `name`, or `steps` | step 1 (mood only) | Plays an animation from animations.json by `name`, or unsaved `steps` (preview while editing). Step 1 applies only the `mood` of the last step, at once; the animation player arrives in step 2. Example: `{"type": "play", "steps": [{"mood": "happy"}]}` |
| `config_set` | `name`, `data` | step 5 | Replaces a config file: checked, saved atomically, applied live. Answer: `config_result`. |
| `location` | `lat`, `lon`, `acc_m`?, `speed_kmh`?, `time`? | step 4 | A GPS fix from the phone. `time` (Unix seconds) also corrects the board's clock. |
| `chat` | `text` | step 3 | A question for the companion. Answer: `chat_reply`. |
| `sim_car` | any car fields, e.g. `ignition`, `rpm` | step 3 | Simulator only: sets fake OBD values. |
| `sim_scenario` | `name` | step 3 | Simulator only: `cold_start`, `warm_up`, `launch`, `hard_brake`, `corner_left`, `corner_right`, `park`. |
| `sim_clock` | `hour`, or `null` for the real time | step 4 | Simulator only: fake time of day, to test night dimming. |

## Companion → app

| type | Fields | Since | When |
|---|---|---|---|
| `state` | `version`, `config`, `config_errors`, `config_source`, `scene`, `status`, `log` | step 1 | Answer to `hello`: everything the app needs to draw itself. `config` holds every config file by name; `config_errors` lists problems by file name (only files that have some); `config_source` says where each file's data came from (see `config_error`); `log` holds recent `log` messages. Later also `car` and `location`. |
| `config` | `name`, `data`, `source` | step 1 | A config file was loaded (from the app, or edited on disk), or answer to `config_get`. |
| `config_error` | `name`, `errors`, `source` | step 1 | A config file on disk has problems. `errors` are readable messages such as `faces.json: moods.happy.h: expected a number, got "tall"`. `source` says what is used instead: `last_good` or `defaults`. |
| `scene` | `scene` | step 1 | What the displays show now. Sent only when it changes. See [Scenes](#scenes). |
| `status` | `mood`, `brightness` | step 1 | Sent when one of its fields changes. Later also `sunrise`, `sunset`, `is_day`, `place`. |
| `log` | `level` (`info`, `warn`, `error`), `source`, `text` | step 1 | Something happened: rule fired, place entered, config problem. |
| `car` | car fields | step 3 | Current car data, 5 times a second. |
| `say` | `text`, `rule` | step 3 | The companion speaks, and which rule made it. |
| `chat_reply` | `text` | step 3 | Answer to `chat`. |
| `config_result` | `name`, `ok`, `errors` | step 5 | Answer to `config_set`. |
| `matrix` | `rows`: 8 strings of 13 digits `0`–`7` | step 6 | The LED matrix frame, mirrored in the simulator. |

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

Planned scene kinds: `off` (asleep, step 2), `value` with `label`, `value`,
`unit` (big number such as oil temperature, step 3), `image` with `image`,
`caption` (place pictures, step 4).

## Bridge (Python ↔ sketch), step 6

- `matrix_draw(bytes[104])`: LED matrix frame, 8 rows × 13 columns, values 0–7.
- `bridge_bench(bytes)`: measures throughput before deciding how scenes reach the OLED.
