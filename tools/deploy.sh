#!/usr/bin/env bash
# Copy the app to the UNO Q over SSH, then start or restart it in App Lab.
#
#   tools/deploy.sh arduino@<board-name>.local            code; config only where missing
#   tools/deploy.sh arduino@<board-name>.local --config   also overwrite the board's config
#
# Config files are not overwritten by default, so changes made on the board
# (later from the phone app) survive a deploy. Needs rsync on both sides
# (on the board: sudo apt install rsync).
set -euo pipefail

if [[ $# -lt 1 ]]; then
  sed -n '4,5p' "$0"
  exit 1
fi

target=$1
dest=/home/arduino/ArduinoApps/car-companion
here=$(cd "$(dirname "$0")/.." && pwd)

rsync -rtv \
  --exclude .git/ --exclude .claude/ --exclude __pycache__/ --exclude tests/ --exclude config/ \
  "$here/" "$target:$dest/"

if [[ ${2:-} == --config ]]; then
  rsync -rtv --exclude .good/ "$here/config/" "$target:$dest/config/"
else
  rsync -rtv --ignore-existing --exclude .good/ "$here/config/" "$target:$dest/config/"
fi

echo "Copied to $target:$dest. Start or restart the app in App Lab."
