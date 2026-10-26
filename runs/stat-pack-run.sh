#!/bin/bash
# stat-pack-run.sh RUN: the proving run of stat packs (handbook/stat-packs.md): six races, ten playbacks,
# six refusals and a report. Not a gate row. The packs are made up here from the disc's own car data
# (stat-pack.py): pack A doubles one machine's weight, moves one of its hover points and makes the first custom
# body heavier; pack B is A with the weight tripled; pack W is the size of a whole replacement file (all 5,104
# values, the bytes at 0x48 among them) with every machine 2% heavier. Nothing of a real pack is used, and the
# files stay under <work>/port/scratch/stat-pack.
#   plain   RUN-plain    no pack: the match race of the gates' row `match` (one player, 29 computer racers) against
#                   the JIT reference's kept run. The game must be the game it was: every step's machine hashes
#                   equal, the recording version 2, not a word of a stat pack in its log.
#   plain2  RUN-plain2   no pack, two games and rollbacks: two games of this build race each other among 6
#                   simulated players and 22 computer racers, rollbacks forced every 7 frames to depths 3, 9 and
#                   17, a test lag of 30 ms; then both recordings are played back on the build from before stat
#                   packs (STOCK's runner; runs pbs-RUN-plain2-1, -2). Version 2 recordings, no word of a stat pack
#                   in either log, the checksums equal to the end, both playbacks 0 steps differing.
#   old     pbo-RUN-1, -2   the other way round: two recordings the build from before stat packs made (OLD's first
#                   race: two launchers, 4 simulated players, 24 computer racers, real rollbacks) played back on
#                   this build with a rollback forced every 2 frames (forced-race-2x3-9-17): 0 steps differing.
#   pack    RUN-pack     two games race each other on pack A (pair-run.sh), both on the changed machine, among 6
#                   simulated players and 22 computer racers (CPU level 3), rollbacks forced as above, a test lag
#                   of 30 ms; then both recordings are played back. The pack must be laid in both, the checksums
#                   equal to the end, both playbacks 0 steps differing, the recordings version 3 with the pack in
#                   their header, and the doubled weight in the racers' blocks (each game's dump of the machines'
#                   state before steps 300 and 301).
#   two     RUN-two      two games among 28 simulated players, game 1 handed pack A and game 2 pack B. Each game
#                   knows only its own pack, so both start: the games must differ from the first step, and the test
#                   server's relay must say so at the first checksum it compares. No playbacks.
#   server  RUN-srv      the pack from a server: a test server started with --stat-pack on pack W's file, computer
#                   racers always and at CPU level 1, and two launchers that go through Quick Play to one race
#                   (quickplay-run.sh: the lobby, the start vote, the match start, the game), a test lag of 50 ms;
#                   then both replays are played back (pb-RUN-srv-1-1, -2-1). The server must name W at its start,
#                   both games lay all its values, the checksums be equal to the end, the playbacks 0 steps
#                   differing, the replays version 3 with W in their header, 28 computer racers at level 1.
#   real    RUN-real     two games race each other on a pack of the repository (PACK: GX Unleashed), read from its
#                   file here a third way beside the launcher's and the server's reader (stat-pack.py wire: the
#                   fingerprint must be the one the file's head says), both on PLAYER_MACHINE among 6 simulated
#                   players and 22 computer racers, rollbacks forced as above; then both recordings are played
#                   back. Judged as RUN-pack: laid in both, the checksums equal, both playbacks 0 steps differing.
#   refused RUN-no-KIND, RUN-game-KIND   three packs nobody may take, each of one value: KIND denormal (a machine's
#                   weight of the bits 00000001), negative (a machine's Grip1 of -50, below its floor of minus
#                   its most, -45) and part (a body's Grip2 of -10.5, past the size a part's value
#                   may have). The launcher, handed a match file with the pack (--play-match), must refuse the
#                   start with its sentence and start no game; the game, handed the pack past the launcher
#                   (stat-pack-refused.sh), must say that it refuses it.
# Before the races the staged launcher imports pack A from the changed car data file (--import-stat-pack, with the
# disc image you set, DISC_DEFAULT): its fingerprint must be the one stat-pack.py worked out by itself.
# Then port/gates/reports/stat-pack-report.py RUN reads the logs; its last line is "stat packs RUN: PASS" or FAIL.
#   PLAYER_MACHINE (6)  the machine whose weight packs A and B change, and both players' machine in the pair races
#   ONLY            one of the names above: that part alone, and the report judges that part alone
#   PACK ($APP_PROTOCOL/packs/gx-unleashed.fzstats: the protocol's packs, port/setup/app.sh)  the pack `real` races on
#   SETTING1, SETTING2  `real`'s two players' machine settings (pair-run.sh; F-Zero GX+ at 0 and 100: the machine
#                   setting's curve at its two ends)
#   LAUNCHER (launcher-dev)  the staged copy under test: its runner and launcher must be this branch's or later (an
#                   older runner ignores a pack). The playbacks run through the harness on that copy's own parts:
#                   its runner (a machine file made here, as gates.sh makes one), its bundle and its game folder,
#                   and the module BUILD (w12). BUNDLE, GAME and MACHINE name others.
#   STOCK (launcher-dev)  the staged copy of the build from before stat packs (the players' build of 8 October,
#                   runner 672749d2), for plain2's playbacks: its runner, its bundle, its game folder
#   OLD (w12gate-qp)  the Quick Play run whose kept replays `old` plays back: <work>/port/runs/OLD-1 and OLD-2
#   CLOCKRATE, LAG (30): as pair-run.sh's.
# Bounds: every game 170 s at most (the Quick Play visit 6 minutes for its one race), every playback 178 s, muted,
# each window titled by its run; the scripts called take the PC themselves one after another (timing-lock.sh, the
# harness), and before each race this script waits for the busy check to say that nobody plays. About 45 minutes
# in all: say so first.
# Exit status: 1 when a part or the import failed or the report says FAIL; 3 when the busy check never allowed it.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); cd "$here/../../.."
. "$here/../../setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}
R=${1:?stat-pack-run.sh RUN}; L=${LAUNCHER:-launcher-dev}; M=${PLAYER_MACHINE:-6}; only=${ONLY:-}
. "$here/../../setup/app.sh" || exit 1   # APP_PROTOCOL: the protocol's folder, from its checkout (port/setup/pins.tsv, REPO_PROTOCOL)
S=${STOCK:-launcher-dev}; OLD=${OLD:-w12gate-qp}; PACK=${PACK:-$APP_PROTOCOL/packs/gx-unleashed.fzstats}
P=$W/port/scratch/stat-pack; mkdir -p "$P"
LD=$W/port/$L
[ -f "$LD/Launcher.App.exe" ] && [ -f "$LD/recomp/moderngekko-run.exe" ] || { echo "stat-pack-run: no staged launcher $LD (port/build/stage-launcher.sh)" >&2; exit 1; }
# the playbacks' parts: the staged copy's own (gates.sh does the same)
machine_file() { { grep -v '^runner *=' "$W/port/machine-n.toml"; echo "runner = \"port/$1/recomp/moderngekko-run.exe\""; } > "$2"; }
if [ -z "${MACHINE:-}" ]; then machine_file "$L" "$P/$R.machine.toml"; MACHINE=$P/$R.machine.toml; fi
game_of() { readlink -f "$W/port/$1/recomp/game" 2> /dev/null || echo "$W/port/$1/recomp/game"; }
export LAUNCHER=$L BUILD=${BUILD:-w12} BUNDLE=${BUNDLE:-$LD/recomp/fzgx} GAME=${GAME:-$(game_of "$L")} MACHINE
car=$W/extracted/GFZE01/files/game/cardata.lz
disc=$DISC_DEFAULT   # your setting, a row of ~/.config/piconet/pins.tsv (port/setup/lib.sh)
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
nobody_plays() {   # the owner is not playing and no game is up (exit 3 means wait): 20 minutes at most
  local tries=0
  until "$BUSY" > /dev/null; do tries=$((tries + 1)); [ $tries -le 60 ] || { echo "stat-pack-run: the busy check said wait for 20 minutes" >&2; return 1; }; sleep 20; done
}
part() { [ -z "$only" ] || [ "$only" = "$1" ]; }
forced='{"every":7,"depths":[3,9,17]}'
status=0
python3 "$here/stat-pack.py" make "$car" "$P/$R-a" "$M" 2 "Made up A" || exit 1
python3 "$here/stat-pack.py" make "$car" "$P/$R-b" "$M" 3 "Made up B" || exit 1
python3 "$here/stat-pack.py" whole "$car" "$P/$R-w" 6 "Made up W" || exit 1   # (6: launcher 2's machine in Quick Play)
python3 "$here/stat-pack.py" wire "$PACK" "$P/$R-real" || exit 1
# the launcher's own import of the changed file: a data folder of its own, never the player's
rm -f "$P/$R-a.fzstats"
"$W/port/$L/Launcher.App.exe" --data "$WW\\port\\$L-data-stat-pack" --import-stat-pack "$(wslpath -w "$P/$R-a.cardata")" \
    --pack-name "Made up A" --disc "$(wslpath -w "$disc")" --out "$(wslpath -w "$P/$R-a.fzstats")" \
    > "$P/$R.import.log" 2>&1 < /dev/null || { echo "stat-pack-run: the import failed (see $P/$R.import.log)" >&2; status=1; }
tr -d '\r' < "$P/$R.import.log"
rate=${CLOCKRATE:-$(python3 "$here/clock-rate.py")}
if part plain; then
  nobody_plays || exit 3
  CLOCKRATE=$rate FROM=nmj "$here/match-run.sh" "$R-plain" || status=1
fi
if part plain2; then
  nobody_plays || exit 3
  CLOCKRATE=$rate PLAYER_MACHINE=$M BOTCOUNT=6 ROLLBACKS=$forced LAG=${LAG:-30} CHECK=0 "$here/pair-run.sh" "$R-plain2" || status=1
  machine_file "$S" "$P/$R.stock.toml"
  MACHINE=$P/$R.stock.toml BUNDLE=$W/port/$S/recomp/fzgx GAME=$(game_of "$S") CONFIG=playback \
    "$here/../replay-check.sh" "pbs-$R-plain2" "$W/port/runs/$R-plain2-1/race.fzrp" "$W/port/runs/$R-plain2-2/race.fzrp" || status=1
fi
if part old; then
  old=(); for i in 1 2; do old+=("$(ls "$W/port/runs/$OLD-$i/replays"/*.fzrp 2> /dev/null | head -1)"); done
  if [ -f "${old[0]}" ] && [ -f "${old[1]}" ]; then
    printf '%s\n' "${old[@]}" > "$P/$R.old.txt"
    CONFIG=forced-race-2x3-9-17 "$here/../replay-check.sh" "pbo-$R" "${old[@]}" || status=1
  else echo "stat-pack-run: no kept replays of $OLD (<work>/port/runs/$OLD-1/replays, $OLD-2)" >&2; status=1; fi
fi
if part pack; then
  nobody_plays || exit 3
  CLOCKRATE=$rate PLAYER_MACHINE=$M BOTCOUNT=6 STATS1="$P/$R-a.json" STATS2="$P/$R-a.json" ROLLBACKS=$forced \
    STATES=300,302 LAG=${LAG:-30} "$here/pair-run.sh" "$R-pack" || status=1
fi
if part two; then
  nobody_plays || exit 3
  CLOCKRATE=$rate PLAYER_MACHINE=$M STATS1="$P/$R-a.json" STATS2="$P/$R-b.json" LAG=${LAG:-30} CHECK=0 "$here/pair-run.sh" "$R-two" || status=1
fi
if part server; then
  trace() { printf '"trace":"%s","traceStates":[300,302]' "$(printf '%s' "$WW\\port\\runs\\$R-srv-$1\\trace.csv" | sed 's/\\/\\\\/g')"; }
  CLOCKRATE=$rate LAUNCHERS=2 RACES=1 FIXED=1 COURSE=16 LAG=50 MINUTES=6 GAME1=$(trace 1) GAME2=$(trace 2) \
    SERVER_ARGS="--stat-pack $P/$R-w.fzstats --cpu-fill always --cpu-level 1" "$here/quickplay-run.sh" "$R-srv" || status=1
fi
if part real; then
  nobody_plays || exit 3
  CLOCKRATE=$rate PLAYER_MACHINE=$M BOTCOUNT=6 STATS1="$P/$R-real.json" STATS2="$P/$R-real.json" ROLLBACKS=$forced \
    STATES=300,302 LAG=${LAG:-30} SETTING1=${SETTING1:-} SETTING2=${SETTING2:-} "$here/pair-run.sh" "$R-real" || status=1
fi
if part refused; then
  for kind in denormal negative part; do
    values=$(python3 "$here/stat-pack.py" bad "$P/$R-no-$kind" "$kind" "$M") || exit 1
    nobody_plays || exit 3
    # the launcher refuses and leaves at once, which launcher-run.sh calls a game that is gone: its status is not read
    DATA_NAME=$L-data-stat-pack MATCH=$P/$R-no-$kind.json AUTOPILOT=1 TITLE="Stat-pack-refused-$R-$kind--agent--closes-by-itself" \
      "$here/launcher-run.sh" "$R-no-$kind" match-race > "$P/$R-no-$kind.log" 2>&1 || true
    echo "$R-no-$kind: $(grep -a 'stat pack' "$W/port/runs/$R-no-$kind/stderr.txt" 2> /dev/null | head -1 | tr -d '\r' | cut -c1-200)"
    "$here/stat-pack-refused.sh" "$R-game-$kind" "$values" || status=1
  done
fi
"$here/../reports/stat-pack-report.py" "$R" "$M" ${only:+--only "$only"} || status=1
exit $status
