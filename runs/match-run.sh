#!/bin/bash
# match-run.sh RUN [ref]: one match race through a staged launcher, for the gates of the native form
# (the port-recomp notes 5.11): Casino Palace: Split Oval, one lap, the game's AI on the player's seat among 29
# CPU racers, the manifest's match-race scene (A tapped every two seconds, which leaves the results; the game then
# stops by itself). Normal speed (the relay paces a match), muted, the window shown without taking the focus, the
# runner's pacing log in <work>/port/runs/RUN/pace.csv. `ref`: on the runner's JIT, which needs a launcher staged
# with the fork's kind of bundle (the reference configuration).
#   FROM=RUN       the same set-up as an earlier run's match: two runs of one set-up are one race, compared per race
#                  frame with run-summary.py RUN1 RUN2
#   LAUNCHER       the staged launcher (default launcher-dev; the JIT reference: launcher-ref)
#   LAPS (1), RUN_ENV, RUNNER_ARGS, SHOTS, RECORD (default: the launcher records into its replay folder)
# The machine is taken first (TIMING.lock), then the match is made.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); cd "$here/../../.."
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; R=$1; B=$W/port/scratch/match; mkdir -p "$B"
pc_take timing-lock.sh "port: match race $R (3 min)" 5
COURSE=16 LAPS=${LAPS:-1} MACHINE=2 PLAYER=Port SERVER_SECONDS=300 port/gates/runs/match-file.sh "$B/$R.json" ${FROM:+"$B/$FROM.json"} > "$B/$R.match.log"
[ "${2:-}" = ref ] && export REFERENCE=1
status=0   # launcher-run.sh's: 1 when the game crashed, froze, never started or had to be ended
HAVE_LOCK=1 AUTOPILOT=1 RECORD="${RECORD:-}" RUN_ENV="${RUN_ENV:-}" PACE=1 MATCH=$B/$R.json TITLE="Match-test-$R--agent--closes-by-itself" SHOTS="${SHOTS:-}" \
  LAUNCHER=${LAUNCHER:-launcher-dev} RUNNER_ARGS="${RUNNER_ARGS:-}" port/gates/runs/launcher-run.sh "$R" match-race || status=$?
kill "$(cat "$B/server.pid")" 2> /dev/null || true
exit $status
