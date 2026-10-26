# gates-table.sh (sourced by gates.sh, which holds the rows): the gate table's own machinery. A row's result and
# figures (put), its inputs, one command of a row with its log (step), the judge's verdict (judge, settle), the time
# a row is given and takes (head_row, times), the table, and the way out (finish). Everything here reads and writes
# gates.sh's own variables: the batch's tag and folders, DRY and JUDGE, and the rows' tables (RES, FIG, ...).

# Where the pass stands, for whoever watches the PC (scripts/progress.py keeps the progress file a window shows;
# the release-build handbook): the rows that take time are its steps, by a name in plain words and the seconds the
# handbook gives each. Rows run side by side, so the pass is timed as a whole: 28 minutes at first, then as its
# earlier passes went; a pass of some rows (ONLY) is a kind of its own. A dry run and a judge-only run say nothing.
declare -A PNAME=([checks]="Build and unit tests" [batch]="Native against the JIT, two scenes" [match]="Match race against the JIT"
  [roundtrip]="Match race played back" [offline]="Offline: boot, menus, a race" [fork]="Fork replay" [forced]="Forced rollbacks"
  [control]="Control playback" [crash]="Crash recording, 30 players" [pair]="Two-game race" [desync]="Desync on purpose"
  [quickplay]="Quick Play, two races" [thirty]="Thirty players, five laps" [mixed]="Two builds in one race")
declare -A PSEC=([checks]=300 [batch]=210 [match]=90 [roundtrip]=60 [offline]=120 [fork]=60 [forced]=180 [control]=120 [crash]=60
  [pair]=180 [desync]=120 [quickplay]=420 [thirty]=300 [mixed]=360)
progress_begin() { :; }; progress_step() { :; }; progress_done() { :; }; progress_bad() { :; }; progress_end() { :; }
progress_rows() {
  [ -z "$DRY$JUDGE" ] && [ -f "$root/scripts/progress.sh" ] || return 0
  source "$root/scripts/progress.sh"
  local id rows=() whole=0 kind=gates
  for id in "${ORDER[@]}"; do
    [ -n "${PSEC[$id]:-}" ] && want "$id" || continue
    [ "$id" != mixed ] || [ -n "${MIXED:-}" ] || continue   # manual without a second build: no step of the pass
    rows+=(--step "$id|${PNAME[$id]}|${PSEC[$id]}|$([ "$id" = checks ] && echo native || echo games)"); whole=$((whole + PSEC[$id]))
  done
  [ -n "${ONLY:-}" ] && kind="gates-${ONLY// /-}" || whole=1680
  progress_begin "$kind" "Gate table, $M" --lanes --whole "$whole" "${rows[@]}"
}

# put ROW RESULT FIGURES. A row whose first command never got the machine is "not run", whatever its later commands and
# the judge made of the folders that were never written: status 75 is the lock wait giving up after 40 minutes
# (timing-lock.sh, cpu-window.sh), 3 the busy check or the machine never free (replay-check.sh, quickplay-run.sh,
# gate-native.sh). Neither says anything about the build under test.
# A later command of the row that ran and failed is not hidden by it (RANBAD: rows whose commands each take the
# machine by themselves, roundtrip and forced): the row is a FAIL. In a judge-only run, a row the batch has no log of
# was not run (a batch made with ONLY), whatever the judge makes of folders that were never written.
put() {
  case "$2" in FAIL*|"did not finish") progress_bad "$1";; *) progress_done "$1";; esac
  [ -z "${BEGAN[$1]:-}" ] || [ -n "${TOOK[$1]:-}" ] || TOOK[$1]=$(( $(date +%s) - BEGAN[$1] ))
  if [ -n "${NOLOG[$1]:-}" ]; then RES[$1]="not run"; FIG[$1]="batch $T has no log of this row: it was not run"; return; fi
  case "${FIRST[$1]:-0}" in 75|3)
    local said; said="its first command never got the machine (status ${FIRST[$1]}): $(grep -a -B1 '^\[gates\] step 1 status ' "$OUT/$1.log" 2> /dev/null | head -1 | tr -d '\r' | cut -c1-160)"
    if [ -n "${RANBAD[$1]:-}" ]; then RES[$1]=FAIL; FIG[$1]="a later command of the row ran and failed; $said; ${3:-}"; return; fi
    RES[$1]="not run"; FIG[$1]=$said
    return;; esac
  RES[$1]=$2; FIG[$1]=${3:-}
}
# ran_bad ROW STATUS: a command after the first that ran a game and failed (replay-check.sh: 1; 3 and 75 never ran)
ran_bad() { case " roundtrip forced " in *" $1 "*) [ "$2" != 1 ] || [ "${NSTEP[$1]}" = 1 ] || RANBAD[$1]=1;; esac; }
want() { [ -z "${ONLY:-}" ] && return 0; case " $ONLY " in *" $1 "*) return 0;; esac; return 1; }
# inputs ROW [FILE WHAT]...: the row's own inputs, looked for when the row is reached. One that is not there (or a
# part that does not fit, LACKS[ROW]): the row is not started and reads "not run: needs WHAT", each of them named
# and the paths in its figures; the other rows run. A dry run says what a run would read and prints the row's
# commands; a judge-only run uses no input.
inputs() {
  local row=$1 what=${LACKS[$1]:-} where=""; shift
  [ -z "$JUDGE" ] || return 0
  while [ $# -ge 2 ]; do   # (a part two kinds of row need is named once)
    [ -e "$1" ] || case ", $what, " in *", $2, "*) ;; *) what+="${what:+, }$2"; where+="${where:+; }no $1";; esac; shift 2
  done
  [ -n "$what" ] || return 0
  if [ -n "$DRY" ]; then echo "    # as things stand a run reads: not run: needs $what${where:+ ($where)}"; return 0; fi
  echo "    not run: needs $what${where:+ ($where)}"
  put "$row" "not run: needs $what" "$where"; return 1
}
# after ROW [FILE WHAT]...: inputs that an earlier row of this batch leaves (a dry run has none to look for)
after() { [ -n "$DRY" ] || inputs "$@"; }
CHILD=""; INI=""
# step ROW COMMAND: one command line, run from the repository's root with its output added to the row's log (or, in
# a dry run, printed). In the background and waited for, so that a signal reaches this script at once.
step() {
  local row=$1 s; shift
  if [ -n "$DRY" ]; then printf '    %s\n' "${SHOW:-$*}"; return 0; fi
  NSTEP[$row]=$(( ${NSTEP[$row]:-0} + 1 ))
  if [ -n "$JUDGE" ]; then   # nothing is started: the status the batch recorded for this command
    [ -e "$OUT/$row.log" ] || { NOLOG[$row]=1; return 0; }
    s=$(grep -a "^\[gates\] step ${NSTEP[$row]} status " "$OUT/$row.log" 2> /dev/null | tail -1 | cut -d' ' -f5)
    [ -n "$s" ] || { UNKNOWN[$row]=1; s=0; }
    [ "${NSTEP[$row]}" != 1 ] || FIRST[$row]=$s
    ran_bad "$row" "$s"
    return "$s"
  fi
  echo "\$ ${SHOW:-$*}" >> "$OUT/$row.log"
  bash -c "$*" >> "$OUT/$row.log" 2>&1 < /dev/null &
  CHILD=$!; wait $CHILD; s=$?; CHILD=""
  [ "${NSTEP[$row]}" != 1 ] || FIRST[$row]=$s
  ran_bad "$row" "$s"
  echo "[gates] step ${NSTEP[$row]} status $s" >> "$OUT/$row.log"; return $s
}
# judge ROW ARGS: port/gates/gate-judge.py reads the row's run folders and log and starts nothing. Its findings go
# to <row>.judge.log, its verdict into JR (pass, FAIL, did not finish) and JF (the figures, or what failed and why).
judge() {
  local row=$1 v; shift
  if [ -n "$DRY" ]; then echo "    port/gates/gate-judge.py $*"; JR=dry-run; JF=""; return 0; fi
  echo "\$ port/gates/gate-judge.py $*" >> "$JL/$row.judge.log"
  port/gates/gate-judge.py "$@" >> "$JL/$row.judge.log" 2>&1
  v=$(grep -a '^verdict: ' "$JL/$row.judge.log" | tail -1); v=${v#verdict: }; JR=${v%% | *}; JF=${v#* | }
  [ -n "$v" ] || { JR=FAIL; JF="the judge gave no verdict: $(tail -1 "$JL/$row.judge.log" | cut -c1-200)"; }
}
# settle ROW STATUS FIGURES: the row's result from its commands' status and the judge's verdict: pass needs both
settle() {
  [ -z "$DRY" ] || return 0
  local r=$JR; [ "$2" = 0 ] || [ "$r" != pass ] || r=FAIL
  put "$1" "$r" "$3$([ "$2" = 0 ] || [ "$JR" != pass ] || echo "; a command of the row ended with status $2")"
}
head_row() {   # ROW MINUTES: the row begins; the time it is given, for the table
  STATED[$1]=$2; [ -n "$DRY$JUDGE" ] || BEGAN[$1]=$(date +%s)
  [ "$2" = 0 ] || progress_step "$1" "$OUT/$1.log"
  [ -n "$DRY" ] && echo "== $1: ${TITLE[$1]} (about $2 min)" || echo "== $(date +%T) $1: ${TITLE[$1]} (about $2 min)"
}
mmss() { printf '%d:%02d' $(($1 / 60)) $(($1 % 60)); }
last() { grep -av '^\[gates\] ' "$OUT/$1.log" 2> /dev/null | tail -n "${2:-1}" | tr -d '\r' | cut -c1-200; }
# busy_clear ROW: the busy check before a row whose script starts a game without asking it (match-run.sh,
# launcher-run.sh, pair-run.sh), stops at once when it says wait (gate-native.sh) or is a build (checks).
# Waits while it says wait
# (another agent's test game counts), 20 minutes at most; then the row is "not run".
busy_clear() {
  if [ -n "$DRY" ] && [ "$BUSY" = true ]; then echo "    # no busy check on this PC: the row goes on"; return 0; fi
  if [ -n "$DRY" ]; then echo "    $BUSY    # exit 0 (\"none\"): go on; exit 3: wait (20 minutes at most, then the row is not run)"; return 0; fi
  [ -z "$JUDGE" ] || return 0   # nothing is started
  local n=0
  until "$BUSY" > /dev/null 2>&1; do
    n=$((n + 1))
    if [ $n -gt 60 ]; then "$BUSY" >> "$OUT/$1.log" 2>&1; put "$1" "not run" "the busy check said wait for 20 minutes: $(last "$1")"; return 3; fi
    sleep 20 & CHILD=$!; wait $CHILD; CHILD=""
  done
}
manual() { head_row "$1" 0; [ -z "$DRY" ] || printf '    # manual: %s\n' "$2"; put "$1" manual "$2"; }

ours() {   # "PID NAME" of every runner and launcher that carries this batch's tag in its command line
  powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='moderngekko-run.exe' or Name='Launcher.App.exe'\" | Where-Object { \$_.CommandLine -like '*$T*' } | ForEach-Object { \"\$(\$_.ProcessId) \$(\$_.Name)\" }" < /dev/null 2> /dev/null | tr -d '\r'
}
# The times: what each row was given (head_row) and what it took, and the whole pass. A batch keeps them beside its
# logs (times.tsv), where a judge-only run reads them.
times() {
  local id line given took
  if [ -n "$JUDGE" ]; then
    while IFS= read -r line; do   # (not `read` by tabs: they are white space to it, and an empty cell would close up)
      id=${line%%$'\t'*}; line=${line#*$'\t'}; given=${line%%$'\t'*}; took=${line#*$'\t'}
      [ -z "$given" ] || STATED[$id]=$given; [ -z "$took" ] || TOOK[$id]=$took
    done < "$OUT/times.tsv" 2> /dev/null
    return 0
  fi
  [ -n "$DRY" ] || { TOOK[all]=$(( $(date +%s) - T0 ))
    for id in "${ORDER[@]}" all; do printf '%s\t%s\t%s\n' "$id" "${STATED[$id]:-}" "${TOOK[$id]:-}"; done > "$OUT/times.tsv"; }
}
table() {
  local id pass=0 fail=0 cut=0 man=0 not=0 took
  times
  echo; echo "gates $T: module $M ${MSHA:-}, runner ${RSHA:-}, image ${ISHA:-}, launcher $L, repository $(git rev-parse --short HEAD)$(git diff --quiet HEAD 2> /dev/null || echo +changes), $(date '+%F %T')"
  echo; echo "| Gate | Result | Figures | Given | Took |"; echo "|---|---|---|---|---|"
  for id in "${ORDER[@]}"; do
    took=""; [ -z "${TOOK[$id]:-}" ] || took="$(mmss "${TOOK[$id]}")${ROWS[$id]:+ (${ROWS[$id]})}"
    echo "| $id: ${TITLE[$id]} | ${RES[$id]} | ${FIG[$id]//|//}${UNKNOWN[$id]:+ (judge only: the log of this batch records no exit statuses; they count as 0)} | ${STATED[$id]:+${STATED[$id]} min} | $took |"
    case "${RES[$id]}" in pass*) pass=$((pass + 1));; manual) man=$((man + 1));;
      "not run"*|dry-run) not=$((not + 1));; "did not finish") cut=$((cut + 1));; *) fail=$((fail + 1));; esac
  done
  echo; echo "$pass pass, $fail FAIL, $cut did not finish, $man manual, $not not run: $([ $((fail + cut + not)) = 0 ] && echo "COMPLETE" || echo "NOT COMPLETE")"
  [ -z "${TOOK[all]:-}" ] || echo "the whole pass took $(mmss "${TOOK[all]}") (a release pass is to take 30 minutes at most; rows that ran side by side each say the time of their set)"
  [ $((fail + cut + not)) = 0 ]
}
finish() {
  trap - EXIT INT TERM
  if [ -n "$JUDGE" ]; then
    echo; echo "judge only: nothing was started; batch $T was read, the judges' logs are in $JL"
    table | tee "$JL/table.md"; exit "${PIPESTATUS[0]}"
  fi
  if [ -z "$DRY" ]; then
    # the step in flight, by its process ID: its own exit trap stops its test server and bots and releases its lock
    [ -z "$CHILD" ] || { kill "$CHILD" 2> /dev/null; sleep 3; }
    [ -z "${LANE:-}" ] || { kill "$LANE" 2> /dev/null; wait "$LANE" 2> /dev/null; }   # row checks, when it runs beside
    while read -r p name; do
      [ -n "$p" ] || continue
      taskkill.exe /PID "$p" /F < /dev/null > /dev/null 2>&1 || true
      echo "gates: ended $name $p (still running at the end)"
    done <<< "$(ours)"
    # the gate scenes' configuration back as gate-native.sh leaves it, also when a batch stopped half way
    [ -z "$INI" ] || cp "$W/scratch/Dolphin.ini.single" "$W/user/Config/Dolphin.ini"
    table | tee "$OUT/table.md"; id=${PIPESTATUS[0]}; progress_end "$id" "$OUT/table.md"; exit "$id"
  fi
  echo "    # on every way out: kill <the step's process ID>; then, for each line of"
  echo "    #   Get-CimInstance Win32_Process (moderngekko-run.exe, Launcher.App.exe) whose command line holds '$T':"
  echo "    #   taskkill.exe /PID <its ID> /F"
  table | sed 's/NOT COMPLETE/dry run: nothing was started or written/'; exit 0
}

