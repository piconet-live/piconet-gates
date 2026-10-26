#!/bin/bash
# freeze-run.sh RUN: the freeze report end to end (protocol/formats.md sections 2, 6 and 7).
# One match race through a staged launcher, as match-run.sh makes it (one player's seat driven by the game's AI
# among 29 CPU racers, a test server in WSL), with the game's "debug.standStill": the game's thread sleeps for 2.6 s
# before step 150 (the countdown), for 2.6 s before step 1,000 and for 30 s before step 1,500 (the race). The stand
# in the countdown must not be reported (the first report there waits 5 s). The first in the race must be reported
# once and then said to move again. In the second, when its second report is in the log (4 s), this script closes
# the game's window from outside, as the launcher or the taskbar does; the game goes when the stand is over. The
# log must then hold both freezes' lines, the stop line that names the close and says how long the game had stood,
# and a summary line with freezes=2, stuck=yes and waits=0 (reports/freeze-report.py --expect-test judges it; its
# last line is this script's: "freeze RUN: PASS" or "FAIL: why").
#   CLOSE=0         nobody closes the window: the 30 s stand ends by itself, the test relay has given the seat up
#                   meanwhile, the game then waits for the relay's inputs (a wait, no freeze) and loses the race
#                   after 15 s. Not judged: the reader's lines are printed (a wait counted apart, a race that ends
#                   under a wait, a stop later that finds no freeze: "stuck=no").
# Bounded: under 2 minutes (CLOSE=0: launcher-run.sh's 170 s), muted, the test's name in the window's title, no
# controller adapter opened.
#   LAUNCHER=NAME   the staged launcher (default launcher-dev: its runner must have the freeze report)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); cd "$here/../../.."
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; R=${1:?freeze-run.sh RUN}
B=$W/port/scratch/match; mkdir -p "$B"; L=${LAUNCHER:-launcher-dev}; DN=$L-freeze-data; RUN=$W/port/runs/$R
pc_take timing-lock.sh "port: freeze report $R (2 min)" 4
COURSE=16 LAPS=1 MACHINE=2 PLAYER=Port SERVER_SECONDS=240 port/gates/runs/match-file.sh "$B/$R.json" > "$B/$R.match.log"
# the close from outside: when the second freeze's second report is in the game's log, the main window of the game
# (the launcher's one child, found by its parent's ID) is sent the close message
(
  LOG=$W/port/$DN/recomp-user/Logs/fzgx.log; rm -f "$LOG"   # (the run before's: this run's game writes a new one)
  for _ in $(seq 1 600); do
    [ "${CLOSE:-1}" != 0 ] || break
    if grep -aq 'fzgx: freeze: no game frame .*report 2 of this freeze' "$LOG" 2> /dev/null; then
      PID=$(tr -d '\r\n' < "$RUN/pid.txt")
      powershell.exe -NoProfile -Command "\$g = (Get-CimInstance Win32_Process -Filter \"ParentProcessId=$PID and Name='moderngekko-run.exe'\").ProcessId; if (\$g) { [void](Get-Process -Id \$g).CloseMainWindow() }" < /dev/null > "$RUN.close.log" 2>&1 || true
      break
    fi
    sleep 0.25
  done
) &
closer=$!
status=0   # launcher-run.sh's: 1 here by design (the game is closed from outside: "GONE ... no end line of its own")
HAVE_LOCK=1 AUTOPILOT=1 PACE=1 MATCH=$B/$R.json TITLE="Freeze-test-$R--agent--closes-by-itself" LAUNCHER=$L DATA_NAME=$DN SHOTS="" \
  GAME_DEBUG='"standStill":{"steps":[150,1000,1500],"tenths":[26,26,300]}' port/gates/runs/launcher-run.sh "$R" match-race || status=$?
kill "$closer" 2> /dev/null || true
kill "$(cat "$B/server.pid")" 2> /dev/null || true
cp "$W/port/$DN/recomp-user/race-summary.txt" "$RUN/race-summary.txt" 2> /dev/null || true
[ "${CLOSE:-1}" != 0 ] || { python3 port/gates/reports/freeze-report.py "$RUN" | tee -a "$RUN/end.txt"; exit 0; }
python3 port/gates/reports/freeze-report.py "$RUN" --expect-test | tee -a "$RUN/end.txt"
exit "${PIPESTATUS[0]}"
