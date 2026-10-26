#!/bin/bash
# map-run.sh RUN: one measuring run of the whole-frame map (the speed handbook, section 4): a match race of 30
# machines (the game's AI on the player's seat, 29 CPU racers, a test server and relay on this computer, normal
# speed, muted) through a staged launcher, with the runner's pacing log, the core's rollback log and the external
# sampler (map-sample.cs) attached to the game's process. Nothing of the game is changed: the sampler is another
# process that suspends one thread, reads where it is and lets it go. Takes TIMING.lock for the run; at most 175 s.
#   LAUNCHER=NAME        the staged launcher (default launcher-dev); DATA_NAME its data folder (default map-data)
#   FROM=RUN             the same race as an earlier run's (set-up and seeds): what two runs must share to be compared
#   LAPS (3), COURSE (16: Casino Palace: Split Oval)
#   RB=EVERY:DEPTH[,DEPTH]   forced rollbacks (the launch file's debug.forceRollback), the depths in turn
#   SAMPLE=0             no sampler (the unperturbed run of a pair); PERIOD (400 us between samples), OTHERS (4)
#   COUNT=1              the counting run: the probe without hashes, with its task timers and task list
#   NOHASH=1             the probe without its hashes (it is on in every run: launcher-run.sh counts fields by it)
#   REFERENCE=1          on the runner's JIT (needs a launcher staged with the fork's kind of bundle)
#   TOOLS=FOLDER         where map-sample.exe is (default <work>/scratch/map/tools); OFFSETS: the runner's five
#                        offsets, which belong to ONE runner build (map-offsets.py prints them; the script refuses a
#                        runner whose SHA-1 is not RUNNER_SHA)
#   SCRIPTS=FOLDER       another checkout's port/gates/runs (one whose test server is built)
# Output: <work>/port/runs/RUN (pace.csv, rb.csv, samples.txt, probe.csv, quiet.txt, hashes.txt, fzgx.log).
# Nothing of a run is committed: runs are game data.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); runs=${SCRIPTS:-$here}
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
R=$1; RUN=$W/port/runs/$R; RUNW="$WW\\port\\runs\\$R"; L=${LAUNCHER:-launcher-dev}
T=${TOOLS:-$W/scratch/map/tools}; B=$W/port/scratch/map-match; mkdir -p "$B"
RUNNER_SHA=${RUNNER_SHA:-8ecdb2c9}; OFFSETS=${OFFSETS:-"system=0xEE7680 ppc=0x282B10 timing=0xB0 core=0x14900 guest=0x80308"}
exe=$W/port/$L/recomp/moderngekko-run.exe
if [ "${SAMPLE:-1}" != 0 ]; then
  [ -x "$T/map-sample.exe" ] || { echo "map-run: no $T/map-sample.exe (build it: the head of port/speed/map-sample.cs)" >&2; exit 2; }
  [ "$(sha1sum "$exe" | cut -c1-8)" = "$RUNNER_SHA" ] || { echo "map-run: $L's runner is not $RUNNER_SHA: the sampler's offsets are another build's (map-offsets.py)" >&2; exit 2; }
fi
js() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }
GD="\"rollbackLog\":$(js "$RUNW\\rb.csv")"
[ -z "${RB:-}" ] || GD="$GD,\"forceRollback\":{\"every\":${RB%%:*},\"depths\":[${RB#*:}]}"
[ -z "${NOHASH:-}${COUNT:-}" ] || GD="$GD,\"probeNoHash\":true"
[ -z "${COUNT:-}" ] || GD="$GD,\"taskTimers\":true,\"taskList\":true"

pc_take timing-lock.sh "speed: map run $R (3 min)" 5
"$BUSY" > /dev/null || { echo "$R: a runner or launcher is running (the busy check): no run"; exit 3; }
QUIET=$([ ! -e "$W/port/scratch/rp/quiet.sh" ] || "$W/port/scratch/rp/quiet.sh" 2>&1 || true)
COURSE=${COURSE:-16} LAPS=${LAPS:-3} MACHINE=2 PLAYER=Map SERVER_SECONDS=300 "$runs/match-file.sh" "$B/$R.json" ${FROM:+"$B/$FROM.json"} > "$B/$R.match.log"
[ -z "${REFERENCE:-}" ] || export REFERENCE=1
status=0
HAVE_LOCK=1 AUTOPILOT=1 PACE=1 MATCH=$B/$R.json TITLE="Map-test-$R--agent--closes-by-itself" SHOTS="${SHOTS:-}" GAME_DEBUG="$GD" \
  LAUNCHER=$L DATA_NAME=${DATA_NAME:-map-data} "$runs/launcher-run.sh" "$R" match-race > "$B/$R.run.log" 2>&1 &
RUNNER_JOB=$!
# launcher-run.sh empties the run's folder first: wait for the launcher's process ID, then find the game under it
for _ in $(seq 1 240); do [ -s "$RUN/pid.txt" ] && break; sleep 0.25; done
if [ -s "$RUN/pid.txt" ]; then
  PID=$(tr -d '\r\n' < "$RUN/pid.txt"); GAME=""
  echo "$QUIET" > "$RUN/quiet.txt"
  { sha1sum "$exe" "$W/port/$L/recomp/gGFZE01_recomp.dll" "$W/port/$L/recomp/fzgx/mod.bin" | sed "s|$W/port/||"; echo "launcher $L; RB=${RB:-none} SAMPLE=${SAMPLE:-1} COUNT=${COUNT:-} NOHASH=${NOHASH:-} REFERENCE=${REFERENCE:-}"; } > "$RUN/hashes.txt"
  for _ in $(seq 1 60); do
    GAME=$(powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"ParentProcessId=$PID and Name='moderngekko-run.exe'\").ProcessId" < /dev/null 2> /dev/null | tr -d '\r\n')
    [ -z "$GAME" ] || break; sleep 0.3
  done
  echo "$R: launcher pid=$PID, game pid=${GAME:-none}"
  if [ -n "$GAME" ] && [ "${SAMPLE:-1}" != 0 ]; then
    "$T/map-sample.exe" "$GAME" "$RUNW\\samples.txt" $OFFSETS seconds=190 others="${OTHERS:-4}" period="${PERIOD:-400}" > "$RUN/sampler.log" 2>&1 &
  fi
fi
wait $RUNNER_JOB || status=$?
touch "$RUN/samples.txt.stop" 2> /dev/null || true; sleep 1.5
kill "$(cat "$B/server.pid")" 2> /dev/null || true
tail -1 "$B/$R.run.log"
echo "$R: done at $(date +%T); $(grep -c '^F' "$RUN/pace.csv" 2> /dev/null || echo 0) fields, $(grep -c '^C' "$RUN/samples.txt" 2> /dev/null || echo 0) CPU-thread samples; $(tail -1 "$RUN/quiet.txt" 2> /dev/null)"
exit $status
