#!/bin/bash
# runs/state.sh NAME FIELD [BUILD] [--dry-run]: a saved state for a gate scene, made fresh in the work folder PORT_WORK:
# the manifest's scene boot-menus (boot, logos, title, the menus with every default, a 30-machine Grand Prix race
# on Twist Road with the accelerator held; the race's first field is about 4,615) is run, and when the probe's log
# has FIELD lines the runner is told to save its state (its automation command save_state) to
# PORT_WORK/derived/NAME.sav. Then the run is stopped.
#   BUILD   a module's name (work/mod-cg-BUILD): the game runs on native code. Without it the run is the
#           reference: the emulator's own compiler, no module.
# The states the gates used until now (race300.sav: race frame about 300; racego.sav: 1.5 s before the green
# light) were recorded by hand under the JIT from a boot with two older codes; nothing of them is kept. The same
# moments from this boot: FIELD 4915 and FIELD 4525.
# Never the same bytes twice: the run is not paced by fields, so the state is taken a few fields after FIELD, and
# a boot's race differs from boot to boot. A scene's reference runs are recorded again after its state.
# The run is the harness's: muted, labelled "Port test", at most 170 s, with SDL_JOYSTICK_HIDAPI_GAMECUBE=0 in the
# game's environment (without it a test game takes the owner's GameCube adapter away from their own game).
#   IMAGE=NAME   the build whose bundle and game folder the run boots (port/bundle-NAME, port/game-NAME; default BUILD)
# Takes the PC itself, after the busy check. Run on 2026-10-08 (the final build's work folder): with BUILD a state is recorded in
# under a minute, asked for 20 to 40 fields after FIELD. Without BUILD it records nothing: the JIT boots the native
# bundle at half a field a second (85 fields in the 170 s). And no state it records serves the gate scenes: their
# reference is the JIT with no bundle, which stands on a state that holds the native form's patched words. The
# gates' two states are kept inputs (kept.tsv); what a recipe needs: inputs.md, "The gate scenes' saved states".
# It needs the harness (vendor/harness, beside runs/). One of the gates' recipes (moved from port/setup on 2026-10-25:
# the gates are private, piconet-gates; the gate scenes' states are their inputs).
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
. "$root/port/setup/lib.sh"
NAME=${1:?state.sh NAME FIELD [BUILD] [--dry-run]}; FIELD=${2:?state.sh NAME FIELD [BUILD] [--dry-run]}; BUILD=""; DRY=""
for a in "${@:3}"; do [ "$a" = --dry-run ] && DRY=1 || BUILD=$a; done
W=${PORT_WORK:?PORT_WORK: the work folder setup.sh made}; WW=$(wslpath -w "$W"); export PORT_WORK_WIN=$WW
K=$HARNESS_DIR/recomp.py   # the harness: the gates' vendor/harness, or RECOMP_KIT's
R=st-$NAME; RUN=$W/port/runs/$R; OUT=$W/derived/$NAME.sav; BUSY=${BUSY_CHECK:-$W/port/scratch/rp/chk.sh}
I=${IMAGE:-${BUILD:?state.sh: IMAGE=NAME, the build whose bundle and game folder are booted}}
export RECOMP_AGENT=${PORT_AGENT:-port} RECOMP_MANIFEST=$root/recomp/manifest.toml RECOMP_MACHINE=$W/port/machine-$([ -n "$DRY" ] && echo n || echo state).toml
who=(--reference); [ -z "$BUILD" ] || who=(--build "$BUILD")
# how the game is started: the launch file port/configs/boot-single-core.json with the image's bundle, what the
# harness needs of the game (launch-file.py --harness), and for the reference run "debug.jit"
LF=$W/port/launch/st-$NAME.json; LFW="$WW\\port\\launch\\st-$NAME.json"
jit=(); [ -n "$BUILD" ] || jit=(--set debug.jit=true)
[ -n "$DRY" ] || "$here/launch-file.py" boot-single-core "$LF" "bundle=$WW\\port\\bundle-$I" "run=$WW\\port\\runs\\$R" --harness boot-menus "${jit[@]}" > /dev/null
harness=(python3 -u "$K" run "$R" --scene boot-menus --config single-core --fields $((FIELD + 240)) "${who[@]}" --env SDL_JOYSTICK_HIDAPI_GAMECUBE=0
         --arg=--config "--arg=$LFW" --not-timing --label "Port test"
         --arg=--title --arg=Port-test--agent-records-a-saved-state--closes-by-itself --max-seconds 170)
if [ -n "$DRY" ]; then
  python3 "$K" --dry-run "${harness[@]:3}" 2>&1 | grep -E "^[0-9]\.|powershell" | cut -c1-220
  echo "when $RUN/probe.csv has $FIELD lines: command=save_state, path=$WW\\derived\\$NAME.sav (into $RUN/auto/commands)"
  exit 0
fi
[ -d "$W/port/user-pristine/GC" ] || { echo "state: no save file in $W/port/user-pristine (runs/profile.sh makes it with a first boot)" >&2; exit 1; }
[ ! -e "$OUT" ] || { echo "state: $OUT exists; a state is never overwritten" >&2; exit 1; }
cd "$root"
sed -e "s|^game = .*|game = \"port/game-$I\"|" "$W/port/machine-n.toml" > "$W/port/machine-state.toml"
wait_while_busy "$BUSY" || exit 3
mkdir -p "$W/derived"
( pc_sharing "$BUSY"; pc_take cpu-window.sh "a saved state: boot to field $FIELD (2 min)" 5
  "${harness[@]}" > "$W/port/st-$NAME.log" 2>&1 &
  run=$!; asked=""
  while kill -0 $run 2> /dev/null; do
    if [ -z "$asked" ] && [ -f "$RUN/probe.csv" ] && [ "$(wc -l < "$RUN/probe.csv")" -ge "$FIELD" ] && [ -d "$RUN/auto/commands" ]; then
      mkdir -p "$RUN/auto/staging"
      printf 'command=save_state\npath=%s\n' "$WW\\derived\\$NAME.sav" > "$RUN/auto/staging/save.txt"
      mv "$RUN/auto/staging/save.txt" "$RUN/auto/commands/save.txt"       # written elsewhere, then renamed: never read half-written
      asked=$(wc -l < "$RUN/probe.csv")
    fi
    sleep 0.2
  done
  wait $run || true
  tail -2 "$W/port/st-$NAME.log"
  [ -n "$asked" ] && echo "state: asked at field $asked of $(wc -l < "$RUN/probe.csv")" || echo "state: the run ended before field $FIELD"
)
[ -s "$OUT" ] || { echo "state: no state was written (see $W/port/st-$NAME.log and $RUN)" >&2; exit 1; }
echo "state: $OUT ($(stat -c %s "$OUT") bytes, $(sha1sum "$OUT" | cut -c1-8))"
