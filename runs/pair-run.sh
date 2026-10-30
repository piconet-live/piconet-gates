#!/bin/bash
# pair-run.sh RUN: two games race each other on this computer (the port-recomp notes 5.14): a test server (the
# coordinator and its relay, in WSL), 28 simulated players (Online.Bots) and two staged launchers, each starting the
# recompiled game from its own match file in its own data folder, each taking a stand-in's seat on the relay.
# Rollback is on as in play (input delay 2). Normal speed (the relay paces the race), muted, windows shown without
# taking the focus and titled by the test. Leaves <work>/port/runs/RUN-1 and RUN-2 (probe.csv, pace.csv, race.fzrp,
# stderr.txt, rb.csv: the rollback log) and <work>/port/scratch/pair/RUN.* (the server's and the bots' logs); then
# port/gates/reports/pair-report.py RUN says whether the two games ran one race.
#   LAG (0)         test lag of both games in ms (an added round trip; LAG2: the second game's, default LAG)
#   JITTER (0)      each packet held up to this many ms longer (both games; JITTER2: the second game's, default JITTER)
#   BOTS (--ai)     how the 28 simulated players drive: --ai (the game's AI with bursts of real inputs), --ai-steady
#                   (never a change: no misprediction), --ai-churn (a change every frame: a rollback every frame)
#   AUTO (1)        the game's AI drives each game's own seat (the race then ends by itself); 0: the pad scripts
#                   INPUT1 and INPUT2 drive them. AUTO2: the second game's alone (AUTO2=0 INPUT2=...: a seat whose
#                   player never finishes, beside one the AI drives home)
#   FINISH_LIMIT    the server's --finish-limit-seconds: the race ends for everyone so many seconds after the first
#                   finish (not given: the server's own, Quick Play's 90; 0: no such end)
#   HOLD2 (1)       the second game is started this many seconds after the first, which then holds at the start
#                   gate that much longer (the panel WAITING FOR PLAYERS; a game not let go by field 2,400 stops)
#   LAUNCHER2       the second game's staged launcher (default LAUNCHER's): two builds in one race. Its data
#                   folder is the first launcher's second one all the same (<LAUNCHER>-data-p2)
#   CLOCK2          the second game starts from this real-time clock value (hexadecimal) instead of the fixed one
#   ALTER2          the second game's state is altered before this step (a desync on purpose)
#   CARD2           the second game's save file is <work>/port/CARD2's (launcher-run.sh's CARD_FROM) and not the
#                   pristine one: a player's own controller options in one game of the two (options-run.sh)
#   ON_DESYNC       what the test server's relay does about a game its checksum vote went against (the server's
#                   --on-desync: observe or disconnect). Default: not passed (the server's default, observe: a
#                   difference is only logged, also with ALTER2; two games that differ are a tie in any case)
#   DATA_PREFIX     the games' data folders are <work>/port/DATA_PREFIX-p1 and -p2 (default: <LAUNCHER>-data), so that
#                   a run need not share another's
#   EARLY_CLOSE (1) 0: the test server's relay closes every frame at its deadline (--no-early-close), never as soon
#                   as every seat's input is there: the relay before 14 October 2026, for comparisons
#   STATS1, STATS2  a stat pack for game 1's and game 2's race: a file with the match start's "setup.stats" (name,
#                   fingerprint, values; stat-pack.py writes one). Both the same file: a race on that pack. Two
#                   files: two games that were handed different packs (stat-pack-run.sh). None: the disc's car data
#   GAME_MODE       a game mode for both games' race: a file with the match start's "setup.mode" (package, hash,
#                   api, params: the protocol's ModeStart, as protocol/tests/vectors/modes/*.mode.json). The mode's
#                   setup words win (its laps are the race's)
#   PLAYER_MACHINE  both games' own machine (0 to 40; default the stand-ins' own): a pack's changed machine in the
#                   race (MACHINE is the playbacks': the harness's machine file, replay-check.sh)
#   ROLLBACKS       rollbacks forced in both games: the game's "debug.forceRollback" as JSON,
#                   '{"every":7,"depths":[3,9,17]}' (not FORCE: replay-check.sh, which plays the recordings back
#                   at the end, refuses that name as one of its own that has gone)
#   STATES          "FROM,TO": the machines' state before those steps into RUN-N/trace.csv.states (the game's
#                   "debug.trace" and "debug.traceStates")
#   BOTCOUNT (28)   simulated players; with fewer the stand-ins and the bots ask for CPU racers, which fill the
#                   race to 30 (the game's own CPU drivers, from the match's CPU seed)
#   COURSE (16), LAPS (1), FIELDS (the scene's), DELAY (2), OC (6.0), CLOCKRATE (1.038), ARGS1, ARGS2 (more of the runner's own
#   arguments), LAUNCHER (launcher-dev)
#   CHECK (1)       at the end both recordings are played back, each against the checksums it recorded
#                   (replay-check.sh: runs pb-RUN-1, pb-RUN-2), and the script fails unless 0 steps differ: the gate
#                   of 5.16, which sees a rollback that left one step's state wrong in both games alike. 0: not.
#   CHECK_LATE      N: and once more with the recordings' inputs known N steps late (runs pbl-RUN-1, -2)
#   CUSTOM          players: both games' seats race custom machines (a seat's parts made from its number, each of
#                   its kind; the custom-machines-online notes); all: every seat, the CPU racers' too
#   PACKS, SEAT_PACKS  packs a seat (handbook/stat-pack-constants.md): PACKS the race's packs, files as STATS1's (comma
#                   between them), SEAT_PACKS each seat's choice, "own1:0,own2:1,5:1" (own1, own2: the two games' own
#                   seats; a number: that seat; 0 the disc's own, k the k-th of PACKS); CUSTOM=two: game 2's seat alone
#                   races a custom machine; CUSTOM=one: game 1's
#   MACHINE1, MACHINE2   the machine of each game's seat (0 to 40), in place of the one the test server dealt it;
#                   written into both games' match files, so the race is one race
#   SETTING1, SETTING2   the machine setting of each game's seat (0 to 100: 0 the acceleration end, 100 the max
#                   speed end), in place of the one the test server gave it; written into both games' match files
#   REJOIN2=SECONDS a crash and a rejoin (the rejoin-and-h9 notes, proofs 1 and 3): SECONDS after the relay's go
#                   (the server's log) game 2's game is ended by its process ID, and REJOIN2_AFTER (0) seconds later
#                   started again on the same match file with "rejoin": true, as the launcher's Rejoin does: run
#                   RUN-2r, data folder <DATA_PREFIX>-p2r, recording RUN-2r/race.fzrp. Give CHECK=0 (game 2's own
#                   recording is cut short); the script waits for the game started again as for the other two
#   SPECTATE3=SECONDS  a spectator joins mid-race (stage A2, the plan-control-room notes section 3): SECONDS after the
#                   relay's go a bot in the race's lobby asks to watch (Online.Bots --watch: a spectator seat) and a
#                   third game is started on the spectator's start ("spectate": true in its match file): run RUN-3,
#                   data folder <DATA_PREFIX>-p3, no recording. It catches up behind LOADING and watches; the relay
#                   leaves it out of the vote (its log: "spectator ..."). The bots are one fewer (BOTCOUNT 27: the
#                   lobby keeps a place for the watcher; CPUs fill the race). ARGS3, DEBUG3, INPUT3 as for the others
#   ONE=1           game 2 is not started (its seat goes to the AI 20 s after the race is made: the server's
#                   --start-timeout): one racer's game, for a spectator test on a PC with the memory for two games
#   DEBUG1, DEBUG2  more members of each game's "debug" part, as launcher-run.sh's GAME_DEBUG takes them
#                   ('"dump":{"step":3000,"prefix":"D:\\\\x\\\\r-2"}'); DEBUG: of both
#   SETTINGS1, SETTINGS2  more members of each game's launcher settings.json, as launcher-run.sh's SETTINGS takes
#                   them ('"widescreen":"trueWide"': one game in true widescreen, the other the game's own)
#   KO2=FRAME       a spectator test: game 2's racer is knocked out. From race frame FRAME on both games hold its
#                   energy (machine +0x184) at 0 with the emulator's task poke (and its task timers, whose hooks
#                   the poke is made from), by race frame, so a step run again
#                   does it too and the games stay equal; the next hit destroys it, and three seconds on game 2
#                   spectates. KO_MACHINES: the machines' address in this kind of race ([main.rel .bss 0x6D838]:
#                   read it from a dump, DEBUG1's "dump"). A recording made so does not play back as recorded
#                   (nothing pokes a playback): give CHECK=0. KO_MORE=FRAME: from race frame FRAME on every
#                   racer but the two games' own is held at 0 the same way, so the racers a spectator watches
#                   go out one after another, each at its next hit.
#                   KO_HOW=flags: no hit is waited for: the poke writes the first byte of the machine's flags
#                   (0x08: retired) instead of its energy, so a racer is out in the very step of its frame.
# Exit status: 1 when a game crashed, froze, never started or had to be ended (launcher-run.sh says which, in the
# line printed here for each game) or a playback differed; 4 when a playback did not finish and nothing else failed.
# Whether the two recordings are one whole race is gate-judge.py's to say (pair RUN).
# The machine is taken first (TIMING.lock), then the match is made. A game whose race has
# not started by field 2,400 stops itself (launcher-run.sh). The server and the bots end by themselves after 300 s
# and are stopped here, by their process IDs, as soon as both games have left.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); cd "$here/../../.."; root=$PWD
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
R=$1; B=$W/port/scratch/pair; mkdir -p "$B"
pc_take timing-lock.sh "port: two games $R (3 min)" 5   # this PC's, where it has it (lib.sh)
# Windows has the memory left for two games (room-for-games.sh), or nothing is started: status 3, as a PC not free
why=$(port/gates/room-for-games.sh $(( $([ -z "${SPECTATE3:-}" ] && echo 2 || echo 3) - $([ -z "${ONE:-}" ] && echo 0 || echo 1) ))) || { echo "pair-run $R: not started: $why" >&2; exit 3; }
host=${RELAY_HOST:-$(ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1)}
rate=${CLOCKRATE:-1.038}
source "$here/../../setup/app.sh"; . "$here/race-lib.sh"   # race_server, race_bots, stop_ours, game_of
[ -f "$APP_SERVER" ] && [ -f "$APP_BOTS" ] || { echo "pair-run: build the application first ($APP_BUILD)" >&2; exit 1; }
stop_ours; sleep 1
rm -f "$B/$R".h0 "$B/$R".h1 "$B/$R"-1.json "$B/$R"-2.json
trap 'stop_ours; pc_release' EXIT   # only this script's own lock (timing-lock.sh, where it was taken)
race_server 300 --no-announce --allow-ai-inputs --start-timeout $([ -z "${ONE:-}" ] && echo 240 || echo 20) --voting-minimum 2 \
    --course "${COURSE:-16}" --laps "${LAPS:-1}" --clock-rate "$rate" ${ON_DESYNC:+--on-desync "$ON_DESYNC"} \
    $([ "${EARLY_CLOSE:-1}" != 0 ] || echo --no-early-close) \
    ${FINISH_LIMIT:+--finish-limit-seconds "$FINISH_LIMIT"} || exit 1
n=${BOTCOUNT:-$([ -z "${SPECTATE3:-}" ] && echo 28 || echo 27)}; fill=""; [ "$n" -ge 28 ] || fill="--cpu-voters 30"
race_bots "$B/$R.bots.log" 290 --server ws://127.0.0.1:47810/ws --count "$n" --name-prefix Bot --offset 3 --expect $((n + 2)) \
    --start-voters "$n" $fill --no-checksums ${BOTS:---ai} --frames 14000 --timeout 280 --clock-rate "$rate"
timeout 120 dotnet "$APP_BOTS" --server ws://127.0.0.1:47810/ws --count 2 --name-prefix Port --handoff "$B/$R.h{0}" \
    --offset 1 --expect $((n + 2)) --start-voters 2 $fill --clock-rate "$rate" ${PLAYER_MACHINE:+--machine "$PLAYER_MACHINE"} \
    > "$B/$R.standin.log" 2>&1 || true
[ -s "$B/$R.h0" ] && [ -s "$B/$R.h1" ] || { echo "pair-run: no match started (see $B/$R.server.log, $B/$R.standin.log)" >&2; exit 1; }
python3 - "$B/$R" "$host" "${DELAY:-2}" "${OC:-6.0}" "${LAG:-0}" "${LAG2:-${LAG:-0}}" "${MACHINE1:-}" "${MACHINE2:-}" "${STATS1:-}" "${STATS2:-}" "${CUSTOM:-}" "${PACKS:-}" "${SEAT_PACKS:-}" "${SETTING1:-}" "${SETTING2:-}" "${GAME_MODE:-}" <<'PY'
import json, sys
base, host, delay, oc, lag1, lag2 = sys.argv[1:7]
stats1, stats2 = sys.argv[9:11]
matches = [json.load(open(f"{base}.h{i}")) for i in (0, 1)]
for match in matches:                         # both files name both seats' machines
    for other, machine in zip(matches, sys.argv[7:9]):
        if machine:
            next(s for s in match["setup"]["seats"] if s["seat"] == other["seat"])["machine"] = int(machine)
    for other, setting in zip(matches, sys.argv[14:16]):
        if setting:
            next(s for s in match["setup"]["seats"] if s["seat"] == other["seat"])["setting"] = int(setting)
    for s in match["setup"]["seats"]:         # custom machines: seat i's parts made from i, each of its kind
        i = s["seat"]
        if sys.argv[11] == "all" or (sys.argv[11] == "players" and s.get("playerId")) or (sys.argv[11] == "two" and i == matches[1]["seat"]) or (sys.argv[11] == "one" and i == matches[0]["seat"]):
            s["custom"] = {"body": i % 25, "cockpit": 25 + 7 * i % 25, "booster": 50 + 11 * i % 25, "pilot": i % 41}
    # packs a seat: the race's packs (wire files) and each named seat's index ("own1", "own2" or a seat number)
    if sys.argv[12]:
        match["setup"]["packs"] = [json.load(open(f)) for f in sys.argv[12].split(",")]
    for item in filter(None, sys.argv[13].split(",")):
        who, k = item.split(":")
        seat = matches[0]["seat"] if who == "own1" else matches[1]["seat"] if who == "own2" else int(who)
        next(x for x in match["setup"]["seats"] if x["seat"] == seat)["pack"] = int(k)
for i, lag, stats in ((0, lag1, stats1), (1, lag2, stats2)):
    match = matches[i]
    if stats:   # the race's stat pack, as a server would put it into the match start
        match["setup"]["stats"] = json.load(open(stats))
    if sys.argv[16]:   # the race's game mode, as a server would put it into the match start
        match["setup"]["mode"] = json.load(open(sys.argv[16]))
    json.dump({"match": match, "relayHost": host, "delay": int(delay), "overclock": float(oc), "otherSounds": "quieter"},
              open(f"{base}-{i + 1}.json", "w"))
    s = match["setup"]
    print(f"game {i + 1}: match {match['matchId']}, seat {match['seat']} of {len(s['seats'])} "
          f"({sum(1 for x in s['seats'] if not x.get('playerId'))} CPU), course {s['course']}, {s['laps']} lap(s), "
          f"seeds {s['shuffleSeed']:#x} {s['cpuSeed']:#x}, test lag {lag} ms, machine "
          f"{next(x for x in s['seats'] if x['seat'] == match['seat'])['machine']}, setting "
          f"{next(x for x in s['seats'] if x['seat'] == match['seat']).get('setting', 'as dealt')}"
          + (f", stat pack {s['stats']['name']} ({s['stats']['fingerprint'][:8]})" if stats else "")
          + (f", game mode {s['mode']['hash'][:8]} (params {s['mode']['params']})" if sys.argv[16] else ""))
    open(f"{base}.seat{i + 1}", "w").write(str(match["seat"]))
PY
ko=""
if [ -n "${KO2:-}" ]; then
  [ -n "${KO_MACHINES:-}" ] || { echo "pair-run: KO2 needs KO_MACHINES (the machines' address, from a dump)" >&2; exit 1; }
  ko=$(python3 -c 'import json, sys
machines, own, other, frame, more, match = sys.argv[1:7]
seats = [(int(own), frame)]
if more:
    seats += [(s["seat"], more) for s in json.load(open(match))["match"]["setup"]["seats"] if s["seat"] not in (int(own), int(other))]
if len(sys.argv) > 7 and sys.argv[7] == "flags":
    print(",".join("%08X:08@%s-99999999" % (int(machines, 16) + seat * 0x620, at) for seat, at in seats))
else:
    print(",".join("%08X:00@%s-99999999" % (int(machines, 16) + seat * 0x620 + 0x184 + i, at) for seat, at in seats for i in range(4)))' \
    "$KO_MACHINES" "$(cat "$B/$R.seat2")" "$(cat "$B/$R.seat1")" "$KO2" "${KO_MORE:-}" "$B/$R-1.json" "${KO_HOW:-}")
  echo "game 2's racer (seat $(cat "$B/$R.seat2")) is knocked out from race frame $KO2${KO_MORE:+, every racer but the two games own from $KO_MORE}: task poke of $(echo "$ko" | tr ',' '\n' | wc -l) bytes"
fi
rm -f "$B/$R".h0 "$B/$R".h1 "$B/$R".seat1 "$B/$R".seat2
L=${LAUNCHER:-launcher-dev}
for i in 1 $([ -n "${ONE:-}" ] || echo 2); do
  # each game's test settings: its launch file's "debug" part, which the launcher hands on (launcher-run.sh)
  game="\"rollbackLog\":\"$(printf '%s' "$WW\\port\\runs\\$R-$i\\rb.csv" | sed 's/\\/\\\\/g')\""
  jitter=${JITTER:-}; [ $i = 1 ] || jitter=${JITTER2:-$jitter}
  [ -z "$jitter" ] || game="$game,\"jitterMs\":$jitter"
  # the task poke is made from the emulator's task hooks, which only the task timers set up
  [ -z "$ko" ] || game="$game,\"taskTimers\":true,\"pokeTask\":\"$ko\",\"pokeTaskByFrame\":true"
  [ -z "${ROLLBACKS:-}" ] || game="$game,\"forceRollback\":$ROLLBACKS"
  [ -z "${STATES:-}" ] || game="$game,\"trace\":\"$(printf '%s' "$WW\\port\\runs\\$R-$i\\trace.csv" | sed 's/\\/\\\\/g')\",\"traceStates\":[$STATES]"
  [ -z "${DEBUG:-}" ] || game="$game,$DEBUG"
  auto=${AUTO:-1}
  if [ $i = 1 ]; then args="${ARGS1:-}"; input=${INPUT1:-}; lag=${LAG:-0}; [ -z "${DEBUG1:-}" ] || game="$game,$DEBUG1"; else
    args="${ARGS2:-}"; input=${INPUT2:-}; lag=${LAG2:-${LAG:-0}}; [ -z "${DEBUG2:-}" ] || game="$game,$DEBUG2"
    auto=${AUTO2:-$auto}
    [ -z "${CLOCK2:-}" ] || game="$game,\"clock\":\"$CLOCK2\""
    [ -z "${ALTER2:-}" ] || game="$game,\"alterStep\":$ALTER2"
  fi
  card=""; [ $i = 1 ] || card=${CARD2:-}
  (
    # a pad script and a length of its own only when given (launcher-run.sh takes the scene's otherwise)
    if [ -n "$input" ]; then export INPUT="$input"; else unset INPUT; fi
    [ -z "$card" ] || export CARD_FROM="$card"
    settings=${SETTINGS1:-}; [ $i = 1 ] || settings=${SETTINGS2:-}
    if [ -n "$settings" ]; then export SETTINGS="$settings"; else unset SETTINGS; fi
    HAVE_LOCK=1 PACE=1 MATCH=$B/$R-$i.json TITLE="Online-test-$R-game-$i--agent--closes-by-itself" SHOTS="${SHOTS:-}" \
      LAUNCHER=$( [ $i = 2 ] && echo "${LAUNCHER2:-$L}" || echo "$L" ) DATA_NAME=${DATA_PREFIX:-$L-data}-p$i RUNNER_ARGS="$args" AUTOPILOT=$auto LAG=$lag GAME_DEBUG="$game" \
      port/gates/runs/launcher-run.sh "$R-$i" match-race
  ) > "$B/$R-$i.run.log" 2>&1 &
  games="${games:-} $!"
  [ $i = 2 ] || sleep "${HOLD2:-1}"
done
if [ -n "${REJOIN2:-}" ]; then
  # game 2 as it was started above, less its run's name: ended by its process ID REJOIN2 s after the go, started again
  # (the probe's race frame is no clock for this: it counts before the go too)
  run2=$W/port/runs/$R-2
  game2=${game//"\\$R-2\\"/"\\$R-2r\\"}
  (
    for _ in $(seq 1 1500); do   # (5 minutes at most: the server's own end)
      ! grep -qs "race .*: go (" "$B/$R.server.log" || break
      sleep 0.2
    done
    sleep "$REJOIN2"
    lpid=$(tr -d '\r\n' < "$run2/pid.txt")
    gpid=$(game_of "$lpid")
    [ -n "$gpid" ] || { echo "rejoin: game 2's game (the launcher $lpid's child) not found $REJOIN2 s after the go"; exit 1; }
    echo "rejoin: $REJOIN2 s after the go: game 2's game (process $gpid) is ended at $(date +%T.%N | cut -c1-12)"
    taskkill.exe /PID "$gpid" /F > /dev/null
    sleep "${REJOIN2_AFTER:-0}"
    python3 -c 'import json, sys; m = json.load(open(sys.argv[1])); m["rejoin"] = True; json.dump(m, open(sys.argv[2], "w"))' "$B/$R-2.json" "$B/$R-2r.json"
    echo "rejoin: game 2 started again at $(date +%T.%N | cut -c1-12)"
    if [ -n "${INPUT2:-}" ]; then export INPUT="$INPUT2"; else unset INPUT; fi
    HAVE_LOCK=1 PACE=1 MATCH=$B/$R-2r.json TITLE="Online-test-$R-game-2r--agent--closes-by-itself" SHOTS="" \
      LAUNCHER=${LAUNCHER2:-$L} DATA_NAME=${DATA_PREFIX:-$L-data}-p2r RUNNER_ARGS="${ARGS2:-}" AUTOPILOT=${AUTO2:-${AUTO:-1}} \
      LAG=${LAG2:-${LAG:-0}} GAME_DEBUG="$game2" port/gates/runs/launcher-run.sh "$R-2r" match-race
  ) > "$B/$R-2r.run.log" 2>&1 &
  games="$games $!"
fi
if [ -n "${SPECTATE3:-}" ]; then
  # SPECTATE3 s after the go: a bot asks to watch the lobby's race, and a third game starts on its spectator's start
  (
    for _ in $(seq 1 1500); do
      ! grep -qs "race .*: go (" "$B/$R.server.log" || break
      sleep 0.2
    done
    sleep "$SPECTATE3"
    rm -f "$B/$R.w0"
    echo "spectator: $SPECTATE3 s after the go a bot asks to watch at $(date +%T.%N | cut -c1-12)"
    timeout 60 dotnet "$APP_BOTS" --server ws://127.0.0.1:47810/ws --count 1 --name-prefix Watch --watch --handoff "$B/$R.w{0}" \
        --offset 40 --expect 1 --clock-rate "$rate" > "$B/$R.watcher.log" 2>&1 || true
    [ -s "$B/$R.w0" ] || { echo "spectator: no spectator's start (see $B/$R.watcher.log)"; exit 1; }
    python3 -c 'import json, sys
m = json.load(open(sys.argv[1])); m["spectate"] = True; m["match"] = json.load(open(sys.argv[2])); json.dump(m, open(sys.argv[3], "w"))' \
        "$B/$R-1.json" "$B/$R.w0" "$B/$R-3.json"
    game3="\"rollbackLog\":\"$(printf '%s' "$WW\\port\\runs\\$R-3\\rb.csv" | sed 's/\\/\\\\/g')\""
    [ -z "${DEBUG3:-}" ] || game3="$game3,$DEBUG3"
    # (a knock-out by the task poke is the race's: the spectator's game makes it too, or it watches another race)
    [ -z "$ko" ] || game3="$game3,\"taskTimers\":true,\"pokeTask\":\"$ko\",\"pokeTaskByFrame\":true"
    echo "spectator: game 3 started at $(date +%T.%N | cut -c1-12) on $(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["match"]["matchId"])' "$B/$R-3.json")"
    if [ -n "${INPUT3:-}" ]; then export INPUT="$INPUT3"; else unset INPUT; fi
    HAVE_LOCK=1 PACE=1 MATCH=$B/$R-3.json TITLE="Online-test-$R-game-3--agent--closes-by-itself" SHOTS="" \
      LAUNCHER=$L DATA_NAME=${DATA_PREFIX:-$L-data}-p3 RUNNER_ARGS="${ARGS3:-}" AUTOPILOT=0 \
      GAME_DEBUG="$game3" port/gates/runs/launcher-run.sh "$R-3" match-race
  ) > "$B/$R-3.run.log" 2>&1 &
  games="$games $!"
fi
# the games only: the server and the bots are stopped by the exit trap, not waited for
status=0; for g in $games; do wait "$g" || status=1; done
tail -q -n 1 "$B/$R-1.run.log" $([ -n "${ONE:-}" ] || echo "$B/$R-2.run.log") $([ -z "${REJOIN2:-}" ] || echo "$B/$R-2r.run.log") \
    $([ -z "${SPECTATE3:-}" ] || echo "$B/$R-3.run.log")
grep -h "desync\|go (\|spectator" "$B/$R.server.log" | cut -c1-200 || true
# The gate of the port-recomp notes 5.16: every recording of a race with real rollbacks plays back with 0 steps
# differing. The server, the bots and the lock go first: each playback takes the machine itself.
worse() { [ "$1" = 0 ] || [ $status = 1 ] || status=$1; }   # 1 (failed) outranks 4 (did not finish)
if [ "${CHECK:-1}" != 0 ]; then
  stop_ours; pc_release
  config=playback   # (as the race: every playback is)
  s=0; CONFIG=$config port/gates/replay-check.sh "pb-$R" "$W/port/runs/$R-1/race.fzrp" "$W/port/runs/$R-2/race.fzrp" || s=$?; worse $s
  if [ -n "${CHECK_LATE:-}" ]; then
    s=0; CONFIG=$config SET="debug.lateSteps=$CHECK_LATE" port/gates/replay-check.sh "pbl-$R" "$W/port/runs/$R-1/race.fzrp" "$W/port/runs/$R-2/race.fzrp" || s=$?; worse $s
  fi
fi
exit $status
