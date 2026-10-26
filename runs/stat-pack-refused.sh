#!/bin/bash
# stat-pack-refused.sh RUN VALUES: does the game itself refuse this stat pack? The pack is handed straight to the
# game, past the launcher (which refuses it first: stat-pack-run.sh shows that too): a launch file of
# port/configs/stat-pack-refused.json with VALUES (base64 of the pack's 6-byte entries) and their own fingerprint,
# started through the harness as replay-check.sh starts a playback. The game must say in its log that the race's
# stat pack is refused, and which value; it then starts no race (it boots to its title), and the run is ended after
# 600 fields. Muted, the window titled by the run.
#   BUILD (w12), BUNDLE, GAME, MACHINE: the parts, as replay-check.sh takes them (stat-pack-run.sh names the
#   staged copy's).
# Prints the game's line. Exit status 0 when the game refused the pack, 1 when it did not say so, 3 when the PC
# was not free.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
KIT=$HARNESS_DIR   # the harness: port/gates/vendor/harness, or RECOMP_KIT's
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
run=${1:?stat-pack-refused.sh RUN VALUES}; values=${2:?stat-pack-refused.sh RUN VALUES}
print=$(python3 -c 'import base64, hashlib, sys; print(hashlib.sha1(b"\x01" + base64.b64decode(sys.argv[1])).hexdigest())' "$values")
manifest=$(mktemp --suffix=.toml); machine=$(mktemp --suffix=.toml); trap 'rm -f "$manifest" "$machine"' EXIT
python3 - "$root/recomp/manifest.toml" "$manifest" <<'PY'
import sys
src, dst = sys.argv[1:3]
t = open(src).read()
scene = ('\n[[scene]]\nname = "adhoc"\nexercises = "a match the game refuses"\nreach = "boot"\ninput = "0:0"\n'
         'fields = 600\nsource = "scratch"\n\n')
k = t.index('# ---- sources of difference between two runs')
open(dst, 'w').write(t[:k] + scene + t[k:])
PY
B=${BUNDLE:-$W/port/bundle-native}; G=${GAME:-$W/port/game-native}
BW="$WW\\$(printf %s "${B#"$W"/}" | tr / '\\')"
sed "s|^game = .*|game = \"${G#"$W"/}\"|" "${MACHINE:-$W/port/machine-n.toml}" > "$machine"
export RECOMP_AGENT=port RECOMP_MANIFEST=$manifest RECOMP_MACHINE=$machine
launch=$("$here/launch-file.py" stat-pack-refused "$W/port/launch/$run.json" "bundle=$BW" "fingerprint=$print" "values=$values" \
         "run=$WW\\port\\runs\\$run" --harness adhoc --manifest "$manifest") || exit 1
tries=0; until "$BUSY" > /dev/null; do tries=$((tries + 1)); [ $tries -le 60 ] || { echo "$run: the busy check said wait for 20 minutes; not run"; exit 3; }; sleep 20; done
LOCKS=${PORT_LOCKS:-$PORT_LOCKS_DEFAULT}; [ -d "$LOCKS" ] || LOCKS=$W
( [ "$LOCKS" -ef "$W" ] || pc_take cpu-window.sh "port: stat pack refused $run (1 min)" 2
  python3 -u "$KIT/recomp.py" run "$run" --scene adhoc --config dual-core --build "${BUILD:-w12}" \
    --not-timing --label "Stat pack refused" --max-seconds 60 --env SDL_JOYSTICK_HIDAPI_GAMECUBE=0 \
    --arg=--title "--arg=Stat-pack-refused-$run--agent--closes-by-itself" --arg=--config "--arg=$launch" ) > "$W/port/launch/$run.log" 2>&1
line=$(cat "$W/port/runs/$run/stderr.txt" "$W/port/runs/$run/fzgx.log" 2> /dev/null | grep -a "the race's stat pack is refused" | head -1 | tr -d '\r')
if [ -n "$line" ]; then echo "$run: ${line#*fzgx: }"; exit 0; fi
echo "$run: the game did not say it refused the pack (see $W/port/runs/$run, $W/port/launch/$run.log)"; exit 1
