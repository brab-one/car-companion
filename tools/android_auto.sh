#!/usr/bin/env bash
# The wireless Android Auto bridge (android_auto/): copy it to the board over the
# USB cable and start it. It then starts with the board, and works while wireless
# Android Auto is switched on (Configure > Board, settings.json android_auto.enabled).
# Phase 1, the phone side only (README, "Wireless Android Auto").
#
#   tools/android_auto.sh          copy and (re)start it, then follow its log
#                                  (Ctrl-C stops following, the bridge keeps running)
#   tools/android_auto.sh --no-log copy and (re)start it only (tools/install.sh)
#   tools/android_auto.sh --stop   stop it, also at boot: the board's Wi-Fi stays yours
#   tools/android_auto.sh --log    follow its log
set -euo pipefail

DIR=/home/arduino/car-companion-aa
here=$(cd "$(dirname "$0")/.." && pwd)
compose="docker compose -f $DIR/compose.yaml"

case "${1:-}" in
  --stop) adb shell "$compose down"; exit ;;
  --log) exec adb shell "$compose logs -f --tail 50" ;;
esac

adb shell mkdir -p $DIR
adb push -q "$here"/android_auto/{Dockerfile,compose.yaml,bridge.py,protocol.py,setting.py} $DIR/
# A fresh start. The image is only built when missing; that downloads Debian, so the
# board must be on your network then (Android Auto switched off).
echo "Starting the bridge (the first time it builds its image, a few minutes) ..."
adb shell "$compose up -d --force-recreate"
echo "Switch wireless Android Auto on in Configure > Board (or the phone app); the board stays on"
echo "your Wi-Fi meanwhile, Android Auto gets an access point of its own."
[[ ${1:-} == --no-log ]] && exit 0
exec adb shell "$compose logs -f --tail 50"
