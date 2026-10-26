#!/bin/bash
# time-native.sh TAG BUILD [ROUNDS]: the timing batch of the native form (the port-recomp notes 5.11): dual core,
# both gate scenes, interleaved: the JIT and module BUILD in the native form (the native bundle, mode 0), ROUNDS
# rounds (default 2). Cheats off for both (the saved states hold the older codes' words). Each run takes TIMING.lock through the harness; quiet.sh is asked first and the batch
# stops when the PC is not quiet. Then the harness's table: recomp.py time.
# No run opens a GameCube controller adapter (SDL_JOYSTICK_HIDAPI_GAMECUBE=0; see launcher-run.sh).
#   ALSO="n3 ..."   more modules of the native form in the same batch (an earlier one, to compare with)
#   BUNDLE=<folder>  the native bundle BUILD (and every ALSO module) was made from, under the work folder (default
#                    <work>/port/bundle-native, module n6's)
#   MACHINE=<file>   the harness's machine file (default <work>/port/machine-gate-n.toml). Another one names another
#                    runner in its `runner` line, for both kinds of run (gate-native.sh says the rest)
#   PORT_WORK, PORT_WORK_WIN, RECOMP_KIT, BUSY_CHECK   another work folder, recomp-kit checkout (its harness in place of port/gates/vendor/harness) or busy check
set -uo pipefail
. "$(dirname "$0")/runner.sh" || exit 2; W=$root   # the runner (pins.tsv REPO_RUNNER)
D=${PORT_WORK:-$PORT_WORK_DEFAULT}; DW=${PORT_WORK_WIN:-$(wslpath -w "$D")}; S=$D/port/scratch/rp
T=$1; B=$2; N=${3:-2}; K=$HARNESS_DIR/recomp.py   # the harness: port/gates/vendor/harness, or RECOMP_KIT's
pc_busy_check "$D"; BN=${BUNDLE:-$D/port/bundle-native}; MF=${MACHINE:-$D/port/machine-gate-n.toml}
case "$BN" in "$D"/*) ;; *) echo "time-native: BUNDLE must be under $D" >&2; exit 2;; esac
[ -f "$MF" ] || { echo "time-native: no machine file $MF" >&2; exit 2; }
BW="$DW\\$(printf %s "${BN#"$D"/}" | tr / '\\')"
# a run's launch file, one for each run, with what the harness needs of the game (launch-file.py --harness): the
# native form's is port/configs/gate-scene.json (the bundle, and the patch list forced), the JIT's
# gate-scene-reference.json ("debug.jit", no bundle). The runner starts no game without one.
launch() {  # run scene who
  local name=gate-scene; [ $3 = ref ] && name=gate-scene-reference
  "$W/port/gates/runs/launch-file.py" $name "$D/port/launch/$1.json" "bundle=$BW" "run=$DW\\port\\runs\\$1" --harness $2
}
export RECOMP_AGENT=port RECOMP_MANIFEST=$W/recomp/manifest.toml RECOMP_MACHINE=$MF
[ ! -e "$S/quiet.sh" ] || "$S/quiet.sh" || { echo "the PC is not quiet: no timing"; exit 4; }   # (this PC's quiet check, where install.sh put it)
# after the quiet check: a batch that stops there must leave the shared configuration as it found it
cp "$D/port/Dolphin.ini.gate-nocheats" "$D/user/Config/Dolphin.ini"
runs=()
one() {  # run scene who
  "$BUSY" > /dev/null || { echo "a runner or launcher is running: batch stopped"; "$BUSY"; exit 3; }
  local why; why=$("$W/port/gates/room-for-games.sh" 1) || { echo "$why: batch stopped"; exit 3; }   # Windows' memory
  local A L; L=$(launch "$@") || exit 2
  case $3 in
    ref) A=(--reference);;
    *) A=(--build "$3");;
  esac
  A+=(--arg=--config "--arg=$L")
  python3 -u $K run $1 --scene $2 --config dual-core "${A[@]}" --env SDL_JOYSTICK_HIDAPI_GAMECUBE=0 --label "Port timing" --arg=--title --arg=Port-timing-run--agent--closes-by-itself --max-seconds 150 2>&1 | grep --line-buffered -E "exited early|force kill|stopped after|Error|error|recomp.py:"
  runs+=("$1")
}
for r in $(seq 1 $N); do for scene in race300 racego; do for who in ref ${ALSO:-} "$B"; do one $T-$scene-$who-$r $scene $who; done; done; done
cp "$D/scratch/Dolphin.ini.single" "$D/user/Config/Dolphin.ini"
mkdir -p "$S"; python3 $K time "${runs[@]}" | tee "$S/time-$T.txt"
rm -f "$D/port/runs/$T"-*/*.ram
echo "done $(date +%T)"
