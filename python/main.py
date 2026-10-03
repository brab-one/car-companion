"""Entry point on the UNO Q. Glue only: it connects the WebUI to the Companion,
which holds all the logic (python/companion/). tools/run_pc.py does the same
job on a PC."""

import time
from pathlib import Path

from arduino.app_utils import App
from arduino.app_bricks.web_ui import WebUI

from companion.core import Companion

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CHANNEL = "msg"  # every message travels on this one WebUI channel, see PROTOCOL.md

ui = WebUI()


def send(msg, to=None):
    ui.send_message(CHANNEL, msg, to)  # to: a client's id, or None for all clients


brain = Companion(CONFIG_DIR, send)
ui.on_message(CHANNEL, lambda sid, data: brain.receive(data, sid))

# Plug-in points for later steps:
#  - BLE link to the phone: pass its messages to brain.receive() and add it to send().
#  - Renderers on the sketch (LED matrix, OLED): forward each scene over Bridge.


def loop():
    brain.tick()
    time.sleep(1 / brain.fps)


App.run(user_loop=loop)
