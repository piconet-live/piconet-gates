#!/bin/bash
# replay-check.sh NAME FILE [FILE...]: the gate of the port-recomp notes 5.16: a recording plays back with 0 steps
# differing. Each FILE (a .fzrp under the work folder, as a WSL or a Windows path) is played back through the
# harness on the native module, uncapped and muted, in a window titled by the check that closes by itself; the
# playback compares every step's checksum with the recorded one and its own count is read from its log.
# Run it on every recording of a race that had real rollbacks (pair-run.sh and quickplay-run.sh do, at their end):
# a rollback that leaves one step's state different from a straight simulation shows here and nowhere else, since
# both games of a race make the same mistake and agree with each other (5.16: the locked cache).
# How the game is started is a launch file (the runner's --config; protocol/formats.md section 2), written for
# each playback from a named one of port/configs into <work>/port/launch/NAME-K.json:
#   CONFIG=NAME   which one (default playback: as the race, as every playback plays);
#                 playback-race-late-2: its inputs known two steps late, so the race runs on predictions and rolls
#                 back as a live race does; forced-*: rollbacks forced every so many frames; control; crash
#   SET="K=JSON .." more keys for a one-off, by their dotted names (launch-file.py): debug.lateSteps=5,
#                 debug.trace={run}\\trace.csv (a line for every checksum kept, in the run's folder),
#                 debug.paceLog={run}\\pace.csv (the pacing log). What the harness needs of the game (its automation
#                 folder allowed, the probe's file, a neutral pad script) is added to every file: launch-file.py --harness
#   BUILD (n6), MAXS (178 s a playback), ARGS (more arguments of the runner's own, as --graphics D3D)
#   HEADLESS=1    no window: the harness's --headless (the runner's null video backend)
#   SHOTS="3000 4200"  fields to take a picture at (<work>/shots, named by the run and the field): two builds'
#                 playbacks of one recording show the same moments
#   RUN_ENV="K=V;K=V"  environment variables for the game: what a library reads for itself (SDL's). A test setting
#                 of the game is never one: the runner reads none there in a start with a launch file (SET=)
#   AT_ONCE=N     N playbacks side by side (default 1: one after the other, as ever). A playback's verdict is its
#                 recorded checksums, step by step, so another game beside it cannot change it; a playback that a
#                 busy PC slows past MAXS reads "did not finish", never a pass. The files are taken N at a time:
#                 one busy check for the set, then its playbacks are started together, each under a name of its
#                 own for the harness (port-pb1, port-pb2, ...: the harness refuses two runs at once under one
#                 name) and in a user folder of its own (<work>/port/user-pb1, ...: the pristine one is copied
#                 into it), and judged in the files' order when the set has ended. A playback of a set that
#                 did not finish is played again, alone, once: "did not finish" says nothing either way, so no
#                 verdict is replaced (one that finished and differed is a FAIL and is not played again). A line
#                 says so; if it does not finish alone either, it reads DID NOT FINISH.
#   NAMES="A B .."  a run name for each file, in place of NAME-1, NAME-2, ...; CONFIGS="X Y .." a launch file for
#                 each file, in place of CONFIG. For a set of playbacks that belong to several rows of the gate
#                 table (gates.sh), each under the name its row has always given it.
#   BUNDLE=<folder>, GAME=<folder>   the native bundle and the game folder BUILD was made from, both under the work
#                 folder (default <work>/port/bundle-native and <work>/port/game-native: module n6's; another
#                 image's module needs its own two, and those of n6 are what the owner's play copy boots)
# Prints one line for each file, ending PASS, FAIL or DID NOT FINISH (gate-judge.py playback reads the playback's
# log: a playback with no summary line, cut by MAXS on a busy PC, is "did not finish: N of M steps", which is not a
# pass and says nothing about differing steps; a crash line or a frozen game is a FAIL), then "replay-check NAME:"
# with the worst of them. Exit status 0 only when every playback compared steps and none differed, 1 when one
# failed, 4 when none failed and one did not finish, 3 when the busy check never allowed a run.
# Output: <work>/port/runs/NAME-K (K: the file's place in the list). The game opens no GameCube controller adapter
# (SDL_JOYSTICK_HIDAPI_GAMECUBE=0; see launcher-run.sh).
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); . "$here/runner.sh" || exit 2   # root: the runner (pins.tsv REPO_RUNNER)
W=${PORT_WORK:-$PORT_WORK_DEFAULT}; WW=${PORT_WORK_WIN:-$(wslpath -w "$W")}   # the build's settings
KIT=$HARNESS_DIR   # the harness: port/gates/vendor/harness, or RECOMP_KIT's
[ $# -ge 2 ] || { sed -n 2,26p "$0"; exit 2; }
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
for gone in MODE LATE FORCE TRACE; do
  [ -z "${!gone:-}" ] || { echo "replay-check: $gone= has gone: name a launch file of port/configs (CONFIG=) or give SET=" >&2; exit 2; }
done
case "${RUN_ENV:-}" in *FZGX_*|*STATICRECOMP*) echo "replay-check: RUN_ENV names a test setting of the game ($RUN_ENV): it is a key of the launch file's \"debug\" part now (SET=\"debug.paceLog={run}\\\\pace.csv\"; protocol/formats.md section 2)" >&2; exit 2;; esac
name=$1; shift
manifest=$(mktemp --suffix=.toml); trap 'rm -f "$manifest"' EXIT
python3 - "$root/recomp/manifest.toml" "$manifest" "${FIELDS:-40000}" "${SHOTS:-}" <<'PY'
import sys
src, dst, fields, shots = sys.argv[1:5]
t = open(src).read()
scene = ('\n[[scene]]\nname = "adhoc"\nexercises = "a replay\'s playback"\nreach = "boot"\ninput = "0:0"\n'
         'fields = %s\n%ssource = "scratch"\n\n' % (fields, "screenshot_fields = [%s]\n" % ", ".join(shots.split()) if shots.split() else ""))
k = t.index('# ---- sources of difference between two runs')
open(dst, 'w').write(t[:k] + scene + t[k:])
PY
B=${BUNDLE:-$W/port/bundle-native}; G=${GAME:-$W/port/game-native}
case "$B" in "$W"/*) ;; *) echo "replay-check: BUNDLE must be under $W" >&2; exit 2;; esac
case "$G" in "$W"/*) ;; *) echo "replay-check: GAME must be under $W" >&2; exit 2;; esac
# what a playback needs, each said with where it comes from, before anything starts
MF=${MACHINE:-$W/port/machine-n.toml}; lacks=""
[ -f "$KIT/recomp.py" ] || lacks+="; the harness ($KIT/recomp.py)"
[ -f "$MF" ] || lacks+="; the machine file $MF (port/setup/install.sh WORK, or MACHINE=FILE)"
[ -f "$B/patches.json" ] || lacks+="; the native bundle $B (BUNDLE=; port/build/build.sh NAME makes port/bundle-NAME)"
[ -f "$G/sys/main.dol" ] || lacks+="; the game folder $G (GAME=; port/build/build.sh NAME makes port/game-NAME from your own disc, which port/setup/setup.sh WORK DISC unpacks$([ -f "$DISC_DEFAULT" ] || printf '; %s' "$(disc_lacks "$DISC_DEFAULT")"))"
for f in "$@"; do [ -f "$f" ] || [ -f "$(wslpath -u "$f" 2> /dev/null)" ] || lacks+="; the recording $f"; done
[ -z "$lacks" ] || { echo "replay-check $name: not run: needs ${lacks#; } (work folder $W)" >&2; exit 2; }
# the module's build recorded the bundle it was made from: another bundle's sites jump into nothing (a guest crash)
inputs=$W/work/cg-${BUILD:-n6}.inputs.json
if [ -f "$inputs" ]; then
  said=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['inputs'].get('bundle',{}).get('mod.bin',''))" "$inputs")
  held=$(sha1sum "$B/mod.bin" | cut -d' ' -f1)
  [ -z "$said" ] || [ "$said" = "$held" ] || { echo "replay-check $name: not run: module ${BUILD:-n6} was built from image ${said:0:8}, and $B holds ${held:0:8}: give BUNDLE= its own" >&2; exit 2; }
fi
BW="$WW\\$(printf %s "${B#"$W"/}" | tr / '\\')"
# the harness takes the game folder from its machine file: the port's, with the folder asked for
machine=$(mktemp --suffix=.toml); outs=$(mktemp -d); trap 'rm -f "$manifest" "$machine" "$machine".pb*; rm -rf "$outs"' EXIT
sed "s|^game = .*|game = \"${G#"$W"/}\"|" "$MF" > "$machine"
grep -q "^game = \"${G#"$W"/}\"" "$machine" || { echo "replay-check: the machine file has no game line" >&2; exit 2; }
export RECOMP_AGENT=${PORT_AGENT:-port} RECOMP_MANIFEST=$manifest RECOMP_MACHINE=$machine
AT=${AT_ONCE:-1}
case "$AT" in ''|*[!0-9]*|0) echo "replay-check: AT_ONCE is a count of playbacks side by side (1, 2, 3)" >&2; exit 2;; esac
# The harness takes the PC with a request file in its machine file's work folder. In a work folder of a build's own
# (PORT_WORK) that is not where the PC's locks are (PORT_LOCKS, by default port/setup/work-folder.env's; cpu-window.sh):
# no other agent would see the request, and the harness would not see their TIMING.lock. So each playback then
# takes a request in the PC's place too, as a build does.
LOCKS=${PORT_LOCKS:-$PORT_LOCKS_DEFAULT}; [ -d "$LOCKS" ] || LOCKS=$W
files=("$@")
read -ra names <<< "${NAMES:-}"; read -ra configs <<< "${CONFIGS:-}"
[ ${#names[@]} = 0 ] || [ ${#names[@]} = ${#files[@]} ] || { echo "replay-check: NAMES names ${#names[@]} runs for ${#files[@]} files" >&2; exit 2; }
[ ${#configs[@]} = 0 ] || [ ${#configs[@]} = ${#files[@]} ] || { echo "replay-check: CONFIGS names ${#configs[@]} launch files for ${#files[@]} files" >&2; exit 2; }
run_of() { if [ ${#names[@]} = 0 ]; then echo "$name-$1"; else echo "${names[$(($1 - 1))]}"; fi; }
# play K SLOT: playback K of the list through the harness; its last lines go to $outs/K. One at a time (SLOT 0): the
# port's own name and user folder. In a set, place SLOT of it: a name and a user folder of that place's own.
play() {
  local k=$1 slot=$2 run f=${files[$(($1 - 1))]} win agent mine sets=() args=() more=() s a e launch config=${CONFIG:-playback}
  run=$(run_of "$k"); [ ${#configs[@]} = 0 ] || config=${configs[$((k - 1))]}
  case "$f" in /mnt/[a-z]/*) win=${f:5:1}; win="${win^^}:\\$(printf %s "${f#/mnt/?/}" | tr / '\\')";; *) win=$f;; esac
  for s in ${SET:-}; do sets+=(--set "$s"); done
  launch=$("$here/runs/launch-file.py" "$config" "$W/port/launch/$run.json" "bundle=$BW" "replay=$win" \
           "run=$WW\\port\\runs\\$run" "${sets[@]}" --harness adhoc --manifest "$manifest") || return 2
  args=(--arg=--title "--arg=Replay-check-$run--agent--closes-by-itself" --arg=--config "--arg=$launch")
  for a in ${ARGS:-}; do args+=("--arg=$a"); done
  IFS=';' read -ra more <<< "${RUN_ENV:-}"; for e in "${more[@]}"; do [ -z "$e" ] || args+=(--env "$e"); done
  if [ "$slot" != 0 ]; then
    agent=port-pb$slot; mine=$machine.pb$slot
    sed -e "s|^user = .*|user = \"port/user-pb$slot\"|" -e "s|^config = .*|config = \"port/user-pb$slot/Config/Dolphin.ini\"|" "$machine" > "$mine"
    grep -q "^user = " "$mine" || echo "user = \"port/user-pb$slot\"" >> "$mine"   # (a machine file that named none: the harness's own default)
  fi
  ( [ "$slot" = 0 ] || export PORT_AGENT=$agent RECOMP_AGENT=$agent RECOMP_MACHINE=$mine
    [ "$LOCKS" -ef "$W" ] || pc_take cpu-window.sh "port: replay check $run (3 min)" 4
    python3 -u "$KIT/recomp.py" run "$run" --scene adhoc --config dual-core --build "${BUILD:-n6}" \
    --not-timing --label "Replay check" --max-seconds "${MAXS:-178}" --env SDL_JOYSTICK_HIDAPI_GAMECUBE=0 \
    ${HEADLESS:+--headless} "${args[@]}" ) 2>&1 | tail -3 > "$outs/$k"
  return 0   # what the harness made of it is read from the run's log, as ever
}
# start: the playbacks of $left (places in the list), together when there are several: the busy check, the start,
# and again for one whose game never started (no log), as ever.
start() {
  local tries=0 slot pids bad pid i run out again why
  while [ ${#left[@]} -gt 0 ]; do
    # the owner is not playing and no other game is up (exit 3 means wait); another agent's game may start between
    # this check and the harness's own start, which then says so: again
    until "$BUSY" > /dev/null; do
      tries=$((tries + 1)); [ $tries -le 60 ] || { echo "$(run_of "${left[0]}"): the busy check said wait for 20 minutes; not run"; exit 3; }
      sleep 20
    done
    # and Windows has the memory left for these games (room-for-games.sh: a start without it has taken the PC down)
    why=$("$here/room-for-games.sh" ${#left[@]}) || { echo "$(run_of "${left[0]}"): not run: $why"; exit 3; }
    if [ "$AT" = 1 ]; then play "${left[0]}" 0 || exit 2
    else   # the set, together; a playback whose launch file could not be written ends the check, as ever
      slot=0; pids=(); for i in "${left[@]}"; do slot=$((slot + 1)); play "$i" "$slot" & pids+=($!); done
      bad=0; for pid in "${pids[@]}"; do wait "$pid" || [ $? != 2 ] || bad=1; done
      [ $bad = 0 ] || { cat "$outs"/* 2> /dev/null >&2; exit 2; }
    fi
    again=()
    for i in "${left[@]}"; do
      run=$(run_of "$i"); out=$(cat "$outs/$i" 2> /dev/null)
      case "$out" in *"cpu-window: TIMING.lock still there"*) echo "$run: the machine was not free in 40 minutes; not run"; exit 3;; esac
      if [ -f "$W/port/runs/$run/stderr.txt" ]; then cp "$W/port/launch/$run.json" "$W/port/runs/$run/launch.json"; else again+=("$i"); fi
    done
    left=("${again[@]}")
    [ ${#left[@]} -eq 0 ] && break
    tries=$((tries + 1)); [ $tries -le 60 ] || { echo "$(run_of "${left[0]}"): never started: $(cat "$outs/${left[0]}" 2> /dev/null)"; exit 3; }
    sleep 20
  done
}
failed=0; cut=0; k=0
while [ $k -lt ${#files[@]} ]; do
  set=(); while [ ${#set[@]} -lt "$AT" ] && [ $k -lt ${#files[@]} ]; do k=$((k + 1)); set+=("$k"); done
  left=("${set[@]}"); start
  for i in "${set[@]}"; do
    said=$("$here/gate-judge.py" playback "$(run_of "$i")" "${files[$((i - 1))]}" --limit "${MAXS:-178}"); s=$?
    if [ $s = 4 ] && [ ${#set[@]} -gt 1 ]; then
      # beside the others it did not finish, which says nothing either way: once more, alone. (A playback that
      # finished is never played again: what it compared stands.)
      echo "$(run_of "$i"): it did not finish beside the others of its set ($(printf '%s' "$said" | sed -n 's/^[^:]*: [^:]*: did not finish: \(.*\): DID NOT FINISH$/\1/p' | head -1)): played again, alone"
      left=("$i"); start
      said=$("$here/gate-judge.py" playback "$(run_of "$i")" "${files[$((i - 1))]}" --limit "${MAXS:-178}"); s=$?
    fi
    [ -z "$said" ] || printf '%s\n' "$said"
    case $s in 0) ;; 4) cut=1;; *) failed=1;; esac
  done
done
if [ $failed != 0 ]; then echo "replay-check $name: FAIL"; exit 1; fi
if [ $cut != 0 ]; then echo "replay-check $name: DID NOT FINISH"; exit 4; fi
echo "replay-check $name: PASS"
