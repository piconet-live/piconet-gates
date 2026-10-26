#!/bin/bash
# board-run.sh RUN: the launcher's status board end to end (protocol/formats.md section 8). One match race
# through a staged launcher, as match-run.sh makes it (the game's AI on the player's seat among 29 CPU racers, a test
# server in WSL), headless (the runner's --headless), with the game's "debug.standStill": the game's thread sleeps
# for 12 s before step 1,200 (a freeze on purpose: no game frame, so no heartbeat). The launcher's own lines (its
# standard output, RUN/stdout.txt: BoardLines) must show the board taken, the phases through the countdown and the
# race, race snapshots, the stand judged a freeze after 10 s and the game moving again, the game's own freeze report
# among its events, and the board's last line when the game has ended; the game's launch file names the board and
# no live feed. reports/board-report.py judges it; its last line is this script's: "board RUN: PASS" or "FAIL: why".
# Bounded: launcher-run.sh's 170 s, muted, the test's name in the window's title, no controller adapter opened.
#   LAUNCHER=NAME   the staged launcher (default launcher-dev: its runner and launcher must have the board)
#   WINDOW=1        with the game's window (no --headless)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); cd "$here/../../.."
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; R=${1:?board-run.sh RUN}
B=$W/port/scratch/match; mkdir -p "$B"; L=${LAUNCHER:-launcher-dev}; DN=$L-board-data; RUN=$W/port/runs/$R
pc_take timing-lock.sh "port: status board $R (3 min)" 4
COURSE=16 LAPS=1 MACHINE=2 PLAYER=Port SERVER_SECONDS=240 port/gates/runs/match-file.sh "$B/$R.json" > "$B/$R.match.log"
RA=--headless; [ "${WINDOW:-0}" != 1 ] || RA=""
status=0   # launcher-run.sh's; the verdict is the report's
HAVE_LOCK=1 AUTOPILOT=1 MATCH=$B/$R.json TITLE="Board-test-$R--agent--closes-by-itself" LAUNCHER=$L DATA_NAME=$DN SHOTS="" \
  RUNNER_ARGS="$RA" GAME_DEBUG='"standStill":{"steps":[1200],"tenths":[120]}' port/gates/runs/launcher-run.sh "$R" match-race || status=$?
kill "$(cat "$B/server.pid")" 2> /dev/null || true
cp "$W/port/$DN/recomp-user/launch.json" "$RUN/game-launch.json" 2> /dev/null || true
echo "board $R: launcher-run.sh ended with status $status"
python3 port/gates/reports/board-report.py "$RUN" | tee -a "$RUN/end.txt"
exit "${PIPESTATUS[0]}"
