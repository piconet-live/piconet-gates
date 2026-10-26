#!/bin/bash
# runs/profile.sh NAME [--dry-run]: a fresh profile for the module of build NAME, trained from nothing but what setup.sh
# and steps 1 to 4 of port/build/build.sh NAME made (the recompiler, port/bundle-NAME, port/game-NAME, the runner):
# no saved state, no kept run, no older profile. In the work folder PORT_WORK:
#   1. the instrumented module NAMEgen (port/build/native-module.sh --profile-generate), about 9 minutes
#   2. if the work folder has no save file yet (port/user-pristine): one first boot of the game on NAMEgen, which
#      creates it (the manifest's scene boot-first, a user folder with no memory card); about a minute
#   3. the training run: the scene boot-menus on NAMEgen, 7,000 fields: boot, logos, title, the menus with every
#      default, and 2,400 fields of a 30-machine Grand Prix race on Twist Road; about two minutes
#   4. llvm-profdata merges what the runs wrote into PORT_WORK/scratch/pgo-NAME/a.profdata
# Then: PROFILE=$PORT_WORK/scratch/pgo-NAME/a.profdata port/build/build.sh NAME
# It trained the final build's profile on 2026-10-08 in its own work folder (9 minutes in all: the instrumented module 7.8,
# the two games 72 s). It needs the harness (vendor/harness, beside runs/) and the runner
# (step 4 of build.sh), which runs the two games. One of the gates' recipes (moved from port/setup on 2026-10-25):
# training the profile is our release process; a public build takes the profile handed out with a release
# (setup.sh --profile FILE) or builds without one (PROFILE=none port/build/build.sh NAME).
# The game runs are the harness's: muted, labelled "Port test", bounded (170 s), with the fixed clock,
# and with SDL_JOYSTICK_HIDAPI_GAMECUBE=0 in the game's environment: without it a test game takes the owner's
# GameCube adapter away from their own game (a standing rule for every script that starts a game).
# A profile is never the same bytes twice (its counts come from real runs), and it is not kept: a module that is
# built again is trained again. The module's manifest records the profile's SHA-1, so that two builds can be told
# apart.
# What this profile does not cover: an online race. Its code (the image's routines in a race from a match file,
# the relay's hook) is compiled without counts until a second training run is added, a match race through a
# launcher staged in the same work folder (n6's second run).
#   TOOL, SWITCHES  another recompiler folder under <work>/work and another switches file than the released
#                   build's (dolrecomp-port, pins.tsv REPO_SWITCHES), as build-module.sh takes them (the instrumented
#                   module is the runner's CMake target module, through native-module.sh)
#   BUNDLE, GAME    the bundle and the game folder of an image that is not this build's own (default
#                   <work>/port/bundle-NAME and port/game-NAME): a module with other switches on a kept image
#   RUNNER=<file>   the runner the two games run on, a file under the work folder (default: the one that stands in
#                   ModernGekko/build, which every runner build writes: a release build names its own kept runner)
#   AGAIN=1         the folders of NAMEgen are this caller's own, from a try that stopped: they are replaced
#                   (scripts/release-build.sh --from). Without it a name whose instrumented module exists is refused
#   SKIP_GEN=1      the instrumented module NAMEgen is there and is kept (a training run that failed): train and
#                   merge only
# The harness runs the games under the name <PORT_AGENT>-train: it keeps a request file of its own, and refuses
# to work beside this script's (BUILD.wanted.<PORT_AGENT>) when both carry one name and the locks are in one folder.
# Takes the PC itself (this PC's cpu-window.sh, PC_SCRIPTS), after the busy check, where this PC's machine sharing is there.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); root=$(cd "$here/../../.." && pwd)
. "$root/port/setup/lib.sh"
find_tools || exit 1   # llvm-profdata, LLVM's
N=${1:?profile.sh NAME [--dry-run]}; DRY=${2:-}
W=${PORT_WORK:?PORT_WORK: the work folder setup.sh made}; WW=$(wslpath -w "$W"); export PORT_WORK_WIN=$WW
K=$HARNESS_DIR/recomp.py   # the harness: the gates' vendor/harness, or RECOMP_KIT's
G=${N}gen; P=$W/scratch/pgo-$N; BUSY=${BUSY_CHECK:-$W/port/scratch/rp/chk.sh}; B=${BUNDLE:-$W/port/bundle-$N}
TOOL=${TOOL:-dolrecomp-port}; SWITCHES=${SWITCHES:-$root/$REPO_SWITCHES}; GAME=${GAME:-$W/port/game-$N}
BW="$WW\\$(printf %s "${B#"$W"/}" | tr / '\\')"
RUNNER=${RUNNER:-$W/ModernGekko/build/moderngekko-run.exe}
pc_sharing "$BUSY"
case "$RUNNER" in "$W"/*) ;; *) echo "profile: RUNNER must be a file under $W (the harness names it from there)" >&2; exit 1;; esac
X="805960D4:$W/derived/loaded-05-movie.bin 8059EF6C:$W/derived/loaded-0c-movie_module.bin"
export RECOMP_AGENT=${PORT_AGENT:-port}-train RECOMP_MANIFEST=$root/recomp/manifest.toml
# how the game is started: the launch file port/configs/boot-single-core.json with this build's bundle and what the
# harness needs of the game (launch-file.py --harness), written anew for each run
LF=$W/port/launch/$N-profile.json; LFW="$WW\\port\\launch\\$N-profile.json"
run() {  # run name, scene, machine file, fields: one harness run on the instrumented module
  [ -n "$DRY" ] || "$here/launch-file.py" boot-single-core "$LF" "bundle=$BW" "run=$WW\\port\\runs\\$1" --harness "$2" > /dev/null
  RECOMP_MACHINE=$W/port/$3 python3 -u "$K" ${DRY:+--dry-run} run "$1" --scene "$2" --config single-core --fields "$4" --build "$G" \
    --env SDL_JOYSTICK_HIDAPI_GAMECUBE=0 --arg=--config "--arg=$LFW" --not-timing --label "Port test" \
    --arg=--title --arg=Port-test--agent-profile-training--closes-by-itself --max-seconds 170 2>&1 | { [ -n "$DRY" ] && grep -E "^[0-9]\.|powershell" | cut -c1-200 || tail -3; }
}
step() { echo "== $(date +%T) $*"; }
for f in "$K" "$RUNNER" "$W/work/$TOOL/dolrecomp.exe" "$SWITCHES" "$B/patches.json" \
         "$GAME/sys/main.dol" "$W/port/machine-n.toml" "$W/port/user-first-pristine/Config/Dolphin.ini"; do
  [ -e "$f" ] || { echo "profile: missing $f" >&2; [ -n "$DRY" ] || exit 1; }
done
[ -n "$DRY" ] || [ -n "${AGAIN:-}${SKIP_GEN:-}" ] || [ ! -e "$W/work/mod-cg-$G" ] || { echo "profile: $W/work/mod-cg-$G exists; choose another name" >&2; exit 1; }
cd "$root"
[ -n "$DRY" ] || wait_while_busy "$BUSY" || exit 3

step "the instrumented module $G"
gen="BUNDLE=$B TOOL=$TOOL SWITCHES=$SWITCHES EXTRA=\"$X\" port/build/native-module.sh $G --profile-generate '$WW\\scratch\\pgo-$N\\gx-%m.profraw'"
if [ -n "$DRY" ]; then echo "  $gen"
elif [ -n "${SKIP_GEN:-}" ]; then
  [ -f "$W/work/mod-cg-$G/gGFZE01_recomp.dll" ] || { echo "profile: SKIP_GEN: no instrumented module $G" >&2; exit 1; }
  echo "  $G is there: not built again"; mkdir -p "$P"; rm -f "$P"/*.profraw "$P/a.profdata"
else
  rm -rf "$P"; mkdir -p "$P"
  ( pc_take native-build-lock.sh "instrumented module $G (about 9 min)" 12
    pc_take cpu-window.sh "instrumented module $G (about 9 min)" 12
    BUNDLE=$B TOOL=$TOOL SWITCHES=$SWITCHES EXTRA="$X" port/build/native-module.sh "$G" --profile-generate "$WW\\scratch\\pgo-$N\\gx-%m.profraw" | tail -2 )
  [ -f "$W/work/mod-cg-$G/gGFZE01_recomp.dll" ] || { echo "profile: no instrumented module (see $W/work/cg-$G.log)" >&2; exit 1; }
fi

# the harness's machine file for this build: its own game folder
# and the runner the games run on (a machine file without the line runs the harness's default: it is written)
[ -z "$DRY" ] || echo "  the two games run on ${RUNNER#"$W"/}"
[ -n "$DRY" ] || { grep -v '^runner *=' "$W/port/machine-n.toml" | sed -e "s|^game = .*|game = \"${GAME#"$W"/}\"|"
                   echo "runner = \"${RUNNER#"$W"/}\""; } > "$W/port/machine-train.toml"
if [ ! -d "$W/port/user-pristine/GC" ]; then
  step "a first boot, for the save file"
  # the machine file of a boot of the native game folder, with the user folder of a first boot
  if [ -z "$DRY" ]; then
    sed -e 's|^user = .*|user = "port/user-first"|' -e 's|^user_pristine = .*|user_pristine = "port/user-first-pristine"|' \
        -e 's|^config = .*|config = "port/user-first/Config/Dolphin.ini"|' "$W/port/machine-train.toml" > "$W/port/machine-train-first.toml"
  fi
  if [ -z "$DRY" ]; then
    wait_while_busy "$BUSY" || exit 3
    rm -rf "$W/port/user-first"
  fi
  ( [ -n "$DRY" ] || pc_take cpu-window.sh "profile training: a first boot (1 min)" 4
    run "tr-$N-first" boot-first "$([ -n "$DRY" ] && echo machine-n.toml || echo machine-train-first.toml)" 3300 )
  if [ -z "$DRY" ]; then
    ls "$W/port/user-first/GC/USA/Card A/"*.gci > /dev/null 2>&1 || { echo "profile: the first boot made no save file (see $W/port/runs/tr-$N-first)" >&2; exit 1; }
    mkdir -p "$W/port/user-pristine"; cp -r "$W/port/user-first-pristine/." "$W/port/user-pristine/"; cp -r "$W/port/user-first/GC" "$W/port/user-pristine/"
  fi
fi

step "the training run: boot, menus, a Grand Prix race"
[ -n "$DRY" ] || wait_while_busy "$BUSY" || exit 3
( [ -n "$DRY" ] || pc_take cpu-window.sh "profile training: boot to a Grand Prix race (2 min)" 5
  run "tr-$N-menus" boot-menus "$([ -n "$DRY" ] && echo machine-n.toml || echo machine-train.toml)" 7000 )
[ -n "$DRY" ] && { echo "  cd $P && $(wslpath -u "$TOOL_LLVM_WIN")/bin/llvm-profdata.exe merge -o a.profdata *.profraw"; exit 0; }
ls "$P"/*.profraw > /dev/null 2>&1 || { echo "profile: the runs wrote no profile into $P" >&2; exit 1; }
python3 - "$W/port/runs/tr-$N-menus/probe.csv" <<'PY'
import sys
lines = sum(1 for _ in open(sys.argv[1]))
print(f"profile: the training run reached {lines - 1} fields" + ("" if lines > 6000 else ": TOO FEW, the race was not reached"))
sys.exit(0 if lines > 6000 else 1)
PY
step "merge"
( cd "$P" && "$(wslpath -u "$TOOL_LLVM_WIN")/bin/llvm-profdata.exe" merge -o a.profdata $(ls *.profraw) )
echo "profile: $P/a.profdata ($(sha1sum "$P/a.profdata" | cut -c1-8), $(stat -c %s "$P/a.profdata") bytes) from $(ls "$P"/*.profraw | wc -l) raw file(s)"
