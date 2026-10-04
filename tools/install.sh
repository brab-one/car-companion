#!/usr/bin/env bash
# Install Car Companion on the board over the USB cable, or bring it up to date:
#
#   1. the app (tools/deploy.sh: copies it, compiles and flashes the sketch, starts it)
#   2. his eyes as the microcontroller's boot animation (tools/boot_eyes.py)
#   3. the wireless Android Auto bridge (tools/android_auto.sh)
#   4. the fast start: the app at boot without App Lab (tools/fast_start.sh)
#   5. the board helper, for Configure > Board (tools/install_board_helper.sh)
#
# Steps 4 and 5 ask for the board's password, the one from its first setup.
#
#   tools/install.sh                all of it
#   tools/install.sh --phone        also build the Android app and install it on your phone
#                                   (plugged into this PC, with USB debugging on)
#   tools/install.sh --no-password  without steps 4 and 5
#   tools/install.sh --config       overwrite the board's config files with yours (see deploy.sh)
#
# Needs adb and python3; for --phone also a JDK 17 or newer and the Android SDK.
# The first time, the board must be on your Wi-Fi: step 3 downloads Debian for
# the bridge. Other adb devices (a phone, an emulator) may be plugged in too:
# the board is the one that runs App Lab.
set -euo pipefail

here=$(cd "$(dirname "$0")/.." && pwd)
phone=no
root=yes
deploy_args=()
for arg in "$@"; do
  case "$arg" in
    --phone) phone=yes ;;
    --no-password) root=no ;;
    --config) deploy_args+=(--config) ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (see tools/install.sh --help)"; exit 1 ;;
  esac
done

devices() { adb devices | awk 'NR > 1 && $2 == "device" {print $1}'; }
step() { echo; echo "== $*"; }

# The board runs Debian with App Lab, not Android.
board=""
for serial in $(devices); do
  if [[ $(adb -s "$serial" shell 'command -v arduino-app-cli >/dev/null && echo yes' 2>/dev/null | tr -d '\r') == yes ]]; then
    board=$serial
    break
  fi
done
if [[ -z $board ]]; then
  echo "No UNO Q found over adb. Plug it into this PC with its USB-C cable (see: adb devices)."
  exit 1
fi
export ANDROID_SERIAL=$board  # for the scripts below
echo "The board: $board"

step "1/5 The app"
"$here/tools/deploy.sh" ${deploy_args[@]+"${deploy_args[@]}"}

step "2/5 His eyes from power-on"
python3 "$here/tools/boot_eyes.py"

step "3/5 The wireless Android Auto bridge"
"$here/tools/android_auto.sh" --no-log

if [[ $root == yes ]]; then
  step "4/5 Fast start (asks for the board's password)"
  "$here/tools/fast_start.sh"
  step "5/5 The board helper (asks for the board's password)"
  "$here/tools/install_board_helper.sh"
else
  step "4/5 and 5/5 skipped (--no-password)"
fi

if [[ $phone == yes ]]; then
  step "The Android app"
  phone_serial=""
  for serial in $(devices); do
    [[ $serial == "$board" || $serial == emulator-* ]] && continue
    if [[ -n $(adb -s "$serial" shell getprop ro.build.version.sdk 2>/dev/null | tr -d '\r') ]]; then
      phone_serial=$serial
      break
    fi
  done
  if [[ -z $phone_serial ]]; then
    echo "No phone found over adb: plug it in, with USB debugging on (Settings > Developer options)."
    exit 1
  fi
  if [[ ! -f $here/android/local.properties && -z ${ANDROID_HOME:-} && -d $HOME/Android/Sdk ]]; then
    echo "sdk.dir=$HOME/Android/Sdk" > "$here/android/local.properties"  # where Android Studio puts it
  fi
  (cd "$here/android" && ./gradlew -q assembleDebug)
  adb -s "$phone_serial" install -r "$here/android/app/build/outputs/apk/debug/app-debug.apk"
  echo "Installed on $phone_serial. In the app's Settings, add the board's address on your Wi-Fi for home."
fi

echo
echo "Done. The board's page: http://localhost:7001 over the cable; Android Auto: Configure > Board."
