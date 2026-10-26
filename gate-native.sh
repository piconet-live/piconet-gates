#!/bin/bash
# gate-native.sh TAG BUILD [ROUNDS]: the exactness gates of the native form (the port-recomp notes 5.11): module BUILD
# (work/mod-cg-BUILD, compiled from the patched game and the mod image) with the native bundle's window, host calls
# and patch list (the launch files port/configs/gate-scene.json and gate-scene-single-core.json: the bundle, and the
# patch list forced, since the saved states hold stock code and two older codes' words), mode 0 (a plain start),
# against the JIT of the same round, which runs the saved state as it is: its launch files are
# gate-scene-reference.json and gate-scene-reference-single-core.json, no bundle and "debug.jit". Every run has a
# launch file of its own (<work>/port/launch/RUN.json), which also says what the harness needs of the game (the
# saved state and the automation folder allowed, the probe, the pad script, the dumps: launch-file.py --harness):
# the runner takes none of it from the environment in a start with a launch file.
# Cheats are OFF for both runs of a pair (machine-gate-n.toml): the emulator's code handler would write the older
# codes' words every picture, against the patch list. Dual core, race300 and racego, ROUNDS rounds (default 2);
# single core one round. Complete output in gbatch-TAG.gates.txt. The busy check is chk.sh, as it is.
# No run opens a GameCube controller adapter (SDL_JOYSTICK_HIDAPI_GAMECUBE=0; see launcher-run.sh).
#   BUNDLE=<folder>   the native bundle BUILD was made from, under the work folder (default <work>/port/bundle-native,
#                     module n6's; the saved states need no game folder of the image)
#   MACHINE=<file>    the harness's machine file (default <work>/port/machine-gate-n.toml). Another one names another
#                     runner in its `runner` line (a runner staged in a launcher folder: gates.sh writes such a
#                     file); the rest of it must be the default's: the configuration put in place here is that one's
#   PORT_WORK, PORT_WORK_WIN, RECOMP_KIT, BUSY_CHECK   another work folder, recomp-kit checkout (its harness in place of port/gates/vendor/harness) or busy check
set -uo pipefail
. "$(dirname "$0")/runner.sh" || exit 2; W=$root   # the runner (pins.tsv REPO_RUNNER)
D=${PORT_WORK:-$PORT_WORK_DEFAULT}; DW=${PORT_WORK_WIN:-$(wslpath -w "$D")}; S=$D/port/scratch/rp
T=$1; B=$2; N=${3:-2}; K=$HARNESS_DIR/recomp.py   # the harness: port/gates/vendor/harness, or RECOMP_KIT's
pc_busy_check "$D"; BN=${BUNDLE:-$D/port/bundle-native}; MF=${MACHINE:-$D/port/machine-gate-n.toml}
case "$BN" in "$D"/*) ;; *) echo "gate-native: BUNDLE must be under $D" >&2; exit 2;; esac
[ -f "$BN/patches.json" ] || { echo "gate-native: $BN is no native bundle" >&2; exit 2; }
[ -f "$MF" ] || { echo "gate-native: no machine file $MF" >&2; exit 2; }
BW="$DW\\$(printf %s "${BN#"$D"/}" | tr / '\\')"
# a run's launch file: the picture on its own thread or on the CPU's (the single-core pairs), native or the reference
launch() {  # run scene config ref|on
  local name=gate-scene; [ $4 = ref ] && name=gate-scene-reference; [ $3 = single-core ] && name=$name-single-core
  "$W/port/gates/runs/launch-file.py" $name "$D/port/launch/$1.json" "bundle=$BW" "run=$DW\\port\\runs\\$1" --harness $2
}
export RECOMP_AGENT=port RECOMP_MANIFEST=$W/recomp/manifest.toml RECOMP_MACHINE=$MF
LOCKS=${PORT_LOCKS:-$PORT_LOCKS_DEFAULT}; [ -d "$LOCKS" ] || LOCKS=$D   # the PC's locks (cpu-window.sh)
# `recomp.py run` does not restore the configuration: it is put in place here (and the cheats-on one put back at the end)
cp "$D/port/Dolphin.ini.gate-nocheats" "$D/user/Config/Dolphin.ini"
grep -q "^EnableCheats = False" "$D/user/Config/Dolphin.ini" || { echo "cheats are not off: batch stopped"; exit 4; }
one() {  # run scene config ref|on
  "$BUSY" > /dev/null || { echo "a runner or launcher is running: batch stopped"; "$BUSY"; exit 3; }
  local why; why=$("$W/port/gates/room-for-games.sh" 1) || { echo "$why: batch stopped"; exit 3; }   # Windows' memory
  local L; L=$(launch "$@") || exit 2
  local A=(--build "$B" --arg=--config "--arg=$L")
  [ $4 = ref ] && A=(--reference --arg=--config "--arg=$L")
  # (the harness's request file is in its machine file's work folder; when the PC's locks are elsewhere, PORT_LOCKS,
  # the run takes a request there too: replay-check.sh says why)
  ( [ "$LOCKS" -ef "$D" ] || pc_take cpu-window.sh "port: gate scene $1 (3 min)" 4
    python3 -u $K run $1 --scene $2 --config $3 "${A[@]}" --env SDL_JOYSTICK_HIDAPI_GAMECUBE=0 --not-timing --label "Port test" --arg=--title --arg=Port-test--agent-gate-run--closes-by-itself --max-seconds 150 2>&1 ) | grep --line-buffered -E "exited early|force kill|stopped after|Error|error|recomp.py:"
  [ "${PIPESTATUS[0]}" != 75 ] || { echo "the machine was not free in 40 minutes: batch stopped"; exit 3; }
}
for r in $(seq 1 $N); do for scene in race300 racego; do for who in ref on; do one $T-dual-core-$scene-$who-$r $scene dual-core $who; done; done; done
for scene in race300 racego; do for who in ref on; do one $T-single-core-$scene-$who-1 $scene single-core $who; done; done
cp "$D/scratch/Dolphin.ini.single" "$D/user/Config/Dolphin.ini"
echo "runs done $(date +%T)"
mkdir -p "$S"; G=$S/gbatch-$T.gates.txt; : > $G
for scene in race300 racego; do
  for r in $(seq 1 $N); do echo "== dual-core $scene $r" >> $G; python3 -u $K gate $T-dual-core-$scene-on-$r --against $T-dual-core-$scene-ref-$r --kind reference >> $G 2>&1; done
  echo "== single-core $scene" >> $G; python3 -u $K gate $T-single-core-$scene-on-1 --against $T-single-core-$scene-ref-1 --kind reference >> $G 2>&1
done
echo "gates done $(date +%T)"
