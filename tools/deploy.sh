#!/usr/bin/env bash
# Copy the app to the UNO Q over the USB cable (adb), restart it, and make its
# page reachable on this PC. No Wi-Fi needed.
#
#   tools/deploy.sh            copy, restart, then open http://localhost:7001
#   tools/deploy.sh --config   also overwrite the board's config files with yours
#
# Config files already on the board are kept by default, so changes made there
# (later from the phone app) survive a deploy. With several adb devices
# plugged in (e.g. your phone), pick the board: ANDROID_SERIAL=<serial> tools/deploy.sh
set -euo pipefail

APP_DIR=/home/arduino/ArduinoApps/car-companion
PORT=7001  # this PC's port for the board's page (7000 stays free for tools/run_pc.py)
here=$(cd "$(dirname "$0")/.." && pwd)
overwrite_config=no
[[ ${1:-} == --config ]] && overwrite_config=yes

# Copy only what the board needs, without Python caches.
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp -r "$here/app.yaml" "$here/README.md" "$here/python" "$here/assets" "$stage/"
[[ -d $here/sketch ]] && cp -r "$here/sketch" "$stage/"
find "$stage" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "Copying the app to $APP_DIR ..."
adb shell mkdir -p "$APP_DIR/config"
adb push "$stage"/* "$APP_DIR/"

for file in "$here"/config/*.json; do
  name=$(basename "$file")
  exists=$(adb shell "test -e $APP_DIR/config/$name && echo yes || echo no")
  if [[ $overwrite_config == yes || $exists != yes* ]]; then
    adb push "$file" "$APP_DIR/config/$name"
  else
    echo "Kept the board's config/$name (use --config to overwrite it)"
  fi
done

echo "Restarting the app ..."
adb shell arduino-app-cli app restart "$APP_DIR"
adb forward tcp:$PORT tcp:7000 >/dev/null

echo
echo "Running on the board. Open http://localhost:$PORT"
echo "Its log: adb shell arduino-app-cli app logs $APP_DIR"
