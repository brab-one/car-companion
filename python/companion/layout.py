"""Places the eyes on the display(s) and builds the scene the renderers draw.

A scene is plain data (see PROTOCOL.md, "Scenes"). Renderers, the web canvas
now and the OLED sketch later, only draw it and never decide anything, so a
new kind of display needs no change here."""

SIZE = 128  # display width and height in pixels
MIN_H = 2   # a closed eye is a thin line, not nothing


def eyes_scene(pair, settings, look=(0.0, 0.0), blink=0.0, brightness=1.0, visor=None):
    """pair: eye parameters from faces.resolve() (possibly mid-animation).
    look: x and y from -1 to 1; positive is right / down, as seen by the viewer.
    blink: 0 is open, 1 is closed. brightness: 0 to 1.
    visor: how the visor looks (faces.json "visor"); pair["visor"] says how far it is down."""
    lay = settings["layout"]
    dx = look[0] * lay["look_x_px"]
    dy = look[1] * lay["look_y_px"]
    left, right = pair["left"], pair["right"]
    if settings["displays"] == 2:
        # One eye per display, centred and scaled up. Display 1 is on the viewer's left.
        s = lay["dual_scale"]
        x, y = SIZE / 2 + dx * s, SIZE / 2 + dy * s
        displays = [
            [_shape(left, x, y, "right", blink, s)],
            [_shape(right, x, y, "left", blink, s)],
        ]
    else:
        half_gap = pair["gap"] / 2
        y = SIZE / 2 + dy
        displays = [[
            _shape(left, SIZE / 2 - half_gap - left["w"] / 2 + dx, y, "right", blink),
            _shape(right, SIZE / 2 + half_gap + right["w"] / 2 + dx, y, "left", blink),
        ]]
    scale = lay["dual_scale"] if settings["displays"] == 2 else 1.0
    down = pair.get("visor", 0)
    return {
        "kind": "eyes",
        "brightness": brightness,
        "displays": [{"shapes": shapes, **({"visor": _visor(visor, down, scale)} if visor and down > 0 else {})}
                     for shapes in displays],
    }


def _visor(look, down, scale=1.0):
    """The visor slides down from above the top edge; down = 1 is all the way down.
    It belongs to the head, so it does not follow the eyes' look."""
    h = round(look["h"] * scale)
    w = min(SIZE, round(look["w"] * scale))
    lowest = SIZE / 2 + (look["y"] - SIZE / 2) * scale
    highest = -h / 2 - 1  # just out of sight
    return {
        "x": SIZE // 2,
        "y": round(highest + (lowest - highest) * down),
        "w": w,
        "h": h,
        "r": min(round(look["r"] * scale), w // 2, h // 2),
        "color": look["color"],
        "alpha": look["alpha"],
        "shine": look["shine"],
    }


def _shape(eye, x, y, inner, blink, scale=1.0):
    """One eye as drawn, in whole pixels. inner: the side facing the other eye."""
    open_ = 1.0 - blink
    w = round(eye["w"] * scale)
    h = max(MIN_H, round(eye["h"] * scale * open_))
    return {
        "x": round(x),
        "y": round(y),
        "w": w,
        "h": h,
        "r": min(round(eye["r"] * scale), w // 2, h // 2),
        "color": eye["color"],
        "slant": round(eye["slant"] * scale * open_),
        "cut": round(eye["cut"] * scale * open_),
        "inner": inner,
    }
