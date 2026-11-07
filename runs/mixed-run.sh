#!/bin/bash
# mixed-run.sh RUN LAUNCHER LAUNCHER [LAUNCHER...]: games of different builds in one race (row `mixed` of
# ../gates.sh). One game for each staged launcher folder named (<work>/port/LAUNCHER, a folder twice: two games of
# it), each on that folder's own runner, module and image, in a data folder of this script's own
# (<work>/port/gate-mixed-data-pN: nothing is written into a launcher folder). The race is made as pair-run.sh makes
# one: a test server in WSL (the coordinator and its relay), simulated players, and a stand-in for each game whose
# seat the game takes from its match file. A match file names no build and the relay asks for none, so nothing here
# depends on the coordinator's rule that a lobby holds one build (Quick Play's way in does: a launcher's hello names
# its build and Coordinator.Lobby.cs puts it with its own). Every game records its replay, and with it the checksum
# of every step: ../gate-judge.py mixed RUN says whether the builds ran one race.
# The conditions a difference would show under, all on unless said:
#   LAGS ("30 90")  each game's test lag in ms, in turn (a third game takes the first again)
#   JITTERS ("0")   each game's jitter in ms, in turn: its packets held up to that much longer (0: none)
#   ROLLBACKS ('{"every":7,"depths":[6,12]}')  rollbacks forced in every game (the game's "debug.forceRollback")
#   WALL (1)        the game whose own seat a pad script drives into the wall after the green light (the stick hard
#                   over for six seconds; then only A tapped every two seconds, which leaves the results when
#                   they come, as every game's script does). 0: none. Every other game's seat is driven by the
#                   game's AI, to the finish
#   BOTCOUNT (6)    simulated players (the game's AI with bursts of real inputs: mispredictions that are not forced);
#                   computer racers fill the race to 30 seats. 30 less the games: 30 player seats, no computer racer
#   FINISH_LIMIT (10)  the race ends for everyone so many seconds after the first finish (the server's rule)
#   STATES ("1500,1501")  every game writes the machines' state of those steps (RUN-N/trace.csv.states): the judge
#                   reads the wall hits there, and what differs between two games' states of one step
#   ALTER=GAME:STEP the control: that game's state is altered before STEP (the game's "debug.alterStep"), which the
#                   judge must find: FAIL, first at that step. Give STATES=STEP,STEP+2 to see the word
#   DELAYS ("2")    each game's input delay in steps, in turn (the match file's "delay": a game's own setting, which
#                   no other game is told). "0 2": two games of one race with different delays. DELAY: all of them
#   SETTINGS ("")   each game's launcher settings, in turn, separated by ";": more members of the settings.json its
#                   launcher starts with ('"present":"console";': game 1 shows its pictures as a console, game 2 as ever).
#                   Only a launcher that knows a member takes it (launcher-run.sh's SETTINGS)
#   PULSES="1 2"    those games' own seats are driven by a pad script of presses at known fields instead of the AI
#                   or the wall script: the accelerator held, and in every second the stick hard right for four
#                   fields, Z for four fields and the accelerator let go for six. ../reports/latency-report.py follows
#                   each press from the pad to the picture. Such a seat does not finish (the server's FINISH_LIMIT
#                   ends its race, ten seconds after the first racer's finish)
#   ROLLBACKS=none  no rollback is forced: only those the simulated players' inputs cause
#   DATA_PREFIX     the games' data folders are <work>/port/DATA_PREFIX-pN (default: gate-mixed-data)
#   EARLY_CLOSE (1) 0: the test server's relay closes every frame at its deadline (--no-early-close), never as soon
#                   as every seat's input is there: the relay before 14 October 2026, for comparisons
#   FULL="2"        those games' windows go to full screen FULL_AFTER (30) seconds after their start, by the
#                   window's own command (full-screen.ps1: what the strip's button sends), and stay there; each
#                   asks the video backend for its own, exclusive full screen although its window has no focus
#                   (the game's "debug.fullScreenWithoutFocus"). The screen of that game's window is taken for
#                   the race; FULL_AT="X Y" moves the window there first (another monitor than the main one).
#                   RUN-N/full-screen.txt says what was sent, the game's log what came of it
#   RULES ("")      more of the test server's race rules, as its options ("--cpu-level 0 --boost-start --restore"):
#                   rules every game of a race takes from the match start, for a race of builds under other rules
#   COURSE (8), LAPS (1), OC (6.0), DEBUG (more members of every game's "debug" part), CLOCKRATE (the WSL
#                   clock against Windows', measured by clock-rate.py once the PC is taken)
# Bounded: every game 170 s at most (launcher-run.sh), muted, its window titled by the run and never taking the
# focus, SDL_JOYSTICK_HIDAPI_GAMECUBE=0. The PC is taken first (TIMING.lock), then the busy check must say that no
# game and no launcher is up, and Windows must have the memory for the games (room-for-games.sh). While the race
# runs the busy check is asked every ten seconds: a runner or a launcher that is not this run's (the owner has
# started to play) ends this run's games at once, each by its process ID, and the script ends with status 3.
# Leaves <work>/port/runs/RUN-N (race.fzrp, rb.csv, trace.csv.states, probe.csv, pace.csv, stderr.txt) and
# <work>/port/scratch/mixed/RUN.* (games.tsv: each game's folder, build, lag and driver; the server's and the
# simulated players' logs; RUN-N.run.log).
# Exit status: 1 when a game crashed, froze, never started or had to be ended; 3 when nothing was started or the
# run was given up for the owner; 2 for a call it cannot make sense of.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); cd "$here/../../.."
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
[ $# -ge 3 ] || { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit 2; }
R=$1; shift; L=("$@"); N=${#L[@]}; B=$W/port/scratch/mixed; mkdir -p "$B"
for i in "${!L[@]}"; do
  l=${L[$i]%/}; l=${l#"$W/port/"}; L[$i]=$l
  case "${l,,}" in   # in small letters: a Windows drive finds port\launcher under Launcher too
    ""|*/*|*\\*|.*) echo "mixed-run: $l: a game's build is a folder of $W/port (launcher-NAME)" >&2; exit 2;;
    launcher|launcher-prev|launcher-c|launcher-ctl-button*|launcher-game-window*)
      echo "mixed-run: $l is a copy of the owner's and is never raced on by a script: name a staged test copy" >&2; exit 2;;
  esac
  [ -f "$W/port/$l/Launcher.App.exe" ] && [ -f "$W/port/$l/recomp/gGFZE01_recomp.dll" ] || {
    echo "mixed-run: $W/port/$l is no staged launcher (port/build/stage-launcher.sh makes one)" >&2; exit 2; }
done
read -ra lags <<< "${LAGS:-30 90}"; read -ra jitters <<< "${JITTERS:-0}"; wall=${WALL:-1}; n=${BOTCOUNT:-6}; alter=${ALTER:-}
read -ra delays <<< "${DELAYS:-${DELAY:-2}}"; IFS=';' read -ra settings <<< "${SETTINGS:-};"; pulses=${PULSES:-0}
for d in "${delays[@]}"; do case "$d" in [0-2]) ;; *) echo "mixed-run: DELAYS: $d is no input delay (0, 1 or 2 steps: the game refuses more)" >&2; exit 2;; esac; done
[ "$((n + N))" -le 30 ] || { echo "mixed-run: $N games and $n simulated players are more than 30 seats" >&2; exit 2; }
case "$alter" in ""|[1-9]:[0-9]*) ;; *) echo "mixed-run: ALTER is GAME:STEP (2:1500)" >&2; exit 2;; esac
source "$here/../../setup/app.sh"; . "$here/race-lib.sh"   # race_server, race_bots, stop_ours, end_launcher
[ -f "$APP_SERVER" ] && [ -f "$APP_BOTS" ] || { echo "mixed-run: build the application first ($APP_BUILD)" >&2; exit 2; }
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
# This run's own processes, by process ID: each game's launcher (the ID launcher-run.sh wrote into RUN-N/pid.txt) and
# the game that launcher started (its child of the runner's name). Not by a text in the command line: a launcher on
# its way out has none and passed as a stranger, which ended a finished race with status 3, and a stranger whose
# command line held the run's name was hidden.
ours() {
  local i p ids="" filter=""
  for i in $(seq 1 "$N"); do
    [ -s "$W/port/runs/$R-$i/pid.txt" ] || continue   # (not started yet)
    p=$(tr -d '\r\n' < "$W/port/runs/$R-$i/pid.txt")
    case "$p" in ""|*[!0-9]*) continue;; esac
    ids="$ids $p"; filter="$filter${filter:+ or }ParentProcessId=$p"
  done
  [ -n "$ids" ] || return 0
  echo "$ids $(powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"($filter) and Name='moderngekko-run.exe'\").ProcessId" < /dev/null 2> /dev/null | tr -d '\r' | tr '\n' ' ')"
}
# the runners, launchers and emulators that are up and are not this run's (the busy check's lines: "PID NAME ...")
others() {
  local mine pid rest; mine=" $(ours) "
  "$BUSY" 2> /dev/null | grep -a '^[0-9][0-9]* ' | while read -r pid rest; do
    case "$mine" in *" $pid "*) ;; *) echo "$pid $rest";; esac
  done || true
}

pc_take timing-lock.sh "port: mixed builds $R ($N games, 3 min)" 5
end_games() {   # this run's launchers and the game each started, by process ID: only when the owner has begun to play
  local i p
  for i in $(seq 1 "$N"); do
    p=$(tr -d '\r\n' < "$W/port/runs/$R-$i/pid.txt" 2> /dev/null || true); [ -n "$p" ] || continue
    end_launcher "$p"
  done
}
trap 'stop_ours; pc_release' EXIT
# (a run of this name before left its launchers' IDs: they are nobody's now, and no process of this run is up yet)
for i in $(seq 1 "$N"); do rm -f "$W/port/runs/$R-$i/pid.txt"; done
for try in 1 2 3 4 5 6 7; do
  up=$(others); [ -n "$up" ] || break
  [ $try != 7 ] || { echo "mixed-run $R: not started: a game or a launcher is up (the busy check): $(echo "$up" | head -1 | cut -c1-120)" >&2; exit 3; }
  sleep 20
done
why=$(port/gates/room-for-games.sh "$N") || { echo "mixed-run $R: not started: $why" >&2; exit 3; }

# ---- the race: a test server, the simulated players, and a stand-in for each game
host=${RELAY_HOST:-$(ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1)}; rate=${CLOCKRATE:-$(python3 "$here/clock-rate.py")}
stop_ours; sleep 1
rm -f "$B/$R".h* "$B/$R"-*.json "$B/$R.games.tsv"
race_server 300 --no-announce --allow-ai-inputs --start-timeout 240 --voting-minimum 2 --course "${COURSE:-8}" \
    --laps "${LAPS:-1}" --clock-rate "$rate" --finish-limit-seconds "${FINISH_LIMIT:-10}" \
    $([ "${EARLY_CLOSE:-1}" != 0 ] || echo --no-early-close) ${RULES:-} || exit 1
fill=""; [ "$((n + N))" -ge 30 ] || fill="--cpu-voters 30"
if [ "$n" -gt 0 ]; then
  race_bots "$B/$R.bots.log" 290 --server ws://127.0.0.1:$TEST_PORT/ws --count "$n" --name-prefix Bot --offset $((N + 1)) --expect $((n + N)) \
      --start-voters "$n" $fill --no-checksums --ai --frames 14000 --timeout 280 --clock-rate "$rate"
fi
timeout 120 dotnet "$APP_BOTS" --server ws://127.0.0.1:$TEST_PORT/ws --count "$N" --name-prefix Port --handoff "$B/$R.h{0}" \
    --offset 1 --expect $((n + N)) --start-voters "$N" $fill --clock-rate "$rate" > "$B/$R.standin.log" 2>&1 || true
for i in $(seq 0 $((N - 1))); do
  [ -s "$B/$R.h$i" ] || { echo "mixed-run: no match started (see $B/$R.server.log, $B/$R.standin.log)" >&2; exit 1; }
  python3 - "$B/$R.h$i" "$B/$R-$((i + 1)).json" "$host" "${delays[$((i % ${#delays[@]}))]}" "${OC:-6.0}" <<'PY'
import json, sys
handoff, out, host, delay, oc = sys.argv[1:6]
match = json.load(open(handoff))
json.dump({"match": match, "relayHost": host, "delay": int(delay), "overclock": float(oc), "otherSounds": "quieter"}, open(out, "w"))
s = match["setup"]
print(f"match {match['matchId']}, seat {match['seat']} of {len(s['seats'])} ({sum(1 for x in s['seats'] if not x.get('playerId'))} CPU), "
      f"course {s['course']}, {s['laps']} lap(s), input delay {delay}")
PY
done
rm -f "$B/$R".h*
# The seat on the wall: the accelerator and the stick hard over for seven seconds from just before the green light
# (the race's frames begin near field 1,800, the light is six seconds later); then A tapped every two seconds, as
# the scene's own script taps it for the seats the AI drives: the tap that follows the results leaves them, so
# every game's recording ends within a tap of the others'.
grind="0:0,2100:0100:255:128,2520:0:128:128$(for f in $(seq 2640 120 8880); do printf ',%d:0100,%d:0' "$f" $((f + 6)); done)"
# The seat of presses at known fields (PULSES): from the green light on, in every second the accelerator comes back,
# the stick is hard right for four fields, Z is down for four fields and the accelerator is let go for six: eight
# changes of the seat's control record a second, each at a field the script names.
pulse="0:0,2100:0100$(for f in $(seq 2160 60 8880); do printf ',%d:0100,%d:0100:255:128,%d:0100,%d:0110,%d:0100,%d:0' "$f" $((f + 10)) $((f + 14)) $((f + 30)) $((f + 34)) $((f + 54)); done)"
sha() { sha1sum "$1" | cut -d' ' -f1; }
forced=${ROLLBACKS:-}; [ -n "$forced" ] || forced='{"every":7,"depths":[6,12]}'; states=${STATES:-1500,1501}
js() { printf '%s' "$1" | sed 's/\\/\\\\/g'; }

# ---- the games, each from its own launcher folder
games=()
for i in $(seq 1 "$N"); do
  l=${L[$((i - 1))]}; lag=${lags[$(((i - 1) % ${#lags[@]}))]}
  game="\"rollbackLog\":\"$(js "$WW\\port\\runs\\$R-$i\\rb.csv")\""
  [ "$forced" = none ] || game="$game,\"forceRollback\":$forced"
  jit=${jitters[$(((i - 1) % ${#jitters[@]}))]}; [ "$jit" = 0 ] || game="$game,\"jitterMs\":$jit"
  game="$game,\"trace\":\"$(js "$WW\\port\\runs\\$R-$i\\trace.csv")\",\"traceStates\":[$states]"
  [ "${alter%%:*}" != "$i" ] || game="$game,\"alterStep\":${alter#*:}"
  [ -z "${DEBUG:-}" ] || game="$game,$DEBUG"
  full=""; case " ${FULL:-} " in *" $i "*) full=1; game="$game,\"fullScreenWithoutFocus\":true";; esac
  case " $pulses " in *" $i "*) drive=pulses; auto=0;; *) if [ "$wall" = "$i" ]; then drive=wall; auto=0; else drive=ai; auto=1; fi;; esac
  delay=${delays[$(((i - 1) % ${#delays[@]}))]}; more=${settings[$(((i - 1) % ${#settings[@]}))]:-}
  build="$(sha "$W/port/$l/recomp/fzgx/mod.bin")/$(sha "$W/port/$l/recomp/gGFZE01_recomp.dll")/$(sha "$W/port/$l/recomp/moderngekko-run.exe")"
  # what the judge holds the game's own files against: its folder, build (image/module/runner), lag, driver, the
  # step it was altered before (-: none), the forced rollbacks and the steps whose state it writes
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$i" "$l" "$build" "$lag" "$drive" "$([ "${alter%%:*}" = "$i" ] && echo "${alter#*:}" || echo -)" \
      "$forced" "$states" "$delay" "${more:--}" >> "$B/$R.games.tsv"
  echo "game $i: $l (build $(echo "$build" | sed -E 's|([0-9a-f]{8})[0-9a-f]*|\1|g')), test lag $lag ms, input delay $delay, its seat: $drive${more:+, launcher settings: $more}"
  (
    if [ $drive = wall ]; then export INPUT="$grind"; elif [ $drive = pulses ]; then export INPUT="$pulse"; else unset INPUT; fi
    HAVE_LOCK=1 PACE=1 MATCH=$B/$R-$i.json TITLE="Mixed-test-$R-game-$i--agent--closes-by-itself" SHOTS="" LAUNCHER=$l SETTINGS="$more" \
      DATA_NAME=${DATA_PREFIX:-gate-mixed-data}-p$i AUTOPILOT=$auto LAG=$lag GAME_DEBUG="$game" port/gates/runs/launcher-run.sh "$R-$i" match-race
  ) > "$B/$R-$i.run.log" 2>&1 &
  games+=($!)
  sleep 1
  if [ -n "$full" ]; then
    (
      for _ in $(seq 1 120); do [ -s "$W/port/runs/$R-$i/pid.txt" ] && break; sleep 0.25; done
      p=$(tr -d '\r\n' < "$W/port/runs/$R-$i/pid.txt" 2> /dev/null || true); [ -n "$p" ] || exit 0
      cd "$W" && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$here/full-screen.ps1")" -Launcher "$p" \
          -After "${FULL_AFTER:-30}" ${FULL_AT:+-X ${FULL_AT% *} -Y ${FULL_AT#* }} < /dev/null 2>&1 | tr -d '\r' > "$W/port/runs/$R-$i/full-screen.txt"
    ) &
  fi
done
# until every game has left; the busy check every ten seconds
given_up=""
while :; do
  left=0; for g in "${games[@]}"; do ! kill -0 "$g" 2> /dev/null || left=1; done
  [ $left = 1 ] || break
  sleep 10
  up=$(others)
  if [ -n "$up" ] && [ -z "$given_up" ]; then
    given_up=$(echo "$up" | head -1 | cut -c1-120); end_games
    echo "mixed-run $R: GIVEN UP: a game or a launcher that is not this run's is up (the owner plays?): $given_up; this run's games were ended" >&2
  fi
done
status=0; for g in "${games[@]}"; do wait "$g" || status=1; done
for i in $(seq 1 "$N"); do tail -q -n 1 "$B/$R-$i.run.log"; done
grep -h "desync\|go (" "$B/$R.server.log" | head -3 | cut -c1-200 || true   # (a race that differs has a line a second)
[ -z "$given_up" ] || exit 3
exit $status
