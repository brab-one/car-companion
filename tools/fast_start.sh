#!/usr/bin/env bash
# Start the app at boot without App Lab compiling the sketch and checking the
# microcontroller's flash first, which takes about 20 s on every boot: two small
# services do App Lab's last steps instead (board/car-companion-sketch.service,
# board/car-companion-start.service). Asks for the board's password once (sudo).
#
#   tools/fast_start.sh          install them, App Lab no longer starts the app at boot
#   tools/fast_start.sh --undo   back to App Lab starting it as its default app
#
# Deploy with tools/deploy.sh first: the services start what App Lab set up then.
# tools/deploy.sh keeps working as before.
set -euo pipefail

APP_DIR=/home/arduino/ArduinoApps/car-companion
UNITS="car-companion-sketch.service car-companion-start.service"
LIB=/usr/local/lib/car-companion
here=$(cd "$(dirname "$0")/.." && pwd)

if [[ ${1:-} == --undo ]]; then
  adb shell -t "sudo sh -c 'systemctl disable $UNITS; cd /etc/systemd/system && rm -f $UNITS; rm -rf $LIB; systemctl daemon-reload'"
  adb shell TMPDIR=/tmp arduino-app-cli properties set default "$APP_DIR"
  echo "App Lab starts the app at boot again (compiling and checking the sketch each time)."
  exit 0
fi

adb shell test -f "$APP_DIR/.cache/app-compose.yaml" ||
  { echo "Deploy the app first (tools/deploy.sh)."; exit 1; }
for file in $UNITS release_sketch.cfg; do
  adb push -q "$here/board/$file" "/tmp/$file"
done
# Lingering keeps the arduino user's session (and its PipeWire socket, which the
# app's container mounts) running from boot. App Lab turns it on only while it has
# a default app, and off again at boot without one, but only if it turned it on
# itself: turned on here, App Lab leaves it alone.
adb shell -t "sudo sh -c 'cd /tmp && install -m 644 $UNITS /etc/systemd/system/ \
  && install -D -m 644 release_sketch.cfg $LIB/release_sketch.cfg \
  && systemctl daemon-reload && systemctl enable $UNITS && loginctl enable-linger arduino'"
adb shell "cd /tmp && rm -f $UNITS release_sketch.cfg"
# Otherwise App Lab would start it too, compiling and flashing first.
adb shell TMPDIR=/tmp arduino-app-cli properties set default none
echo "The app now starts at boot without App Lab. Undo: tools/fast_start.sh --undo"
