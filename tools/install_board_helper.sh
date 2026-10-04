#!/usr/bin/env bash
# Install the board helper on the UNO Q, once: a small service that applies
# config/board.json (the processor's limit and power policy, Wi-Fi power
# saving) as root, which the app in its container may not do. It asks for the
# board's password, the one from its first setup.
#
#   tools/install_board_helper.sh            install, or update it
#   tools/install_board_helper.sh --remove   take it off again
set -euo pipefail

here=$(cd "$(dirname "$0")/.." && pwd)
SERVICE=car-companion-board.service
HELPER=/usr/local/bin/car-companion-board-helper

if [[ ${1:-} == --remove ]]; then
  adb shell -t "sudo systemctl disable --now $SERVICE; sudo rm -f /etc/systemd/system/$SERVICE $HELPER; sudo systemctl daemon-reload"
  echo "Removed. The board keeps its current values until it restarts."
  exit
fi

adb push "$here/board/board_helper.py" /tmp/car-companion-board-helper >/dev/null
adb push "$here/board/$SERVICE" /tmp/$SERVICE >/dev/null
echo "Installing the board helper (asks for the board's password) ..."
adb shell -t "sudo install -m 755 /tmp/car-companion-board-helper $HELPER \
  && sudo install -m 644 /tmp/$SERVICE /etc/systemd/system/$SERVICE \
  && sudo systemctl daemon-reload && sudo systemctl enable $SERVICE && sudo systemctl restart $SERVICE \
  && rm -f /tmp/car-companion-board-helper /tmp/$SERVICE"
echo "The helper is $(adb shell systemctl is-active $SERVICE | tr -d '\r'). Configure > Board now changes the board."
