#!/bin/bash
# quickplay-run.sh RUN: Quick Play end to end through the launcher on the recompiled game (the port-recomp notes
# 5.15). Staged launchers (stage-launcher.sh), each with a data folder of its own, join a coordinator through the
# launcher's test door (a launch file's "quickPlay", Launcher.App --config FILE: the calls the lobby page's buttons
# make, on the launcher's own session) and go through the lobby, the start vote, the course vote, the machine choice,
# the race on the recompiled game, the results and back to the lobby, RACES times. The game's AI drives each player's
# seat (the file's "autopilot"), so a race ends by itself. Muted; windows shown without taking the focus and titled
# by the test. Each launcher's launch file is written here, into its run folder, under the name the end looks for.
#   SERVER          the coordinator (ws://HOST:PORT/ws or wss://...). Default: a test server started here in WSL (the
#                   coordinator and its relay in one process), stopped at the end by its process ID
#   LAUNCHERS (2)   launchers that race;  RACES (2)  races each stays for
#   WATCHER (0)     1: one more launcher joins once the first race's match has started and only waits in the lobby
#                   (the live race reaches it); it leaves when that race is over
#   BOTCOUNT (0)    simulated players (Online.Bots, from WSL) in the same lobby, naming the launchers' game build;
#                   BOTS (--no-checksums --ai) how they drive, or "--handoff FILE{0}": they take their seats in
#                   the match and never join the race. A bot run is one race: they are started again for each race
#   LAPS (1), COURSE (16: the course every launcher votes for when the vote offers it; a test server started here
#                   with FIXED=1 races it without a vote), LAG (0: test lag of every game, ms), LAG2 (game 2's)
#   SERVER_ARGS     more arguments for the test server (e.g. "--start-timeout 600 --ready-timeout 600")
#   ON_DESYNC       what the test server's relay does about a game its checksum vote went against (the server's
#                   --on-desync: observe or disconnect). Default: not passed (the server's default, observe)
#   VISIT1, VISIT2..  more members of launcher N's "quickPlay" ('"custom":{"create":"X"},"afterLeave":"watch"')
#   DOOR1, DOOR2..  more members of the "debug" object of launcher 1's, 2's, .. launch file ('"startLimitSeconds":60');
#                   ARGS1, ARGS2..: more arguments of the runner's own for its games; GAME1, GAME2..: more members of
#                   its games' "debug" part ('"alterStep":1500': the launch file's "game", handed on to the game); SETTINGS1, SETTINGS2..: more members of its settings.json (a launcher
#                   with another module: '"recomp":{"module":"C:\\...\\gGFZE01_recomp.dll"}')
#   SHOT1_AFTER     "60 120": screenshots of launcher 1's game that many seconds after its green light
#                   (<work>/shots/port-RUN-1-tN.png)
#   CLOSE1_AFTER    launcher 1's game is closed (its process ended, as a player closing the window) this many
#                   seconds after its green light (a game closed in the middle of a race)
#   RUN_ENV="K=V;K=V"  more environment variables for every launcher and its games, as launcher-run.sh takes them
#   MINUTES (8)     the longest the visit may take: the lock's stated end and each launcher's "timeLimitSeconds";
#                   launch.ps1 ends each launcher and its game a minute after it at the latest (RUN-N/limit.txt)
#   LAUNCHER1, LAUNCHER2..  another staged launcher folder for that launcher (two builds in one visit: each
#                   launcher names its own folder's game build to the server, which keeps a lobby to one build
#                   unless it was given the group both are in: SERVER_ARGS="--builds-together FILE"). The
#                   simulated players name LAUNCHER's build; the playbacks at the end (CHECK) run on one build
#   LAUNCHER (launcher-dev), CLOCKRATE (measured at the start by clock-rate.py: the WSL clock against Windows',
#                   for a relay or bots in WSL)
#   CHECK (1)       at the end every replay the launchers saved is played back against the checksums it recorded
#                   (replay-check.sh: runs pb-RUN-N-K), and the script fails unless 0 steps differ: the gate of 5.16.
#                   0: not (a run cut short on purpose, whose replays are not whole). Played back as the race
# Leaves <work>/port/runs/RUN-N for launcher N: door.jsonl (the door's lines), raceK/ (probe.csv, pace.csv, rb.csv,
# runner.log of its Kth game), replays/ (the launcher's replay folder), and <work>/port/scratch/qp/RUN.* (the test
# server's and the bots' logs). A game that never closed (it froze, and its launcher gave up at the time limit) has
# no raceK: its files stay in RUN-N itself, with its runner.log and fzgx.log. Then port/gates/reports/quickplay-report.py
# RUN, and port/gates/gate-judge.py quickplay RUN --launchers N --races K for the verdict.
# Exit status: 1 when a launcher did not end every one of its races (its game never closed, the visit failed) or a
# playback differed; 4 when a playback did not finish and nothing else failed.
# No game opens a GameCube controller adapter (SDL_JOYSTICK_HIDAPI_GAMECUBE=0; see launcher-run.sh).
# The machine is taken first (TIMING.lock; the other agents' request files are not waited for: the port has
# priority), then the busy check (port/scratch/rp/chk.sh) must say nobody plays.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); cd "$here/../../.."; root=$PWD
source "$here/emu-log.sh"
source "$here/../../setup/app.sh"
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
R=$1; B=$W/port/scratch/qp; mkdir -p "$B"
N=${LAUNCHERS:-2}; RACES=${RACES:-2}; MIN=${MINUTES:-8}; L=${LAUNCHER:-launcher-dev}
bots=${BOTCOUNT:-0}
# The machine: the lock, then nobody's game running (another agent's game that was running when the lock was taken
# ends within a few minutes; the owner's does not), then the lock still ours (met 2026-10-06 09:59: another agent's
# run wrote its lock over this one while this script waited for a third agent's game to end). Tried for 20 minutes.
# The lock is read where timing-lock.sh wrote it (its _TW: PORT_LOCKS, the PC's one place, not this work folder).
ready=""
for _ in $(seq 1 10); do
  IGNORE_REQUESTS="${IGNORE_REQUESTS:-map bench emit disc}" pc_take timing-lock.sh "port: Quick Play $R ($MIN min at most)" "$MIN"
  clear=""
  for _ in $(seq 1 6); do if "$BUSY" > "$B/$R.chk" 2>&1; then clear=1; break; fi; sleep 20; done
  if [ -n "$clear" ] && { ! pc_has timing-lock.sh || grep -qs "^pid=$$\$" "$_TW/TIMING.lock"; }; then ready=1; break; fi
  echo "$R: $(date +%T) not started: $([ -n "$clear" ] && echo "the lock was taken over ($(grep -s '^owner=' "$_TW/TIMING.lock" | tr -d '\n'))" || echo "a game is running ($(grep -o -- '--title [^ ]*' "$B/$R.chk" | head -1))"); waiting again"
  pc_release; sleep 15
done
[ -n "$ready" ] || { echo "$R: the machine was not free in 20 minutes:"; cut -c1-200 "$B/$R.chk"; exit 3; }
# and Windows has the memory left for every launcher's game (room-for-games.sh), or nothing is started
why=$(port/gates/room-for-games.sh $((N + ${WATCHER:-0}))) || { echo "$R: $(date +%T) not started: $why"; exit 3; }
# the stated end counts from here
! pc_has timing-lock.sh || sed -i "s/^expected_end=.*/expected_end=$(date -d "+$MIN minutes" +%FT%T%z)/; s/^expected_end_epoch=.*/expected_end_epoch=$(date -d "+$MIN minutes" +%s)/" "$_TW/TIMING.lock"
. "$here/race-lib.sh"   # race_server, race_bots, stop_ours, game_of
pids=()
alive() { tasklist.exe /FI "PID eq $1" 2> /dev/null | grep -q "Launcher.App"; }
# Everything this run starts on Windows carries the run's name in its command line (the game's title, which is the
# name of its launcher's launch file too): that is how the end finds it, whatever happened in between. Process IDs
# alone are reused.
ours() {   # "PID NAME" of every launcher and game of this run that is up
  powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='moderngekko-run.exe' or Name='Launcher.App.exe'\" | Where-Object { \$_.CommandLine -like '*Quick-Play-test-$R-game-*' } | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.Name)\" }" < /dev/null 2> /dev/null | tr -d '\r'
}
stop_launchers() {   # on every way out: the launchers and games of this run that are still up, each by its ID
  local left; left=$(ours)
  [ -z "$left" ] || echo "$left" > "$B/$R.left"
  while read -r p name; do
    [ -n "$p" ] || continue
    taskkill.exe /PID "$p" /F < /dev/null > /dev/null 2>&1 || true   # (it reads standard input: the list, without this)
    echo "$R: ended $name $p (still running at the end)"
  done <<< "$left"
  left=$(ours)
  if [ -n "$left" ]; then echo "$R: STILL RUNNING AFTER THE END, to be ended by hand: $left" | tr '\n' ' '; echo; else rm -f "$B/$R.left"; fi
}
trap 'stop_launchers; stop_ours; pc_release' EXIT
stop_ours
# the WSL clock against Windows' over five seconds (it has run 3.8% slow on this PC, and at other times not): a
# relay or bots in WSL are given the rate measured now, unless CLOCKRATE says
rate=${CLOCKRATE:-$(python3 "$here/clock-rate.py")}
echo "$R: the WSL clock against Windows': $rate"
# the pad of every game: A tapped every three seconds from field 1,500 on, which leaves the results (the game's AI
# drives the race)
PAD="0:0$(for f in $(seq 1500 180 $((MIN * 3600))); do printf ',%d:100,%d:0' "$f" $((f + 6)); done)"
if [ -z "${SERVER:-}" ]; then
  host=$(ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1)
  [ -f "$APP_SERVER" ] || { echo "quickplay-run: build the application first ($APP_BUILD)" >&2; exit 1; }
  course=""; [ -z "${FIXED:-}" ] || course="--course ${COURSE:-16}"
  race_server $((MIN * 60 + 60)) --no-announce --allow-debug --voting-minimum 2 --laps "${LAPS:-1}" --clock-rate "$rate" \
      $course ${ON_DESYNC:+--on-desync "$ON_DESYNC"} ${SERVER_ARGS:-} || exit 1
  URL="ws://$host:$TEST_PORT/ws"
else
  URL=$SERVER
fi
echo "$R: $(date +%T) coordinator $URL, $N launcher(s), $RACES race(s), $bots simulated player(s)"
# the simulated players name the launchers' game build, or the coordinator would keep them in a lobby of their own
sha() { sha1sum "$1" | cut -d' ' -f1; }
build="$(sha "$W/port/$L/recomp/fzgx/mod.bin")/$(sha "$W/port/$L/recomp/gGFZE01_recomp.dll")/$(sha "$W/port/$L/recomp/moderngekko-run.exe")"
echo "$R: game build $(echo "$build" | sed -E 's|([0-9a-f]{8})[0-9a-f]*|\1|g')"
botrace=0
start_bots() {   # one bot run is one race: started again for each race of the visit
  botrace=$((botrace + 1))
  race_bots "$B/$R.bots$botrace.log" $((MIN * 60)) --server "$URL" --count "$bots" --name-prefix Bot --offset 3 --expect $((bots + N)) \
      --start-voters "$bots" --cpu-voters "$((bots + N))" ${BOTS:---no-checksums --ai} --frames "${BOT_FRAMES:-30000}" --timeout $((MIN * 60 - 20)) \
      --clock-rate "$rate" --build "$build"
  echo "$R: $(date +%T) $bots simulated players for race $botrace"
}
start() {   # start I KIND: launcher I through its test door; KIND race or watch
  local i=$1 kind=$2 RUN=$W/port/runs/$R-$1 RUNW="$WW\\port\\runs\\$R-$1" DATA=$W/port/qp-data-p$1 DATAW="$WW\\port\\qp-data-p$1"
  rm -rf "$RUN" "$DATA"; mkdir -p "$RUN/auto/commands" "$RUN/auto/staging" "$DATA/recomp-user"
  emu_log_on "$DATA"   # the emulator's own log: raceK/dolphin.log
  cp -r "$W/port/user-pristine/GC" "$DATA/recomp-user/"
  local door="DOOR$i" extra="ARGS$i" more="SETTINGS$i" game="GAME$i" lag=${LAG:-0} own="LAUNCHER$i"
  local folder=${!own:-$L}
  [ -f "$W/port/$folder/Launcher.App.exe" ] || { echo "$R: $W/port/$folder is no staged launcher (LAUNCHER$i)" >&2; exit 1; }
  # (a test is silent: the launcher's own sounds, the lobby's three tones, are muted in every test's settings)
  printf '{"soundMuted":true,"racer":{"name":"Port%02d","machine":%d,"color":{"r":%d,"g":%d,"b":%d},"stockColor":null}%s}\n' \
      "$i" $((i * 3 % 30)) $((40 + i * 60 % 200)) $((200 - i * 50 % 160)) $((i * 90 % 255)) "${!more:+,${!more}}" > "$DATA/settings.json"
  [ "$i" != 2 ] || lag=${LAG2:-$lag}
  # the launch file: the visit, and what its games get (a JSON text doubles its backslashes)
  js() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }
  local name="Quick-Play-test-$R-game-$i" more_debug=""
  local visit="\"server\":$(js "$URL"),\"log\":$(js "$RUNW\\door.jsonl"),\"timeLimitSeconds\":$((MIN * 60 - 30))"
  local visit_more="VISIT$i"; visit="$visit${!visit_more:+,${!visit_more}}"   # more of the visit: "custom", "afterLeave"
  local ra="$(js --mute),$(js --automation-dir),$(js "$RUNW\\auto")"
  # every game's own test settings of the emulator's side (its launch file's "debug", not the environment): the
  # automation folder allowed, the probe, the pacing log, the pad script, a window that does not take the focus
  local side="\"automation\":true,\"probe\":$(js "$RUNW\\probe.csv"),\"paceLog\":$(js "$RUNW\\pace.csv"),\"windowNoActivate\":true,\"pad\":$(js "$PAD")"
  if [ "$kind" = watch ]; then visit="$visit,\"watch\":true,\"races\":1"; more_debug=",\"game\":{$side}"; else
    visit="$visit,\"races\":$RACES,\"startWith\":$((N + bots)),\"voteCourse\":${COURSE:-16}"; more_debug=",\"autopilot\":true"
    [ "$lag" = 0 ] || more_debug="$more_debug,\"testLagMs\":$lag"
    # the game's own test settings, handed on by the launcher into the game's launch file ("debug")
    more_debug="$more_debug,\"game\":{$side,\"rollbackLog\":$(js "$RUNW\\rb.csv")${!game:+,${!game}}}"
  fi
  for x in ${!extra:-}; do ra="$ra,$(js "$x")"; done
  printf '{"about":"quickplay-run.sh %s: launcher %s (%s)","debug":{"title":"%s--agent--closes-by-itself","runnerArguments":[%s],"quickPlay":{%s}%s%s}}\n' \
      "$R" "$i" "$kind" "$name" "$ra" "$visit" "$more_debug" "${!door:+,${!door}}" > "$RUN/$name.json"
  local a="--data|$DATAW|--config|$RUNW\\$name.json"
  ( cd "$W" && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WW\\kit-win\\launch.ps1" -Runner "$WW\\port\\$folder\\Launcher.App.exe" \
      -RunDir "$RUNW" -Env "SDL_JOYSTICK_HIDAPI_GAMECUBE=0${RUN_ENV:+;$RUN_ENV}" -ArgList "$a" \
      -MaxSeconds "$((MIN * 60 + 60))" < /dev/null > "$RUN.launch.log" 2>&1 ) &
  for _ in $(seq 1 80); do [ -s "$RUN/pid.txt" ] && break; sleep 0.25; done
  [ -s "$RUN/pid.txt" ] || { echo "$R: launcher $i did not start (see $RUN.launch.log)" >&2; exit 1; }
  pids+=("$(tr -d '\r\n' < "$RUN/pid.txt")")
  echo "$R: $(date +%T) launcher $i ($kind) pid ${pids[-1]}$([ "$folder" = "$L" ] || echo ", from $folder")"
}
grep -qs MaxSeconds "$W/kit-win/launch.ps1" || { echo "$R: $W/kit-win/launch.ps1 sets no time limit (an older harness): port/setup/install.sh --shared, the orchestrator's" >&2; exit 2; }   # every game's limit (the project's standing rule 4)
for i in $(seq 1 "$N"); do start "$i" race; sleep 1; done
# the simulated players after the launchers: the first three seats' launchers report the live race for the lobby
[ "$bots" = 0 ] || { sleep 2; start_bots; }
count() { grep -c "$2" "$W/port/runs/$R-$1/door.jsonl" 2> /dev/null || true; }
declare -A kept; watcher=${WATCHER:-0}; closed=""; green=""; shots=(${SHOT1_AFTER:-}); shotgreen=""
deadline=$(( $(date +%s) + MIN * 60 - 10 ))
tick=0
while [ "$(date +%s)" -lt $deadline ]; do
  up=0; tick=$((tick + 1))
  for k in "${!pids[@]}"; do
    i=$((k + 1)); RUN=$W/port/runs/$R-$i
    alive "${pids[$k]}" && up=$((up + 1))
    # a game that closed: its files are kept before the launcher's next game writes over them
    n=$(count "$i" '"state":"closed"'); n=${n:-0}
    if [ "$n" -gt "${kept[$i]:-0}" ]; then
      kept[$i]=$n; mkdir -p "$RUN/race$n"
      for f in probe.csv pace.csv rb.csv; do [ ! -f "$RUN/$f" ] || mv "$RUN/$f" "$RUN/race$n/" 2> /dev/null || cp "$RUN/$f" "$RUN/race$n/" || true; done
      cp "$W/port/qp-data-p$i/recomp-user/runner.log" "$RUN/race$n/" 2> /dev/null || true
      emu_log_keep "$W/port/qp-data-p$i" "$RUN/race$n"
      echo "$R: $(date +%T) launcher $i: race $n over"
    fi
  done
  if [ "$watcher" = 1 ] && [ "$(count 1 '"event":"live"')" -gt 0 ]; then watcher=started; start $((N + 1)) watch; fi
  # pictures of game 1 at given seconds after its green light (each stalls that game's picture for a moment)
  if [ ${#shots[@]} -gt 0 ] && [ "$(count 1 'green light')" -gt 0 ]; then
    [ -n "$shotgreen" ] || shotgreen=$(date +%s)
    if [ $(( $(date +%s) - shotgreen )) -ge "${shots[0]}" ]; then
      printf 'command=screenshot\npath=%s\n' "$WW\\shots\\port-$R-1-t${shots[0]}.png" > "$W/port/runs/$R-1/auto/staging/shot${shots[0]}.txt"
      mv "$W/port/runs/$R-1/auto/staging/shot${shots[0]}.txt" "$W/port/runs/$R-1/auto/commands/shot${shots[0]}.txt"
      shots=("${shots[@]:1}")
    fi
  fi
  if [ -n "${CLOSE1_AFTER:-}" ] && [ -z "$closed" ] && [ "$(count 1 'green light')" -gt 0 ]; then
    [ -n "$green" ] || green=$(date +%s)
    if [ $(( $(date +%s) - green )) -ge "$CLOSE1_AFTER" ]; then
      c=$(game_of "${pids[0]}"); closed=1
      [ -z "$c" ] || { taskkill.exe /PID "$c" /F < /dev/null > /dev/null 2>&1 || true; echo "$R: $(date +%T) closed launcher 1's game (pid $c) in the middle of its race"; }
    fi
  fi
  # the race's simulated players go when every launcher is back from it, and new ones come for the next race
  if [ "$bots" -gt 0 ] && [ "$botrace" -lt "$RACES" ]; then
    back=0; for i in $(seq 1 "$N"); do [ "${kept[$i]:-0}" -ge "$botrace" ] && back=$((back + 1)); done
    if [ "$back" = "$N" ]; then
      [ ! -s "$B/bots.pid" ] || kill "$(cat "$B/bots.pid")" 2> /dev/null || true
      sleep 6; start_bots   # a watcher has left by then
    fi
  fi
  [ $up -gt 0 ] || break
  sleep 0.5
done
for k in "${!pids[@]}"; do i=$((k + 1)); rm -rf "$W/port/runs/$R-$i/replays"; cp -r "$W/port/qp-data-p$i/replays" "$W/port/runs/$R-$i/" 2> /dev/null || true; done
stop_launchers
echo "$R: $(date +%T) done; $(ls "$W"/port/runs/"$R"-*/replays/*.fzrp 2> /dev/null | wc -l) replay(s)"
# Every racing launcher must have ended every race: a game that froze never closes, and its launcher only gives up
# at the time limit. Such a game's logs are kept beside the files it left (no raceK folder was made for it).
status=0
for i in $(seq 1 "$N"); do
  RUN=$W/port/runs/$R-$i; n=$(count "$i" '"state":"closed"'); n=${n:-0}
  [ "$n" -lt "$RACES" ] || continue
  status=1
  if [ -f "$RUN/probe.csv" ]; then
    cp "$W/port/qp-data-p$i/recomp-user/runner.log" "$W/port/qp-data-p$i/recomp-user/Logs/fzgx.log" "$RUN/" 2> /dev/null || true
    emu_log_keep "$W/port/qp-data-p$i" "$RUN"
  fi
  echo "$R: launcher $i ended $n of $RACES race(s)$(grep -o '"event":"failed".*' "$RUN/door.jsonl" 2> /dev/null | head -1 | sed 's/.*"text":"\([^"]*\)".*/: \1/; s/\\u0027/\x27/g'); its game's last whole field: $(tail -2 "$RUN/probe.csv" 2> /dev/null | head -1 | cut -d, -f1,6 | sed 's/,/, race frame /')"
done
# The gate of the port-recomp notes 5.16: every recording of a race with real rollbacks plays back with 0 steps
# differing. The server, the bots and the lock go first: each playback takes the machine itself.
if [ "${CHECK:-1}" != 0 ]; then
  stop_ours; pc_release
  if [ "${AT_ONCE:-1}" != 1 ]; then
    # AT_ONCE=N (replay-check.sh): every launcher's recordings in one call, N playbacks side by side, each under the
    # name it has one after the other (pb-RUN-LAUNCHER-K); the loop below then has nothing left to play
    all=(); names=""
    for d in "$W"/port/runs/"$R"-*/replays; do
      i=${d%/replays}; i=${i##*-}; k=0
      for f in "$d"/*.fzrp; do [ -e "$f" ] || continue; k=$((k + 1)); all+=("$f"); names+=" pb-$R-$i-$k"; done
    done
    config=playback
    if [ ${#all[@]} -gt 0 ]; then
      s=0; CONFIG=$config NAMES="${names# }" port/gates/replay-check.sh "pb-$R" "${all[@]}" || s=$?
      [ $s = 0 ] || [ $status = 1 ] || status=$s   # 1 (failed) outranks 4 (did not finish)
    fi
  fi
  for d in "$W"/port/runs/"$R"-*/replays; do
    [ "${AT_ONCE:-1}" = 1 ] || break
    [ -n "$(ls "$d"/*.fzrp 2> /dev/null)" ] || continue
    i=${d%/replays}; i=${i##*-}
    config=playback
    s=0; CONFIG=$config port/gates/replay-check.sh "pb-$R-$i" "$d"/*.fzrp || s=$?
    [ $s = 0 ] || [ $status = 1 ] || status=$s   # 1 (failed) outranks 4 (did not finish)
  done
fi
exit $status
