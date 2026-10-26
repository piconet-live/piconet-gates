#!/bin/bash
# match-file.sh OUT [FROM]: a match file for a test race of one player among CPU racers, as the launcher writes one
# when the coordinator starts a match (dolphin-fzgx Core/FzgxBoot.h describes it). Starts a test server on this
# computer (the coordinator and its relay, in WSL; it ends by itself after SERVER_SECONDS, default 420), lets a
# stand-in player queue, vote to start and ask for CPU racers, and writes the coordinator's match start with the
# launcher's own values to OUT. The game then takes the stand-in's place on the relay with the match's token.
# With FROM (an earlier OUT): the same race again. The set-up (course, laps, seats, machines, names, colours, seeds)
# is FROM's; only the relay's port, the token and the match's name are the new server's. Two runs of one set-up must
# give the same race.
#   COURSE (default 16, Casino Palace: Split Oval), LAPS (1), MACHINE (the stand-in's; default the bot's), STOCK (a
#   stock colour 0-3), PLAYER (the name, default Port), DELAY (2), OC (6.0), CLOCKRATE (1.038: WSL's clock runs slow
#   against Windows' here), RELAY_HOST (this WSL's address, which a Windows game reaches).
# Who drives the player's seat is no part of a match file: the game's AI drives it when the game's launch file says
# "debug.autopilot" (launcher-run.sh AUTOPILOT=1), so that the race is the same every time.
# Leaves: OUT, OUT.server.log, and server.pid beside OUT (stop the server early with `kill $(cat server.pid)`). A
# test server an earlier call left running is stopped first, by that file's process ID: there is one port.
# A match file holds a relay token of a test server that is gone minutes later; it is still never committed.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
out=$1; from=${2:-}
host=${RELAY_HOST:-$(ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1)}
rate=${CLOCKRATE:-1.038}
source "$here/../../setup/app.sh"; server=$APP_SERVER; bots=$APP_BOTS
[ -f "$server" ] && [ -f "$bots" ] || { echo "match-file: build the application first ($APP_BUILD)" >&2; exit 1; }
rm -f "$out" "$out.handoff"
pidfile=$(dirname "$out")/server.pid
if [ -s "$pidfile" ] && grep -qs "Online.Server" "/proc/$(cat "$pidfile")/cmdline"; then kill "$(cat "$pidfile")"; sleep 1; fi
setsid timeout "${SERVER_SECONDS:-420}" dotnet "$server" --no-announce --allow-ai-inputs --start-timeout 240 --voting-minimum 1 \
    --course "${COURSE:-16}" --laps "${LAPS:-1}" --clock-rate "$rate" > "$out.server.log" 2>&1 < /dev/null &
echo $! > "$pidfile"
"$(dirname "$0")/server-up.sh" 127.0.0.1 "$out.server.log" || exit 1
timeout 120 dotnet "$bots" --server ws://127.0.0.1:47810/ws --count 1 --name-prefix "${PLAYER:-Port}" --handoff "$out.handoff" \
    --offset 1 --expect 1 --start-voters 1 --cpu-voters 1 --clock-rate "$rate" \
    ${MACHINE:+--machine $MACHINE} ${STOCK:+--stock-color $STOCK} > "$out.bot.log" 2>&1 || true
[ -s "$out.handoff" ] || { echo "match-file: no match started (see $out.server.log, $out.bot.log)" >&2; kill "$(cat "$pidfile")" 2> /dev/null; exit 1; }
python3 - "$out.handoff" "$out" "$host" "${DELAY:-2}" "${OC:-6.0}" "$from" <<'PY'
import json, sys
handoff, out, host, delay, oc, earlier = sys.argv[1:7]
match = json.load(open(handoff))
if earlier:
    old = json.load(open(earlier))["match"]
    match["setup"], match["seat"] = old["setup"], old["seat"]
json.dump({"match": match, "relayHost": host, "delay": int(delay), "overclock": float(oc), "otherSounds": "quieter"},
          open(out, "w"))
s = match["setup"]
print(f"match {match['matchId']}: course {s['course']}, {s['laps']} lap(s), {len(s['seats'])} seats, seat {match['seat']}, "
      f"seeds {s['shuffleSeed']:#x} {s['cpuSeed']:#x}, relay {match['relay']['host'] or host}:{match['relay']['port']}"
      + (", set-up from " + earlier if earlier else ""))
PY
rm -f "$out.handoff"
