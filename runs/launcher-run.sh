#!/bin/bash
# launcher-run.sh RUN [SCENE]: the check of step 1 from the launcher's side. Starts the staged launcher
# (stage-launcher.sh) with --play-offline, which starts the recompiled game exactly as Home's "Play offline" does, in
# a data folder of its own (never the player's), and drives it with a manifest scene's scripted input (default
# boot-menus: title, menus, a Grand Prix race). Test-only additions, named in the launch file this script writes
# (RUN/launch.json, given as --config): the window title "Port test", for the runner --mute and its automation
# folder (screenshots and a clean stop), and for the game (the launch file's "game", which the launcher hands on as
# the game's "debug" part) what allows that folder, the probe's file and the pad script. Nothing of the game's is
# set in the environment: the runner reads no test setting there in a start with a launch file.
# Output: <work>/port/runs/RUN (probe.csv, stdout.txt, stderr.txt), screenshots <work>/shots/port-RUN-f<field>.png.
# Bounded: 170 s. Takes the machine like a build (BUILD.wanted.port). launch.ps1 ends the launcher and its game
# 40 s after that whatever happens here (the stop's 30 s and a margin): the run then says GONE, and RUN/limit.txt
# holds "stopped by its time limit".
# How the game ended is this script's last line, also kept in RUN/end.txt for gate-judge.py, and its exit status:
#   0  "game and launcher exited ... after the stop command", or "the game left by itself" with the core's own end
#      line in its log ("...; stopping", a playback's summary)
#   1  GONE (the process ended with no end line of its own: a crash, or closed from outside), FROZEN (fewer than 60
#      fields in 60 s while the process lives), NOT STARTED (a match with no go), NOT ENDED (ended here by its ID)
#   3  NOT STARTED: Windows had too little memory left for a game (../room-for-games.sh); nothing was started
# The game never opens a GameCube controller adapter (SDL_JOYSTICK_HIDAPI_GAMECUBE=0): the emulator turns that
# driver on by itself when no port is set to the adapter, and the owner's own game then gets no input from theirs.
#   SHOTS="3000 5000"   fields to take screenshots at (default: the scene's)
#   CARD=0              start with no memory card (default: the save file of <work>/port/user-pristine;
#                       CARD_FROM=NAME: of <work>/port/NAME, e.g. user-story-pristine for story-mission1)
#   LAUNCHER=NAME       the staged launcher <work>/port/NAME (default launcher-dev; its data folder is NAME-data)
#   MATCH=FILE          a race from this match file (match-file.sh) with --play-match instead of offline play; the
#                       replay is recorded to the run's folder (race.fzrp). The run ends when the game leaves by
#                       itself (after the results) or at the scene's fields.
#                       RECORD=default: no --replay is given, and the launcher records where it does for a player
#                       (<data>/replays, named by the time and the match).
#   REPLAY=FILE         a replay's playback (--play-replay) instead of offline play: the game boots the recorded race
#                       from the file and plays it with the replay scrubber, as a player watches it. A player's stays
#                       paused at the replay's end; this run's game stops there (the game's "replayEndQuits";
#                       REPLAY_STAYS=1: as a player's, until the scene's fields), as the race, as every replay plays.
#                       Use a scene without pad input (replay-playback).
#   SETUP=1             the game's own controller options (--play-controller-setup: what the Controller page's
#                       "Set up in the game" starts) instead of offline play; the game closes when the pad script
#                       leaves them (controller-setup-run.sh)
#   REFERENCE=1         the runner's JIT instead of the native module (the reference of the gates: the game's
#                       "debug.jit", and the runner's --allow-interpreter). A race on the JIT needs a launcher
#                       staged with the fork's kind of bundle (the runner's port/image/fork_bundle.py): the JIT
#                       takes no host calls, so a native bundle never gets its frame tick there
#   RUNNER_ARGS="a b"   more arguments of the runner's own (--graphics D3D); no setting of the game is one
#   AUTOPILOT=1         the game's AI drives the player's seat (the launch file's "autopilot": the game's
#                       "debug.autopilot"); LAG=N: a test lag of N ms ("testLagMs")
#   GAME_DEBUG='"k":v'  more members of the game's "debug" part, handed on by the launcher (its launch file's "game"):
#                       '"rollbackLog":"C:\\\\runs\\\\rb.csv","jitterMs":8' (JSON: a backslash is written twice)
#   INPUT=SCRIPT        the pad script instead of the scene's (FIELD:BUTTONS[:SX:SY[:CX:CY]],...); FIELDS=N the
#                       run's length instead of the scene's; TITLE=TEXT the window's title (no spaces)
#   PACE=1              a pacing run: the runner's pacing log (the game's "debug.paceLog") goes to RUN/pace.csv (read
#                       it with pace-report.py), the window is shown without taking the focus, and the machine is taken
#                       with TIMING.lock instead of a build request, so that no other game shares the GPU
#   SOUND=1             not muted (a listening test, stated beforehand)
#   RUN_ENV="K=V;K=V"   more environment variables for the launcher and the game: what a library reads for itself
#                       (SDL's). A test setting of the game is never one: GAME_DEBUG ('"noReinterpretReuse":true')
#   KEEP_DATA=1         the data folder of the run before is kept (default: a fresh one every run)
#   SHADER_CACHE=1      the user folder gets a Cache folder, without which the emulator's shader cache on disk is
#                       never written by this runner
#   DATA_NAME=NAME      the data folder <work>/port/NAME instead of LAUNCHER-data (two games at once: pair-run.sh)
#   SETTINGS='"k":v'    more members of the launcher's settings.json, which this script then writes into the data
#                       folder with "soundMuted": true ('"present":"console","inputDelay":1': the launcher's test
#                       settings, which it hands on to the game it starts). Without it no settings file is written
#   HAVE_LOCK=1         the caller already holds TIMING.lock (a match's test server must be started after the
#                       machine is taken: its start timeout runs while a lock is waited for)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../../.." && pwd)
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
BOUND=170   # the run's seconds, as the header says
R=$1; SCENE=${2:-boot-menus}; RUN=$W/port/runs/$R; RUNW="$WW\\port\\runs\\$R"
L=${LAUNCHER:-launcher-dev}; DN=${DATA_NAME:-$L-data}; DATA=$W/port/$DN; DATAW="$WW\\port\\$DN"
if [ -n "${HAVE_LOCK:-}" ]; then :   # the caller holds TIMING.lock already (it had to start a test server after taking it)
elif [ -n "${PACE:-}" ]; then pc_take timing-lock.sh "port: pacing run $R (3 min)" 4
else pc_take cpu-window.sh "port: launcher check $R (3 min)" 4; fi
INPUT_OVERRIDE=${INPUT:-}; FIELDS_OVERRIDE=${FIELDS:-}
read -r INPUT FIELDS SCENE_SHOTS < <(python3 - "$repo/recomp/manifest.toml" "$SCENE" <<'PY'
import sys, tomllib
scene = next(s for s in tomllib.load(open(sys.argv[1], "rb"))["scene"] if s["name"] == sys.argv[2])
shots = sorted(set(scene.get("screenshot_fields", [])) | ({scene["screenshot_field"]} if "screenshot_field" in scene else set()))
print(scene["input"], scene["fields"], ",".join(map(str, shots)))
PY
)
INPUT=${INPUT_OVERRIDE:-$INPUT}; FIELDS=${FIELDS_OVERRIDE:-$FIELDS}
SHOTS=${SHOTS-$(echo "$SCENE_SHOTS" | tr , ' ')}
rm -rf "$RUN"; [ -n "${KEEP_DATA:-}" ] || rm -rf "$DATA"
mkdir -p "$RUN/auto/commands" "$RUN/auto/staging" "$DATA/recomp-user"
source "$(dirname "$0")/emu-log.sh"; emu_log_on "$DATA"   # the emulator's own log: RUN/dolphin.log at the end
[ -z "${SHADER_CACHE:-}" ] || mkdir -p "$DATA/recomp-user/Cache"
# a settings file only when asked for, and then a silent launcher's (the project's standing rule 4)
[ -z "${SETTINGS:-}" ] || printf '{"soundMuted":true,%s}\n' "$SETTINGS" > "$DATA/settings.json"
if [ "${CARD:-1}" != 0 ]; then cp -r "$W/port/${CARD_FROM:-user-pristine}/GC" "$DATA/recomp-user/"; fi
if [ -n "${MATCH:-}" ]; then
  cp "$MATCH" "$RUN/match.json"   # the game reads its own copy: Windows programs cannot read every WSL path
  PLAY="--play-match|$RUNW\\match.json|--replay|$RUNW\\race.fzrp"
  # RECORD=default: nobody says where; the launcher records into its replay folder (<data>/replays), as for a player
  [ "${RECORD:-}" != default ] || PLAY="--play-match|$RUNW\\match.json"
elif [ -n "${REPLAY:-}" ]; then
  cp "$REPLAY" "$RUN/play.fzrp"
  PLAY="--play-replay|$RUNW\\play.fzrp"
elif [ -n "${SETUP:-}" ]; then
  PLAY="--play-controller-setup"
else
  PLAY="--play-offline"
fi
# the launch file: the title and the runner's arguments (a JSON text doubles its backslashes)
js() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }
ARGS="--data|$DATAW|$PLAY|--config|$RUNW\\launch.json"
RA="$(js --automation-dir),$(js "$RUNW\\auto")"
[ -n "${SOUND:-}" ] || RA="$RA,$(js --mute)"
ENV="SDL_JOYSTICK_HIDAPI_GAMECUBE=0"
case "${RUN_ENV:-}" in *FZGX_*|*STATICRECOMP*) echo "$R: RUN_ENV names a test setting of the game (${RUN_ENV}): it is a key of the game's \"debug\" part now (GAME_DEBUG; protocol/formats.md section 2)" >&2; exit 2;; esac
[ -z "${RUN_ENV:-}" ] || ENV="$ENV;$RUN_ENV"
# what the launcher hands on to the game as its launch file's "debug" part: the runner's automation folder is
# allowed, the probe's file and the pad script (the emulator's side reads them from the launch file, not from the
# environment), and what the run's kind adds
GG="\"automation\":true,\"probe\":$(js "$RUNW\\probe.csv"),\"pad\":$(js "$INPUT")"
[ -z "${PACE:-}" ] || GG="$GG,\"paceLog\":$(js "$RUNW\\pace.csv"),\"windowNoActivate\":true"
[ -z "${REPLAY:-}" ] || [ -n "${REPLAY_STAYS:-}" ] || GG="$GG,\"replayEndQuits\":true"
if [ -n "${REFERENCE:-}" ]; then GG="$GG,\"jit\":true"; RA="$RA,$(js --allow-interpreter)"; fi
for a in ${RUNNER_ARGS:-}; do RA="$RA,$(js "$a")"; done
GD=""; [ "${AUTOPILOT:-0}" != 1 ] || GD="$GD,\"autopilot\":true"
[ "${LAG:-0}" = 0 ] || GD="$GD,\"testLagMs\":$LAG"
GD="$GD,\"game\":{$GG${GAME_DEBUG:+,$GAME_DEBUG}}"
printf '{"about":"launcher-run.sh %s (%s)","debug":{"title":%s,"runnerArguments":[%s]%s}}\n' "$R" "$SCENE" "$(js "${TITLE:-Port test}")" "$RA" "$GD" > "$RUN/launch.json"
# Windows has the memory left for a game (room-for-games.sh), or none is started: status 3, as a PC that is not free
why=$("$here/../room-for-games.sh" 1) || { echo "$R: NOT STARTED: $why" | tee -a "$RUN/end.txt"; exit 3; }
grep -qs MaxSeconds "$W/kit-win/launch.ps1" || { echo "$R: $W/kit-win/launch.ps1 sets no time limit (an older harness): port/setup/install.sh --shared, the orchestrator's" >&2; exit 2; }   # every game's limit (the project's standing rule 4)
( cd "$W" && powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WW\\kit-win\\launch.ps1" -Runner "$WW\\port\\$L\\Launcher.App.exe" \
    -RunDir "$RUNW" -Env "$ENV" -ArgList "$ARGS" -MaxSeconds "$((BOUND + 40))" < /dev/null > "$RUN.launch.log" 2>&1 ) &
# not waited for: under WSL the PowerShell that started the launcher only returns when the launcher exits
START=$(date +%s.%N)
for _ in $(seq 1 120); do [ -s "$RUN/pid.txt" ] && break; sleep 0.25; done
[ -s "$RUN/pid.txt" ] || { echo "$R: the launcher did not start (see $RUN.launch.log)" >&2; exit 1; }
PID=$(tr -d '\r\n' < "$RUN/pid.txt")
alive() { tasklist.exe /FI "PID eq $PID" 2> /dev/null | grep -q "Launcher.App"; }
automation() { printf '%s\n' "${@:2}" > "$RUN/auto/staging/$1.txt"; mv "$RUN/auto/staging/$1.txt" "$RUN/auto/commands/$1.txt"; }
lines() { [ -f "$RUN/probe.csv" ] && wc -l < "$RUN/probe.csv" || echo 0; }
say() { echo "$R: $*" | tee -a "$RUN/end.txt"; }   # how the run ended: the last line here, and RUN/end.txt
echo "$R: launcher pid=$PID"
first=""; pending=($SHOTS); deadline=$(( $(date +%s) + BOUND )); bad=0; mark=0; marked=0; top=0
while [ "$(date +%s)" -lt $deadline ] && alive; do
  n=$(lines); now=$(date +%s)
  if [ -z "$first" ] && [ "$n" -ge 2 ]; then first=$(echo "$(date +%s.%N) - $START" | bc); echo "$R: first field after ${first}s"; mark=$now; marked=$n; fi
  # a game that lives and no longer plays (a crash into stray code writes a field every second or two)
  if [ -n "$first" ] && [ $((now - mark)) -ge 60 ]; then
    if [ $((n - marked)) -lt 60 ]; then
      say "FROZEN: $((n - marked)) fields in the last $((now - mark)) s (field $n, race frame $(tail -1 "$RUN/probe.csv" | cut -d, -f6)) while its process lives; stopping it"; bad=1; break
    fi
    mark=$now; marked=$n
  fi
  while [ ${#pending[@]} -gt 0 ] && [ "$n" -ge "${pending[0]}" ]; do
    automation "shot${pending[0]}" command=screenshot "path=$WW\\shots\\port-$R-f${pending[0]}.png"; pending=("${pending[@]:1}")
  done
  [ "$n" -ge "$FIELDS" ] && break
  # a match race that has not started: the game stands at the start gate (race frame 0) and shows nothing. A game
  # that was racing and stands there again booted a second time (it reset itself: top is the highest race frame
  # seen; a boot's first fields hold a stray number, far above any race's)
  rf=$({ tail -1 "$RUN/probe.csv" 2> /dev/null || true; } | cut -d, -f6); case "$rf" in ''|*[!0-9]*) rf=-1;; esac
  if [ "$rf" -gt "$top" ] && [ "$rf" -lt 1000000 ]; then top=$rf; fi
  if [ -n "${MATCH:-}" ] && [ "$n" -ge 2400 ] && [ "$rf" = 0 ]; then
    if [ "$top" -gt 0 ]; then say "RESET: the game was at race frame $top and is at its start gate again at field $n (it booted again); stopping"
    else say "NOT STARTED: the race has not started by field $n (no go from the relay?); stopping"; fi
    bad=1; break
  fi
  sleep 0.2
done
keep_log() {   # the core's log, and the runner's standard error, which a game started by the launcher writes to a file
  cp "$DATA/recomp-user/Logs/fzgx.log" "$RUN/fzgx.log" 2> /dev/null || true
  [ -s "$RUN/stderr.txt" ] || cp "$DATA/recomp-user/runner.log" "$RUN/stderr.txt" 2> /dev/null || true
  emu_log_keep "$DATA" "$RUN"
}
# the sourced script's own trap removed the request or the lock: both here
trap 'keep_log; [ -n "${HAVE_LOCK:-}" ] || pc_release' EXIT
if ! alive; then
  # gone before any stop command: by itself only when the core said so in its log; a crash leaves no such line
  keep_log; after="$(echo "$(date +%s.%N) - $START" | bc)s after the start"
  own=$(cat "$RUN/fzgx.log" "$RUN/stderr.txt" 2> /dev/null | grep -a 'fzgx: .*; stopping\|fzgx: playback:' | tail -1 | tr -d '\r' | sed 's/.*fzgx: //' | cut -c1-90 || true)
  if [ -n "$own" ]; then say "the game left by itself $after ($own); $(lines) fields"; exit $bad; fi
  say "GONE: the game's process ended $after with no end line of its own (a crash, or closed from outside); $(lines) fields"; exit 1
fi
automation zz-stop command=stop; STOP=$(date +%s.%N)
for _ in $(seq 1 30); do alive || break; sleep 1; done
if alive; then
  say "NOT ENDED: the launcher did not exit within 30 s of the game's stop; ending its process $PID and the game it started"; bad=1
  # the game is the launcher's one child: found by its parent's ID, never by name alone
  CHILD=$(powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"ParentProcessId=$PID and Name='moderngekko-run.exe'\").ProcessId" < /dev/null | tr -d '\r\n')
  [ -n "$CHILD" ] && taskkill.exe /PID "$CHILD" /F > /dev/null; taskkill.exe /PID "$PID" /F > /dev/null || true
else
  say "game and launcher exited $(echo "$(date +%s.%N) - $STOP" | bc)s after the stop command; $(lines) fields"
fi
exit $bad
