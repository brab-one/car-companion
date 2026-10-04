#!/usr/bin/env bash
# Copy the app to the UNO Q over the USB cable (adb), restart it, and make its
# page reachable on this PC. No Wi-Fi needed.
#
#   tools/deploy.sh            copy, restart, then open http://localhost:7001
#   tools/deploy.sh --config   also overwrite the board's config files, pictures and clips
#
# Config files, place pictures and clips are data: by default they are only copied
# when the board does not have them yet, so changes made there (in the
# Configure dialog, later from the phone) survive a deploy. With several adb
# devices plugged in (e.g. your phone), pick the board:
#   ANDROID_SERIAL=<serial> tools/deploy.sh
set -euo pipefail

APP_DIR=/home/arduino/ArduinoApps/car-companion
PORT=7001  # this PC's port for the board's page (7000 stays free for tools/run_pc.py)
here=$(cd "$(dirname "$0")/.." && pwd)
overwrite=no
[[ ${1:-} == --config ]] && overwrite=yes

# The code: everything the board needs, without Python caches and data.
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp -r "$here/app.yaml" "$here/README.md" "$here/python" "$here/assets" "$here/sketch" "$stage/"
rm -rf "$stage/assets/images" "$stage/assets/clips"
find "$stage" -name __pycache__ -type d -prune -exec rm -rf {} +

# Stop the running app first: it watches its config files and would check new
# ones with its old code while they are being copied.
echo "Stopping the app ..."
adb shell TMPDIR=/tmp arduino-app-cli app stop "$APP_DIR" >/dev/null 2>&1 || true  # may not exist yet

echo "Copying the app to $APP_DIR ..."
adb shell mkdir -p "$APP_DIR"
adb push "$stage"/* "$APP_DIR/" >/dev/null

# The data: local folder, folder on the board, file pattern.
push_data() {
  adb shell mkdir -p "$2"
  for file in "$1"/$3; do
    [[ -e $file ]] || continue
    name=$(basename "$file")
    exists=$(adb shell "test -e '$2/$name' && echo yes || echo no")
    if [[ $overwrite == yes || $exists != yes* ]]; then
      adb push "$file" "$2/$name" >/dev/null
      echo "  copied $name"
    else
      echo "  kept the board's $name (--config overwrites it)"
    fi
  done
}
push_data "$here/config" "$APP_DIR/config" "*.json"
push_data "$here/assets/images" "$APP_DIR/assets/images" "*.png"
push_data "$here/assets/clips" "$APP_DIR/assets/clips" "*.png"

# Linux keeps new files in memory for up to 30 s before writing them to the
# flash; unplugging the board in that time leaves them empty. Write them now.
adb shell sync

# AI models the bricks use (the LLM brick's "model:" in app.yaml) must be on the
# board before the app starts. App Lab downloads them once, through its daemon.
for model in $(sed -n 's/^ *model: *\(llamacpp:[^ ]*\).*/\1/p' "$here/app.yaml"); do
  if ! adb shell "curl -s -m 10 http://127.0.0.1:8800/v1/models/$model" | grep -q '"status":"installed"'; then
    echo "Downloading the AI model $model onto the board (once; a few minutes) ..."
    adb shell "curl -sN -X PUT http://127.0.0.1:8800/v1/models/$model" | grep -E 'event: (done|error)' || true
  fi
done

echo "Starting the app (it compiles and flashes the sketch each time, about a minute) ..."
# adb sets TMPDIR to Android's /data/local/tmp, which the board does not have.
adb shell TMPDIR=/tmp arduino-app-cli app start "$APP_DIR"
adb forward tcp:$PORT tcp:7000 >/dev/null

echo
echo "Running on the board. Open http://localhost:$PORT"
echo "Its log: adb shell TMPDIR=/tmp arduino-app-cli app logs $APP_DIR"
