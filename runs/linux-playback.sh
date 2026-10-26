#!/bin/bash
# linux-playback.sh RUN FILE: a recording played back by the Linux runner and module (port/build/linux.sh), headless
# (no window, the null video backend), muted, uncapped, in WSL, as the race (a runner from before 0.3.0 played a file
# without "view" in the game's replay mode, retired since). The playback compares every step's checksum with the
# recorded one, as replay-check.sh's do on Windows; its last lines say how many differed.
#   DEBUG    more keys of the launch file's "debug" part, as JSON without braces: '"lateSteps": 2',
#            '"forceRollback": {"every": 1, "depths": [6]}'. The trace of every checksum kept is always written
#            (RUN/trace.csv: compare it with a Windows playback's, replay-check.sh SET='debug.trace="{run}\\trace.csv"')
#   BUILD    the parts: LB/gen/mod-cg-BUILD and LB/run/game-BUILD, bundle-BUILD (default v020l; GAME_OF names the
#            game and bundle's name when it differs: default the BUILD without its last letter, v020)
#   MAXS     seconds at most (default 178)
# Output in LB/run/runs/RUN (LB: LINUX_BUILD, default ~/linux-build). Exit 0 only when steps were compared and none
# differed; 1 differed; 4 no summary line (cut by MAXS, or a crash: read RUN/stderr.txt); 3 the busy check said wait.
# A game started by hand takes the PC's turn: ( PORT_AGENT=NAME; . port/setup/lib.sh; pc_take timing-lock.sh "what" 4; this ).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
. "$root/port/setup/lib.sh"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
LB=${LINUX_BUILD:-$HOME/linux-build}; B=${BUILD:-v020l}; GN=${GAME_OF:-${B%?}}
run=${1:?linux-playback.sh RUN FILE} file=${2:?linux-playback.sh RUN FILE}
case $run in ''|*/*|.|..) echo "linux-playback: RUN is one plain name" >&2; exit 2 ;; esac
R=$LB/run/runs/$run; M=$LB/gen/mod-cg-$B/gGFZE01_recomp.so; G=$LB/run/game-$GN
for f in "$M" "$G/sys/main.dol" "$LB/run/bundle-$GN/mod.bin" "$file"; do [ -f "$f" ] || { echo "linux-playback: no $f" >&2; exit 2; }; done
"$BUSY" > /dev/null || { echo "linux-playback: the busy check says wait"; exit 3; }
rm -rf "$R"; mkdir -p "$R"; cp -r "$W/port/user-pristine" "$R/user"; cp "$file" "$R/replay.fzrp"
# the harness's emulator settings (no speed limit, the fixed clock), with the null backends for picture and sound
sed 's/^GFXBackend = .*/GFXBackend = Null/; s/^Backend = Cubeb/Backend = No Audio Output/' "$root/port/setup/Dolphin.ini.pristine" > "$R/user/Config/Dolphin.ini"
cat > "$R/launch.json" <<EOF
{
  "about": "A recording played back headless on Linux, every step compared with the recorded checksum (linux-playback.sh)",
  "bundle": "$LB/run/bundle-$GN",
  "widescreen": true,
  "showFrameRate": true,
  "replay": {"file": "$R/replay.fzrp", "scrubber": false},
  "debug": {"automation": true, "userSettings": true, "pad": "0:0", "trace": "$R/trace.csv"${DEBUG:+, $DEBUG}}
}
EOF
start=$(date +%s)
# --headless: no window, the null video backend (forks/moderngekko 0005)
( cd "$R" && SDL_JOYSTICK_HIDAPI_GAMECUBE=0 timeout --signal=INT --kill-after=10 "${MAXS:-178}" "$LB/out/mg/moderngekko-run" \
    --headless --mute --no-mods --automation-dir "$R/auto" --game "$G" --user-dir "$R/user" --module "$M" \
    --title "Linux-playback-$run--agent--closes-by-itself" --config "$R/launch.json" > "$R/stdout.txt" 2> "$R/stderr.txt" )
echo "$run: the game ended with status $? after $(( $(date +%s) - start )) s"
said=$(grep -h -o "^fzgx: playback: [0-9]* of [0-9]* steps compared with the recording, [0-9]* differed[^\"]*" "$R/stderr.txt" | tail -1)
[ -n "$said" ] || { echo "$run: no summary line (see $R/stderr.txt): DID NOT FINISH"; exit 4; }
echo "$run: ${said#fzgx: }"
case $said in *", 0 differed"*) echo "$run: PASS"; exit 0;; *) grep -h "differs from the recording first" "$R/stderr.txt" | head -1; echo "$run: FAIL"; exit 1;; esac
