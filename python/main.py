"""Entry point on the UNO Q. Glue only: it connects the WebUI and the sketch
(via Bridge) to the Companion, which holds all the logic (python/companion/).
tools/run_pc.py does the same job on a PC, without the sketch."""

import time
from pathlib import Path

from arduino.app_utils import App, Bridge
from arduino.app_bricks.web_ui import WebUI

from companion.core import Companion
from companion.llm import LlmClient

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
CHANNEL = "msg"  # every message travels on this one WebUI channel, see PROTOCOL.md

ui = WebUI()


def send(msg, to=None):
    ui.send_message(CHANNEL, msg, to)  # to: a client's id, or None for all clients


# Questions the data cannot answer go to App Lab's LLM brick (a small Qwen
# model on llama.cpp), once arduino:llm is in app.yaml.
brain = Companion(CONFIG_DIR, send, llm=LlmClient(), warm_up=True, on_board=True)
ui.on_message(CHANNEL, lambda sid, data: brain.receive(data, sid))


def on_accel(x: float, y: float, z: float):
    """The sketch sends Modulino Movement samples (in g) about 20 times a second."""
    brain.accel_sample(x, y, z)


def on_motion_sensor(found: bool):
    """The sketch reports every few seconds while it finds no Modulino Movement."""
    brain.motion_sensor(found)


Bridge.provide("accel", on_accel)
Bridge.provide("motion_sensor", on_motion_sensor)

# Plug-in points for later steps:
#  - BLE link to the phone: pass its messages to brain.receive() and add it to send().
#  - Renderers on the sketch (LED matrix, OLED): forward each scene over Bridge.


def loop():
    brain.tick()
    time.sleep(1 / brain.fps)


App.run(user_loop=loop)
