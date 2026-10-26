#!/bin/bash
# practice-run.sh NAME: a scripted practice (port/configs/practice.json, or CONFIG=FILE: one seat, no relay, the
# rewind; the AI drives the seat and a pad script saves, pauses, scrubs, resumes and loads) through the harness,
# uncapped and muted, in a window titled by the run that closes by itself after FIELDS fields (default 9000) or
# MAXS seconds (default 170). Then its replay ($W/port/runs/NAME/practice.fzrp) is played back with replay-check.sh
# (NAME-pb): every step must match. Prints the practice's own lines (fzgx: practice: ...) and the check's verdict.
# BUILD, BUNDLE, GAME, MACHINE as for replay-check.sh (all named: there is no default for a practice).
# HEADLESS=1: no window (the harness's --headless: the runner's null video backend), the playback too.
# PLAYBACK=NAME: the playback's launch file (default playback: as the race, as every playback since 0.3.0, a
# practice whose mines come back too).
# PACE=1: a pacing run instead: at normal speed (the emulator's speed limit at 1, in a user folder of the run's own
# under port/scratch/practice-pace), with the runner's pacing log in RUN/pace.csv (pace-report.py,
# pace-resume.py), the window shown without taking the focus, the machine taken with TIMING.lock.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
KIT=$HARNESS_DIR   # the harness: port/gates/vendor/harness, or RECOMP_KIT's
[ $# = 1 ] && [ -n "${BUILD:-}" ] && [ -n "${BUNDLE:-}" ] && [ -n "${GAME:-}" ] && [ -n "${MACHINE:-}" ] \
  || { sed -n 2,7p "$0"; exit 2; }
name=$1; run=$W/port/runs/$name
"$BUSY" > /dev/null || { echo "practice-run: the busy check says wait"; exit 3; }
why=$("$here/../room-for-games.sh" 1) || { echo "practice-run: not run: $why"; exit 3; }
[ -z "${PACE:-}" ] || pc_take timing-lock.sh "port: practice pacing run $name (3 min)" 4
manifest=$(mktemp --suffix=.toml); machine=$(mktemp --suffix=.toml); trap 'rm -f "$manifest" "$machine"' EXIT
python3 - "$root/recomp/manifest.toml" "$manifest" "${FIELDS:-9000}" <<'PY'
import sys
src, dst, fields = sys.argv[1:4]
t = open(src).read()
scene = ('\n[[scene]]\nname = "adhoc"\nexercises = "a practice"\nreach = "boot"\ninput = "0:0"\n'
         'fields = %s\nsource = "scratch"\n\n' % fields)
k = t.index('# ---- sources of difference between two runs')
open(dst, 'w').write(t[:k] + scene + t[k:])
PY
sed "s|^game = .*|game = \"${GAME#"$W"/}\"|" "$MACHINE" > "$machine"
set_pace=()
if [ -n "${PACE:-}" ]; then   # a user folder of the run's own with the speed limit at 1, and the pacing log
  paced=port/scratch/practice-pace/$name; rm -rf "${W:?}/$paced"; mkdir -p "$W/$paced"
  pristine=$(sed -n 's/^user_pristine = "\(.*\)"/\1/p' "$MACHINE")
  cp -r "$W/$pristine" "$W/$paced/user-pristine"
  sed -i 's/^EmulationSpeed = .*/EmulationSpeed = 1.0/' "$W/$paced/user-pristine/Config/Dolphin.ini"
  sed -i -e "s|^user_pristine = .*|user_pristine = \"$paced/user-pristine\"|" -e "s|^user = .*|user = \"$paced/user\"|" \
    -e "s|^config = .*|config = \"$paced/user/Config/Dolphin.ini\"|" -e '/^config_pristine = /d' "$machine"
  set_pace=(--set 'debug.paceLog={run}\\pace.csv' --set debug.windowNoActivate=true)
fi
BW="$WW\\$(printf %s "${BUNDLE#"$W"/}" | tr / '\\')"
launch=$("$here/launch-file.py" "${CONFIG:-practice}" "$W/port/launch/$name.json" "bundle=$BW" \
         "run=$WW\\port\\runs\\$name" "${set_pace[@]}" --harness adhoc --manifest "$manifest") || exit 2
RECOMP_AGENT=${PORT_AGENT:-practice} RECOMP_MANIFEST=$manifest RECOMP_MACHINE=$machine \
  python3 -u "$KIT/recomp.py" run "$name" --scene adhoc --config dual-core --build "$BUILD" \
  --not-timing --label "Practice check" --max-seconds "${MAXS:-170}" --env SDL_JOYSTICK_HIDAPI_GAMECUBE=0 \
  ${HEADLESS:+--headless} \
  --arg=--title "--arg=Practice-check-$name--agent--closes-by-itself" --arg=--config "--arg=$launch" 2>&1 | tail -3
cp "$W/port/launch/$name.json" "$run/launch.json" 2> /dev/null
grep -a "fzgx: practice\|differs\|Error\|error" "$run/stderr.txt" | head -60
[ -f "$run/practice.fzrp" ] || { echo "practice-run $name: no replay was written"; exit 1; }
# (the practice's own CONFIG, FIELDS and MAXS are not the playback's)
env -u FIELDS -u MAXS CONFIG="${PLAYBACK:-playback}" "$here/../replay-check.sh" "$name-pb" "$run/practice.fzrp"
