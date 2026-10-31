#!/bin/bash
# gates.sh MODULE [--launcher NAME] [--bundle DIR] [--game DIR] [--dry-run | --judge-only]: every gate of the native
# form (the port handbook, "What must hold"), in order, and one table at the end: gate, result, figures. It wraps the
# scripts each gate already has (gate-native.sh, match-run.sh, launcher-run.sh, replay-check.sh, pair-run.sh,
# quickplay-run.sh, mixed-run.sh, each part's check) and reads their outputs; it adds no gate of its own. Whether a
# game ran and ended as it should (no crash line, not frozen, its own end line, whole recordings, playbacks that
# finished) is gate-judge.py's to say, from the run's folders: a row passes only when its commands and that judge
# both do. A gate no script can judge yet is a row with result "manual" and the reason.
#   MODULE        the module under test: <work>/work/mod-cg-MODULE (n7)
#   --launcher NAME  the staged copy to gate: the launcher folder <work>/port/NAME that stage-launcher.sh made
#                 (default launcher-dev; LAUNCHER=NAME says the same, as launcher-run.sh takes it). Its runner is the
#                 runner under test in every row: the rows the harness starts (the gate scenes, the playbacks) get
#                 machine files of this batch's own, the port's two with that runner in their `runner` line. This
#                 script stages nothing: a row through the launcher is not run when the folder does not hold the
#                 parts under test, and says how to stage it.
#   MACHINE=FILE  for a runner that is in no launcher folder: the harness's machine file that names it (its `runner`
#                 line), as replay-check.sh takes it. The playbacks get FILE as it is, the gate scenes the port's
#                 gate machine file with that runner; the rows through the launcher run only when the launcher
#                 folder holds the same runner.
#   --bundle DIR  the native bundle MODULE was built from (default: the launcher folder's own, recomp/fzgx)
#   --game DIR    the game folder of that bundle's image (default: the one the launcher folder links, recomp/game).
#                 Both are handed to the scripts that take them (BUNDLE, GAME: gate-native.sh, replay-check.sh).
#   --dry-run     prints every command, starts nothing, writes nothing; says which rows a run would leave out
#   --judge-only  starts nothing: the verdicts again from the logs and run folders an earlier batch left (TAG names
#                 it), which are only read. The judges' logs and the table go to JUDGE_OUT (default: a new temporary
#                 folder). A command's exit status is the one that batch recorded in its log; a log from before
#                 statuses were recorded counts them as 0, and the row says so.
#   TAG           names every run of the batch (default g<MODULE>-<hour><minute><second>): <work>/port/runs/TAG-*
#   ONLY="a b"    only these rows (ids as in the table); the others read "not run" and the exit status is not 0
#   REF           the JIT reference's match race to compare with (default nmj: <work>/port/runs/nmj and its match file)
#   IGNORE_REQUESTS  as this PC's timing-lock.sh takes it (PC_SCRIPTS, port/setup/lib.sh)
#   AT_ONCE=N     how many playbacks run side by side (default 3; 1: one after the other, as before 2026-10-11)
#   MIXED=NAME    row mixed: another build's staged launcher folder (<work>/port/NAME), whose game races the one under
#                 test, then the roles swapped; MIXED_THIRTY=1: and two games of each among 26 simulated players
# A row needs only its own inputs (the parts under test, its recordings, an earlier row's run): one whose input is
# not there is not started and reads "not run: needs X", with the path in its figures, and the other rows run.
# Results: pass | pass, noise: <set> (<n> words) | FAIL | did not finish | manual | not run[: needs X]. "did not
# finish": a playback cut by its time limit (a busy PC), which says nothing either way. "not run" also when a row's
# first command gave up waiting for the machine (its status 75 or 3). Exit status 0 only when no row failed,
# every row ran and every playback finished. Logs: <work>/port/scratch/gates/TAG/<row>.log (each command, its output
# and "[gates] step N status S"), <row>.judge.log (the judge's findings), the table again in table.md there.
# About 30 minutes in all on a PC that is otherwise quiet (85 until 2026-10-11): the full check runs beside the
# playbacks of kept recordings (rows fork, forced, control), and playbacks run three side by side (replay-check.sh
# AT_ONCE; a playback's verdict is its recorded checksums, so a game beside it cannot change it, and one that did
# not finish beside the others is played again alone). No scene is shortened and no row is left out. The table says
# for each row the time it was given and the time it took, and the whole pass's time.
# Every game is muted and closes by itself; two rows hold games longer than three minutes
# (quickplay: 14 at most, thirty: 10 at most). On every way out the step in flight is ended by its process ID and
# then every runner and launcher whose command line carries TAG, each by its process ID.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd); . "$here/runner.sh" || exit 2; cd "$root"   # root: the runner (pins.tsv REPO_RUNNER)
W=${PORT_WORK:-$PORT_WORK_DEFAULT}   # the work folder and the disc: the build's settings
K=$HARNESS_DIR/recomp.py
pc_busy_check "$W"   # BUSY: the busy check (`true` on a PC without it)
M=""; DRY=""; JUDGE=""; L=${LAUNCHER:-launcher-dev}; BN=""; GN=""
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) DRY=1;; --judge-only) JUDGE=1;; --launcher) L=${2%/}; shift;; --bundle) BN=${2%/}; shift;; --game) GN=${2%/}; shift;;
  --runner) echo "gates: --runner has gone: name the staged copy (--launcher NAME, or MACHINE=FILE for a runner in no launcher folder)" >&2; exit 2;;
  -*) echo "gates: unknown option $1" >&2; exit 2;; *) M=$1;; esac; shift; done
[ -n "$M" ] || { sed -n 2,53p "$0"; exit 2; }
L=${L#"$W/port/"}   # the folder's name, as launcher-run.sh takes it
case "$L" in ""|*/*) echo "gates: --launcher names a folder of $W/port (launcher-dev)" >&2; exit 2;; esac
[ -z "${MACHINE:-}" ] || [ -f "$MACHINE" ] || { echo "gates: no machine file $MACHINE" >&2; exit 2; }
T=${TAG:-g$M-$(date +%H%M%S)}; REF=${REF:-nmj}
AT=${AT_ONCE:-3}; case "$AT" in ''|*[!0-9]*|0) echo "gates: AT_ONCE is a count of playbacks side by side (3)" >&2; exit 2;; esac
AT2=$AT; [ "$AT" -le 2 ] || AT2=2   # for a row's pair of playbacks
unset AT_ONCE                       # each row's command says its own
[ ${#T} -ge 5 ] || { echo "gates: TAG must have five characters or more (processes are found by it)" >&2; exit 2; }
OUT=$W/port/scratch/gates/$T; RUNS=$W/port/runs; RT=$W/port/replays-test
JL=$OUT   # the judges' logs: beside the rows' logs; in a judge-only run a folder of their own (the batch is only read)
if [ -n "$JUDGE" ]; then
  [ -n "${TAG:-}" ] && [ -d "$OUT" ] || { echo "gates: --judge-only needs TAG=<a batch that ran>: no folder $OUT" >&2; exit 2; }
  JL=${JUDGE_OUT:-$(mktemp -d)}; mkdir -p "$JL"
fi
# ---- the staged copy: the parts under test, and the machine files that hand its runner to the harness
LD=$W/port/$L; MD=$W/work/mod-cg-$M/gGFZE01_recomp.dll
[ -n "$BN" ] || BN=$LD/recomp/fzgx
[ -n "$GN" ] || { GN=$(readlink -f "$LD/recomp/game" 2> /dev/null); GN=${GN:-$LD/recomp/game}; }
GIVEN=${MACHINE:-}; PM_FROM=${GIVEN:-$W/port/machine-n.toml}; GM_FROM=$W/port/machine-gate-n.toml   # the playbacks', the gate scenes'
if [ -n "$GIVEN" ]; then
  R=$(sed -n 's/^runner *= *"\(.*\)" *$/\1/p' "$MACHINE" | head -1); R=$W/${R:-ModernGekko/build/moderngekko-run.exe}; PM=$MACHINE
else R=$LD/recomp/moderngekko-run.exe; PM=$OUT/machine.toml; fi
GM=$OUT/machine-gate.toml
# machine FROM TO: the harness's machine file FROM with the runner under test as its `runner` (a file without the
# line runs the harness's default runner, so the line is written, not replaced; a machine file has no tables)
RLINE="runner = \"${R#"$W"/}\""
machine() { [ ! -f "$1" ] || { grep -v '^runner *=' "$1"; echo "$RLINE"; } > "$2"; }
HENV="export RECOMP_AGENT=port RECOMP_MANIFEST=$root/recomp/manifest.toml RECOMP_MACHINE=$GM"
# replay-check.sh plays back on this module with this bundle, game folder and machine file (its own defaults are
# n6's and the harness's runner), also at the end of pair-run.sh and quickplay-run.sh; gate-native.sh takes the bundle
# and is given the gate scenes' machine file; the launcher's rows take the folder's name
export BUILD=$M BUNDLE=$BN GAME=$GN LAUNCHER=$L MACHINE=$PM
RATE='CLOCKRATE=$(python3 port/gates/runs/clock-rate.py)'   # measured at each use: the WSL clock is not always slow

ORDER=(checks batch match start roundtrip roundtrip-jit offline pieces fork forced control crash pair desync
       quickplay thirty mixed failures service movie timing)
declare -A TITLE RES FIG NSTEP UNKNOWN FIRST NOLOG RANBAD LACKS STATED BEGAN TOOK ROWS
TITLE=(
  [checks]="Linux build and unit tests (each part's own check, port/setup/app.sh APP_CHECKS)"
  [batch]="standard batch: native form in mode 0 against the JIT, both scenes, dual and single core"
  [match]="match race against the JIT reference $REF, racer hashes per race frame"
  [start]="the match race's start: long fields at the gate, catch-up"
  [roundtrip]="the match race's recording played back as the race"
  [roundtrip-jit]="the same recording under the JIT with the fork's image"
  [offline]="offline through $L: boot, menus, a Grand Prix race"
  [pieces]="pieces of the game failing their check (match race, offline)"
  [fork]="a fork replay played back as the race"
  [forced]="six playbacks with forced rollbacks, 1 to 17 steps"
  [control]="the playback gate can fail: the locked cache left out by the switch"
  [crash]="the 30-player crash's reproduction: a recording as the race, rollbacks forced, its screen copies; the undo log's guard checked at every step"
  [pair]="two games, lags 30 and 90 ms, game 1's seat on a pad script, game 2's never across the line: the race ends 10 s after the first finish; both recordings played back"
  [desync]="a difference made on purpose is found by the relay; nobody is disconnected, nothing repaired"
  [quickplay]="Quick Play, local server: two launchers, a watcher, two races"
  [thirty]="three games and 27 simulated players, five laps, to the finish"
  [mixed]="two builds in one race, then the roles swapped: $L against ${MIXED:-another build (MIXED=NAME)}; lags 30 and 90 ms, rollbacks forced 6 and 12 deep, a seat on the wall, the finish"
  [failures]="Quick Play failure cases (no server, another module, no go, a game closed)"
  [service]="Quick Play on the real online service"
  [movie]="the story's movie at full speed, no step on the fallback"
  [timing]="timing against the JIT"
)
for id in "${ORDER[@]}"; do RES[$id]="not run"; FIG[$id]=""; done
[ -z "$DRY" ] || for id in "${ORDER[@]}"; do RES[$id]=dry-run; done
# The table's own machinery (put, inputs, step, judge, settle, head_row, the times, the table, the way out):
source "$here/gates-table.sh"

# ---- before anything starts: what each kind of row needs of the parts under test. Nothing here stops the batch:
# a row whose input is not there says so in the table (inputs), and the others run.
sha8() { [ ! -f "$1" ] || sha1sum "$1" | cut -c1-8; }
RSHA=$(sha8 "$R"); MSHA=$(sha8 "$MD"); ISHA=$(sha8 "$BN/mod.bin")
BUSY_IN=(); [ "$BUSY" = true ] || BUSY_IN=("$BUSY" "the busy check (port/setup/install.sh)")
PARTS=("$R" "the runner under test" "$MD" "module $M (port/build/build-module.sh $M)"
       "$BN/patches.json" "the native bundle (--bundle DIR)")
HARNESS=("${BUSY_IN[@]}" "${PARTS[@]}" "$K" "the harness (port/gates/vendor/harness, or RECOMP_KIT)")
SCENES=("$GM_FROM" "the gate scenes' machine file (port/setup/install.sh)"
        "$W/derived/race300.sav" "the saved state race300 (port/gates/runs/state.sh)" "$W/derived/racego.sav" "the saved state racego")
PLAYBACK=("${HARNESS[@]}" "$GN/sys/main.dol" "the game folder (--game DIR)"
          "$PM_FROM" "the playbacks' machine file (port/setup/install.sh)")
STAGED=("${BUSY_IN[@]}" "$LD/Launcher.App.exe" "the staged launcher $L (port/build/stage-launcher.sh)" "${PARTS[@]}"
        "$GN/sys/main.dol" "the game folder (--game DIR)" "$W/kit-win/launch.ps1" "the harness's Windows scripts (port/setup/install.sh)"
        "$W/port/user-pristine/GC" "a save file for boots (FIRST_BOOT=1 port/build/build.sh NAME)")
# the game folders are made from the user's own disc (port/setup/setup.sh): without it every game row reads "not run"
[ -f "$DISC_DEFAULT" ] || echo "gates: note: $(disc_lacks "$DISC_DEFAULT"); the game folders are made from your own disc (port/setup/setup.sh WORK DISC, then port/build/build.sh NAME)"
source "$root/port/setup/app.sh"
BUILT="the test server and the simulated players, built ($APP_BUILD; row checks does)"
SERVER=("$APP_SERVER" "$BUILT" "$APP_BOTS" "$BUILT")
if [ -z "$JUDGE" ]; then
  # a module and a bundle of two images: the game stops at its first frames (stage-launcher.sh refuses them too)
  image() { python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['image_sha1'])" "$1" 2> /dev/null; }
  unfit=""; mi=$(image "$W/work/cg-$M/manifest.json"); bi=$(image "$BN/manifest.json")
  [ -z "$mi" ] || [ -z "$bi" ] || [ "$mi" = "$bi" ] || unfit="the bundle module $M was built from (image ${mi:0:8}; $BN holds ${bi:0:8})"
  # the rows through the launcher test what its folder holds: it must be the parts the other rows test
  hold=""
  if [ -e "$LD/Launcher.App.exe" ]; then
    [ ! -e "$R" ] || cmp -s "$R" "$LD/recomp/moderngekko-run.exe" || hold+=", the runner under test"
    [ ! -e "$MD" ] || cmp -s "$MD" "$LD/recomp/gGFZE01_recomp.dll" || hold+=", module $M"
    [ ! -e "$BN/mod.bin" ] || cmp -s "$BN/mod.bin" "$LD/recomp/fzgx/mod.bin" || hold+=", the image of $BN"
    [ ! -e "$GN" ] || [ "$(readlink -f "$LD/recomp/game")" = "$(readlink -f "$GN")" ] || hold+=", the game folder $GN"
    [ -z "$hold" ] || hold="launcher folder $L holding ${hold#, } (in a CPU window: RUNNER=$R MODULE=cg-$M BUNDLE=<the bundle's folder> GAME=<the game folder> port/build/stage-launcher.sh $LD)"
  fi
  for id in batch roundtrip fork forced control crash match offline pair desync quickplay thirty; do LACKS[$id]=$unfit; done
  for id in match offline pair desync quickplay thirty; do LACKS[$id]+=${hold:+${LACKS[$id]:+, }$hold}; done
fi
# the machine files of this batch: the port's two, with the runner under test
[ -n "$DRY$JUDGE" ] || { mkdir -p "$OUT"; [ -n "$GIVEN" ] || machine "$PM_FROM" "$PM"; machine "$GM_FROM" "$GM"; }
trap finish EXIT; trap 'exit 130' INT TERM
echo "gates $T: module $M ${MSHA:-}, runner ${RSHA:-} ($R), image ${ISHA:-} ($BN), game folder $GN, launcher $L; logs $OUT"
echo "gates $T: every game muted; rows quickplay and thirty hold games longer than three minutes (14 and 10 at most)"
T0=$(date +%s); progress_rows
if [ -n "$DRY" ]; then
  echo "    cd $root"
  [ -n "$GIVEN" ] || echo "    { grep -v '^runner *=' $PM_FROM; echo '$RLINE'; } > $PM    # the playbacks' machine file"
  echo "    { grep -v '^runner *=' $GM_FROM; echo '$RLINE'; } > $GM    # the gate scenes' machine file"
  echo "    export BUILD=$M BUNDLE=$BN GAME=$GN LAUNCHER=$L MACHINE=$PM"
fi

# ---- the rows
# Row checks, the full check, runs beside the playbacks of kept recordings (rows fork, forced, control): their
# verdicts are recorded checksums, and a part of the check that fails is not judged by speed, so neither changes
# the other's verdict; they share the processors and nothing else.
# When these very files passed the full check at their landing (scripts/premerge.sh keeps the record, by tree) and
# nothing is changed since, the suites are not run a second time: the row builds what the live rows need of it, the
# test server and the simulated players, and says in its figures that it did so.
LANDED=""
if [ -z "$DRY$JUDGE" ] && [ -z "$(git status --porcelain 2> /dev/null)" ]; then
  LANDED=$(grep -m1 "^$(git rev-parse 'HEAD^{tree}') " "$(cd "$(git rev-parse --git-common-dir)" && pwd)/premerge-passed" 2> /dev/null)
fi
WAS_LANDED='^gates: the full check passed at the landing of these files'
checks_done() {   # STATUS: the row's result from its log, once its command has ended
  local s=$1 r
  [ ! -e "$OUT/checks.ended" ] || [ -z "${BEGAN[checks]:-}" ] || TOOK[checks]=$(( $(cat "$OUT/checks.ended") - BEGAN[checks] ))
  if grep -aq "$WAS_LANDED" "$OUT/checks.log" 2> /dev/null; then
    [ "$s" = 0 ] && r=pass || r=FAIL
    put checks $r "$(grep -a -m1 "$WAS_LANDED" "$OUT/checks.log" | sed 's/^gates: //'); built here: the test server and the simulated players ($APP_BUILD)$([ "$s" = 0 ] || echo "; the build ended with status $s: $(last checks)")"
  else
    [ "$s" = 0 ] && [ "$(last checks)" = "check: ok" ] && r=pass || r=FAIL
    put checks $r "core: $(grep -A1 'port core tests' "$OUT/checks.log" | tail -1 | cut -c1-80); net: $(grep -c 'Test run summary' "$OUT/checks.log") test runs, $(awk '$1 == "failed:" { n += $2 } END { print n + 0 }' "$OUT/checks.log") failing tests"
  fi
}
LANE=""
if want checks && { head_row checks 5; inputs checks "${BUSY_IN[@]}" && busy_clear checks; }; then
  cw() { ! pc_has cpu-window.sh || printf 'source %q "%s" %s; ' "$PC_SCRIPTS/cpu-window.sh" "$1" "$2"; }   # this PC's CPU window, where it is (PC_SCRIPTS)
  if [ -n "$LANDED" ]; then
    read -r tree day commit <<< "$LANDED"
    cmd="( PORT_AGENT=port-checks; $(cw "port: the test server and the simulated players" 3)echo 'gates: the full check passed at the landing of these files (tree ${tree:0:8}, recorded $day as commit $commit): not run again'; $APP_BUILD --disable-build-servers -nodeReuse:false -v quiet -nologo )"
  else cmd="( PORT_AGENT=port-checks; $(cw "port: each part's checks" 8)$APP_CHECKS )"
  fi
  if [ -n "$DRY$JUDGE" ]; then
    [ -z "$DRY" ] || echo "    # (when these files passed the full check at their landing and nothing is changed: only $APP_BUILD, and the row says so)"
    step checks "$cmd"; s=$?; [ -n "$DRY" ] || checks_done $s
  else   # beside the rows that follow, until they are done
    ( trap 'kill "$CHILD" 2> /dev/null' TERM; step checks "$cmd"; date +%s > "$OUT/checks.ended" ) & LANE=$!
  fi
fi

KEPT="(port/setup/kept.tsv)"
# replayed ROW: in a judge-only run, the commands of a row of playbacks as its batch recorded them (one for the row's
# share of a set; one for each playback in a batch from before 2026-10-11). Status 1 when one of them was not 0.
replayed() {
  local n j s=0
  n=$(grep -ac '^\[gates\] step [0-9]* status ' "$OUT/$1.log" 2> /dev/null); [ "${n:-0}" -ge 1 ] || n=1
  for ((j = 0; j < n; j++)); do step "$1" "" || s=1; done
  return $s
}
# The playbacks of kept recordings, rows fork, forced and control: one call of replay-check.sh, three playbacks side
# by side (AT_ONCE=3), the longest first so that a set's playbacks are of a length, each under the run name its row
# has always given it (NAMES) and by its own launch file (CONFIGS). Then each row gets its own log, with the lines of
# its playbacks, and its judge reads it as ever. A row's status is from its own lines: one playback that differed, 1;
# none that differed and one that did not finish, 4; a row whose playbacks never got the machine, the call's status.
PB_NAMES=(); PB_CONFIGS=(); PB_FILES=(); PB_ROWS=(); KEPT_ROWS=""
playback() { PB_ROWS+=("$1"); PB_NAMES+=("$T-$2"); PB_CONFIGS+=("$3"); PB_FILES+=("$4"); }   # ROW RUN CONFIG FILE
HR=$RT/20261004-155342-m32-hr.fzrp
if want control && { head_row control 2
    inputs control "${PLAYBACK[@]}" "$RUNS/qs0-1/replays/20261006-101707-m22.fzrp" "the recording of run qs0 $KEPT"; }; then
  KEPT_ROWS+=" control"; playback control ctl-1 control "$RUNS/qs0-1/replays/20261006-101707-m22.fzrp"
fi
FORCED=""
if want forced && { head_row forced 3; inputs forced "${PLAYBACK[@]}" "$HR" "the fork recording 20261004-155342-m32-hr.fzrp $KEPT" \
    "$RT/20261004-014343-m32-P1.fzrp" "the fork recording 20261004-014343-m32-P1.fzrp $KEPT" "$RUNS/rm1/race.fzrp" "the recording of run rm1 $KEPT"; }; then
  KEPT_ROWS+=" forced"; FORCED=1
  playback forced f5-1 forced-race-2x3-9-17 "$RUNS/rm1/race.fzrp"
  playback forced f4-1 forced-1x6 "$HR"
  playback forced f2-1 forced-3x1-2-4-8-12-17 "$HR"
  playback forced f3-1 forced-7x17 "$HR"
  playback forced f1-1 forced-1x1 "$HR"
fi
if want fork && { head_row fork 1; inputs fork "${PLAYBACK[@]}" "$HR" "the fork recording 20261004-155342-m32-hr.fzrp $KEPT"; }; then
  KEPT_ROWS+=" fork"; playback fork fork-1 playback "$HR"
fi
[ -z "$FORCED" ] || playback forced f6-1 forced-4x2-5-11 "$RT/20261004-014343-m32-P1.fzrp"
declare -A KS
if [ -n "$KEPT_ROWS" ]; then
  if [ -n "$JUDGE" ]; then for row in $KEPT_ROWS; do replayed "$row"; KS[$row]=$?; done
  else
    step kept "AT_ONCE=$AT NAMES=\"${PB_NAMES[*]}\" CONFIGS=\"${PB_CONFIGS[*]}\" port/gates/replay-check.sh $T-kept ${PB_FILES[*]}"; ks=$?
    for row in $KEPT_ROWS; do
      [ -z "$DRY" ] || continue
      want_lines=0; lines=""
      for i in "${!PB_NAMES[@]}"; do
        [ "${PB_ROWS[$i]}" = "$row" ] || continue
        want_lines=$((want_lines + 1)); lines+=$(grep -a "^${PB_NAMES[$i]}: " "$OUT/kept.log")$'\n'
      done
      rs=0
      if [ "$(grep -acE ': (PASS|FAIL|DID NOT FINISH)$' <<< "$lines")" -lt $want_lines ] && [ $ks != 0 ]; then rs=$ks   # it never got the machine
      elif grep -aq ': FAIL$' <<< "$lines"; then rs=1
      elif grep -aq ': DID NOT FINISH$' <<< "$lines"; then rs=4; fi
      { echo "\$ rows$KEPT_ROWS, $AT playbacks side by side; this row's lines of: $(grep -a -m1 '^\$ ' "$OUT/kept.log" | cut -c3-)"
        printf '%s' "$lines" | grep -a . || true
        echo "[gates] step 1 status $rs"; } >> "$OUT/$row.log"
      NSTEP[$row]=1; FIRST[$row]=$rs; KS[$row]=$rs; ROWS[$row]="with${KEPT_ROWS/ $row/}"
    done
  fi
fi
case " $KEPT_ROWS " in *" fork "*)
  judge fork playbacks --log "$OUT/fork.log" --expect 1
  settle fork "${KS[fork]:-0}" "$JF (as the race)";; esac
case " $KEPT_ROWS " in *" forced "*)
  judge forced playbacks --log "$OUT/forced.log" --expect 6
  settle forced "${KS[forced]:-0}" "$JF; audit lines: grep -a 're-simulation audit' $RUNS/$T-f*-1/stderr.txt";; esac
case " $KEPT_ROWS " in *" control "*)
  # the judge passes this row only on a playback that finished, FAILed and differed at more than 1 step
  judge control playbacks --log "$OUT/control.log" --expect 1 --control
  [ -n "$DRY" ] || put control "$JR" "$JF (the control must FAIL with more than the recording's own 1 step differing; x16fh: 44)";; esac
# row checks has ended, or is waited for here
if [ -n "$LANE" ]; then
  wait "$LANE"; LANE=""
  s=$(grep -a '^\[gates\] step 1 status ' "$OUT/checks.log" 2> /dev/null | tail -1 | cut -d' ' -f5)
  NSTEP[checks]=1; FIRST[checks]=${s:-1}; checks_done "${s:-1}"
fi

G=$W/port/scratch/rp/gbatch-$T.gates.txt
if want batch && { head_row batch 3.5; inputs batch "${HARNESS[@]}" "${SCENES[@]}" && busy_clear batch; }; then INI=1
  step batch "MACHINE=$GM port/gates/gate-native.sh $T $M"; s=$?
  if [ -z "$DRY" ]; then
    lines=$(grep -c . "$G" 2> /dev/null); ok=$(grep -c '^  PASS' "$G" 2> /dev/null); exact=$(grep -v 'NOT EXACT' "$G" 2> /dev/null | grep -c 'EXACT by 2')
    bad=$(grep -c 'NOT EXACT\|FAIL' "$G" 2> /dev/null); noise=$(grep -o 'pass, noise: .*' "$G" 2> /dev/null | sort -u | sed 's/^pass, noise: //' | paste -sd, | sed 's/,/, /g')
    if [ $s = 0 ] && [ "${exact:-0}" = 6 ] && [ "${ok:-0}" = 30 ] && [ "${bad:-1}" = 0 ]; then r=pass; [ -z "$noise" ] || r="pass, noise: $noise"; else r=FAIL; fi
    judge batch runs "$T-dual-core-*" "$T-single-core-*"; [ "$JR" = pass ] || r=FAIL
    put batch "$r" "${exact:-0} of 6 pairs EXACT by both gates, ${ok:-0} of 30 PASS lines, ${bad:-?} failing, ${lines:-0} lines; lines passing by a named noise set: $(grep -c 'pass, noise:' "$G" 2> /dev/null)$([ $s = 0 ] || echo "; stopped with status $s: $(last batch)"); $JF"
  else judge batch runs "$T-dual-core-*" "$T-single-core-*"
  fi
fi

# the dumps are game data and large: gone once the row that reads them has passed, kept for a second reading otherwise
if want batch; then
  if [ -n "$DRY" ]; then echo "    rm -f $RUNS/$T-*/*.ram    # only when batch passed"
  elif [ -z "$JUDGE" ] && [[ "${RES[batch]}" == pass* ]]; then rm -f "$RUNS/$T"-*/*.ram; fi
fi

if want match && { head_row match 1.5; inputs match "${STAGED[@]}" "${SERVER[@]}" \
    "$RUNS/$REF/probe.csv" "the JIT reference's run $REF (LAUNCHER=launcher-ref port/gates/runs/match-run.sh $REF ref)" \
    "$W/port/scratch/match/$REF.json" "the JIT reference's match file" && busy_clear match; }; then
  step match "$RATE FROM=$REF port/gates/runs/match-run.sh $T-match"; s=$?
  step match "port/gates/reports/run-summary.py $REF $T-match" || s=1
  judge match game "$T-match" --end results --log "$OUT/match.log" --must probe pace
  settle match $s "$(grep 'racers_hash by step' "$OUT/match.log" 2> /dev/null | tail -1 | sed 's/ *racers_hash by step: //; s/;.*//'); $(grep -o 'fallback=[0-9]*' "$OUT/match.log" 2> /dev/null | tail -1); $JF"
fi

if want start && { head_row start 0; after start "$RUNS/$T-match/pace.csv" "row match's pacing log in this batch"; }; then
  step start "port/gates/reports/pace-start.py $RUNS/$T-match/pace.csv"
  [ -n "$DRY" ] || put start manual "no limit is written down: read against the JIT's ($REF: 85 ms, 17 fields). Fields over 50 ms in the race mode before race frame 400: $(grep -c '^  field .*mode 2/' "$OUT/start.log"), the longest $(grep '^  field .*mode 2/' "$OUT/start.log" | grep -o '): *[0-9.]* ms' | grep -o '[0-9.]*' | sort -n | tail -1) ms (n6: 79 ms); $(grep 'catch-up:' "$OUT/start.log" | sed 's/^ *//; s/, from.*//')"
fi

# judged ROW: in a judge-only run, a row whose commands may all be left out (roundtrip without a recording, pieces)
# ran in the batch only if the batch holds its judge's log; without one it was not run.
judged() { [ -z "$JUDGE" ] || [ -e "$OUT/$1.log" ] || [ -e "$OUT/$1.judge.log" ] || NOLOG[$1]=1; }
if want roundtrip && { head_row roundtrip 1; judged roundtrip
    after roundtrip "$RUNS/$T-match/race.fzrp" "row match's recording in this batch" && inputs roundtrip "${PLAYBACK[@]}"; }; then
  # (judge only: a batch from before a row could read "not run: needs" ran this one with no recording and no command)
  s=0; [ -z "$JUDGE" ] || [ -f "$RUNS/$T-match/race.fzrp" ] || s=2
  # as the race, under the name it has had since the game's replay mode played it too (-rtr-1)
  if [ $s = 2 ]; then :
  elif [ -n "$JUDGE" ]; then replayed roundtrip || s=1
  else step roundtrip "NAMES=\"$T-rtr-1\" CONFIG=playback port/gates/replay-check.sh $T-rt $RUNS/$T-match/race.fzrp" || s=1
  fi
  judge roundtrip playbacks --log "$OUT/roundtrip.log" --expect 1
  settle roundtrip $s "$JF (as the race)$([ $s != 2 ] || echo "; no recording: row match did not leave one")"
fi
want roundtrip-jit && manual roundtrip-jit "replay-check.sh plays on the native module only; the JIT playback of 5.12 was port\\scratch\\rt.sh (work folder, not in the repository)"

# The picture is asked for at field 5200 and the race's pace is measured over its fields before that one (the race
# starts at field 4613: 587 fields): the screenshot can stall the game a quarter of a second, and the row measured
# that and the emulator's catch-up after it while the picture was asked for at field 4710, inside the measured span.
if want offline && { head_row offline 2; inputs offline "${STAGED[@]}" && busy_clear offline; }; then
  step offline "SHOTS=5200 port/gates/runs/launcher-run.sh $T-offline"; s=$?
  step offline "port/gates/reports/run-summary.py --race-before 5200 $T-offline" || s=1
  if [ -z "$DRY" ]; then
    race=$(grep ' race: ' "$OUT/offline.log" | tail -1); n=$(echo "$race" | sed -n 's/.* race: \([0-9]*\) fields.*/\1/p'); mean=$(echo "$race" | sed -n 's/.*mean \([0-9.]*\) ms.*/\1/p')
    [ "${n:-0}" -ge 500 ] && python3 -c "import sys; sys.exit(0 if 16.6 <= float('${mean:-0}') <= 16.8 else 1)" || s=1
    judge offline game "$T-offline" --end stop --log "$OUT/offline.log" --must probe
    settle offline $s "$JF; $(grep -o 'modes (first field).*' "$OUT/offline.log" | tail -1 | grep -o ' [12]@[0-9]*' | paste -sd' ' | sed 's/^ *//') (n6: 1@1218 2@2502);$(echo "$race" | sed 's/.* race://'); picture $W/shots/port-$T-offline-f5200.png not looked at by this script"
  else judge offline game "$T-offline" --end stop --log "$OUT/offline.log" --must probe
  fi
fi

if want pieces && { head_row pieces 0
    after pieces "$RUNS/$T-match" "row match's run in this batch" "$RUNS/$T-offline" "row offline's run in this batch"; }; then
  # like with like: the runner's own count of pieces failing at shutdown (n6: 1 and 17), not the count of log lines
  judged pieces
  judge pieces pieces "$T-match" "$T-offline"
  [ -n "$DRY" ] || put pieces "$JR" "$JF; n6: match 1, offline 17 at shutdown, each a menu module at the movie player's address"
fi

# The crash of 2026-10-06 (the port-recomp notes 5.18), reproduced without a network: game 1's recording of the
# 30-player race w4b, played as the race with a 5-step rollback forced every 12 frames. On runner 7dac514f (a rollback
# put the game's display records back): 48 copies of 640x448 into the six portrait buffers, then the crash line and a
# game that stands. The recording is game data, kept in the work folder only: a copy of <work>/port/runs/w4b-1/race.fzrp.
# Without it the row is not run (inputs). Another recording serves only once it has shown the fault on that runner
# (<work>/port/scratch/rollback-gx-record/moderngekko-run-7dac514f.exe).
CRASH_REC=$RT/20261006-w4b-1.fzrp
if want crash && { head_row crash 1
    inputs crash "${PLAYBACK[@]}" "$CRASH_REC" "the recording of the crash (game data; a copy of port/runs/w4b-1/race.fzrp of 2026-10-06)"; }; then
  step crash "CONFIG=crash SET='debug.paceLog={run}\\pace.csv' port/gates/replay-check.sh $T-crash $CRASH_REC"; s=$?
  judge crash playbacks --log "$OUT/crash.log" --expect 1 --copies "$T-crash-1" --undo-check "$T-crash-1"
  settle crash $s "$JF (runner 7dac514f: 48 copies of 640x448 into the portraits, then the crash)"
fi

pad() {   # the pad script of port\scratch\x16\pair.sh, unchanged: period, amplitude
  python3 - "$1" "$2" <<'PY'
import sys
period, amp = int(sys.argv[1]), int(sys.argv[2])
x = 0
events = {}
for f in range(1500, 8900, period):
    x += 1
    events[f] = ("0100", 128 + (amp if x % 2 else -amp) * (1 if x % 5 else 0))
for f in range(1560, 8900, 120):
    stick = max((k for k in events if k <= f), default=None)
    sx = events[stick][1] if stick is not None else 128
    events[f] = ("0000", sx); events[f + 4] = ("0100", sx)
print(",".join(["0:0"] + [f"{f}:{b}:{sx}:128" for f, (b, sx) in sorted(events.items())]))
PY
}
# Game 2's pad in row pair: nothing until the results are up, then A every second (the first press leaves the list).
# Its machine stands on the grid, so the host's rule ends the race with it short of the line: the row's race-end proof
# (the server's rule at 10 s: the results come about 60 s after the go on Loop Cross, field 5,400 or so).
still() { python3 -c 'print(",".join(["0:0"] + [f"{f}:0100,{f + 6}:0" for f in range(5700, 8900, 60)]))'; }
both="$RUNS/$T-pair-1/race.fzrp $RUNS/$T-pair-2/race.fzrp"
if want pair && { head_row pair 3; inputs pair "${STAGED[@]}" "${SERVER[@]}" "${PLAYBACK[@]}" && busy_clear pair; }; then
  pre="$RATE COURSE=8 LAPS=1 LAG=30 LAG2=90 AUTO=0 FINISH_LIMIT=10 CHECK_LATE=2 AT_ONCE=$AT2"   # (AT_ONCE: each pair of playbacks side by side)
  SHOW="$pre INPUT1=<pad script: stick every 30 fields, 14 off centre> INPUT2=<nothing, then A from field 5,700> port/gates/runs/pair-run.sh $T-pair" \
    step pair "$pre INPUT1=$(pad 30 14) INPUT2=$(still) port/gates/runs/pair-run.sh $T-pair"; s=$?
  step pair "port/gates/replay-compare.py $both" || s=1
  step pair "port/gates/reports/pair-report.py $T-pair"
  judge pair pair "$T-pair" --log "$OUT/pair.log" --playbacks 4 --short 2
  settle pair $s "$JF (straight and inputs 2 steps late); rollbacks, depths: $(grep "^| $T-pair " "$OUT/pair.log" 2> /dev/null | tail -1 | cut -d'|' -f6-7 | sed 's/|/; /g')"
fi

if want desync && { head_row desync 2; inputs desync "${STAGED[@]}" "${SERVER[@]}" && busy_clear desync; }; then
  step desync "$RATE LAG=100 ALTER2=1500 CHECK=0 port/gates/runs/pair-run.sh $T-alter"
  # the comparison's status is not the row's: these two recordings must differ (the judge says from which step)
  step desync "port/gates/replay-compare.py $RUNS/$T-alter-1/race.fzrp $RUNS/$T-alter-2/race.fzrp"
  # the test server runs at its default (the relay observes, as the live relays do): the difference must be in its
  # log, nobody disconnected, both games on to their own finish, the recordings different from the altered step on
  judge desync desync "$T-alter" --altered 1500 --log "$OUT/desync.log"
  [ -n "$DRY" ] || put desync "$JR" "$JF (state altered before step 1,500; the relay compares every 60th)"
fi

pairs() {   # pairs RUN N: launcher 1's replays against the same matches' of launchers 2..N
  echo "for f in $RUNS/$1-1/replays/*.fzrp; do for i in \$(seq 2 $2); do g=\$(ls $RUNS/$1-\$i/replays/*-\${f##*-} | head -1); port/gates/replay-compare.py \$f \$g || exit 1; done; done"
}
if want quickplay && { head_row quickplay 7; inputs quickplay "${STAGED[@]}" "${SERVER[@]}" "${PLAYBACK[@]}"; }; then
  step quickplay "AT_ONCE=$AT WATCHER=1 BOTCOUNT=4 LAG=50 RACES=2 MINUTES=14 port/gates/runs/quickplay-run.sh $T-qp"; s=$?
  step quickplay "$(pairs $T-qp 2)" || s=1
  step quickplay "port/gates/reports/quickplay-report.py $T-qp"
  judge quickplay quickplay "$T-qp" --launchers 2 --races 2 --log "$OUT/quickplay.log"
  settle quickplay $s "$JF; the report: $OUT/quickplay.log"
fi

if want thirty && { head_row thirty 5; inputs thirty "${STAGED[@]}" "${SERVER[@]}" "${PLAYBACK[@]}"; }; then
  step thirty "AT_ONCE=$AT LAUNCHERS=3 BOTCOUNT=27 LAPS=5 FIXED=1 RACES=1 MINUTES=10 port/gates/runs/quickplay-run.sh $T-q30"; s=$?
  step thirty "$(pairs $T-q30 3)" || s=1
  step thirty "port/gates/reports/quickplay-report.py $T-q30"
  judge thirty quickplay "$T-q30" --launchers 3 --races 1 --log "$OUT/thirty.log"
  settle thirty $s "$JF; the report: $OUT/thirty.log"
fi

# Row mixed, for a build that is to race in the lobbies of one already out: its game and the other build's (MIXED: that
# one's staged launcher folder) in one race, every step's checksum compared, then the roles swapped; the judge holds
# both races to their conditions. Manual without MIXED, and no part of a release pass until the orchestrator says so.
if want mixed && [ -z "${MIXED:-}" ] && { [ -z "$JUDGE" ] || [ ! -e "$OUT/mixed.log" ]; }; then
  manual mixed "it needs a second build, staged: MIXED=<its launcher folder> ONLY=mixed port/gates/gates.sh $M --launcher $L (two races of three minutes; by hand: port/gates/runs/mixed-run.sh RUN <folder> $L, then gate-judge.py mixed RUN)"
elif want mixed && { head_row mixed $((${MIXED_THIRTY:+3 +} 6)); inputs mixed "${STAGED[@]}" "${SERVER[@]}" "$W/port/${MIXED:-}/Launcher.App.exe" "the other build's staged launcher (MIXED=NAME)" && busy_clear mixed; }; then
  step mixed "port/gates/runs/mixed-run.sh $T-mixa ${MIXED:-} $L"; s=$?
  step mixed "port/gates/runs/mixed-run.sh $T-mixb $L ${MIXED:-}" || s=1
  [ -z "${MIXED_THIRTY:-}" ] || step mixed "BOTCOUNT=26 port/gates/runs/mixed-run.sh $T-mix30 ${MIXED:-} $L ${MIXED:-} $L" || s=1
  judge mixed mixed "$T-mixa" "$T-mixb" ${MIXED_THIRTY:+"$T-mix30"} --log "$OUT/mixed.log"; settle mixed $s "$JF"
fi
want failures && manual failures "four runs (5.15 item 2) whose result is a message in the door's lines, read by hand: quickplay-run.sh with a dead SERVER, SETTINGS2, DOOR1='\"startLimitSeconds\":60', CLOSE1_AFTER=20"
want service && manual service "it starts a relay on the test service: only when the brief says so. SERVER=wss://piconet-test-coordinator.fly.dev/ws BOTCOUNT=4 RACES=1 MINUTES=12 port/gates/runs/quickplay-run.sh RUN"
want movie && manual movie "no script reads the movie's fields (run pcn2 was read by hand): CARD_FROM=user-story-pristine port/gates/runs/launcher-run.sh RUN story-mission1"
want timing && manual timing "the module against the JIT, on a quiet PC and by the limits of the speed handbook: MACHINE=$GM port/gates/time-native.sh TAG $M (it refuses when the PC is not quiet)"

exit 0
