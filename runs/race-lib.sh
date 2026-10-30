# race-lib.sh (sourced by pair-run.sh, mixed-run.sh and quickplay-run.sh, after port/setup/lib.sh and app.sh): a
# test race's test server and simulated players, and a launcher's game, made and ended one way. The caller sets B
# (its scratch folder) and R (the run's name) first; every process is found and ended by the ID written for it,
# never by a text in a command line of someone else's.
#   race_server SECONDS ARG...   the test server (APP_SERVER, built by APP_BUILD) with these arguments, detached and
#                                ended by itself after SECONDS; its log $B/$R.server.log, its ID $B/server.pid. Then
#                                waits until it is up (server-up.sh): status 1 when it never was, the server stopped
#   race_bots LOG SECONDS ARG... the simulated players (APP_BOTS) the same way: their log LOG, their ID $B/bots.pid
#   stop_ours                    the server and the simulated players this run started, by the IDs it wrote
#   game_of LAUNCHER             the process ID of the game that launcher (a Windows process ID) started: its one
#                                child of the runner's name; nothing when there is none
#   end_launcher LAUNCHER        that launcher's game, then the launcher, ended by their IDs
_race_runs=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
race_server() {
  local seconds=$1; shift
  setsid timeout "$seconds" dotnet "$APP_SERVER" $TEST_PORTS "$@" > "$B/$R.server.log" 2>&1 < /dev/null &
  echo $! > "$B/server.pid"
  "$_race_runs/server-up.sh" 127.0.0.1 "$B/$R.server.log" "$(cat "$B/server.pid")"
}
race_bots() {
  local log=$1 seconds=$2; shift 2
  setsid timeout "$seconds" dotnet "$APP_BOTS" "$@" > "$log" 2>&1 < /dev/null &
  echo $! > "$B/bots.pid"
}
stop_ours() {
  local f
  for f in server bots; do
    if [ -s "$B/$f.pid" ] && grep -qs "Online" "/proc/$(cat "$B/$f.pid")/cmdline"; then kill "$(cat "$B/$f.pid")" 2> /dev/null || true; fi
    rm -f "$B/$f.pid"
  done
}
game_of() {
  powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Process -Filter \"ParentProcessId=$1 and Name='moderngekko-run.exe'\").ProcessId" < /dev/null | tr -d '\r\n'
}
end_launcher() {   # (taskkill reads standard input: /dev/null, or it takes a caller's list)
  local game; game=$(game_of "$1")
  [ -z "$game" ] || taskkill.exe /PID "$game" /F < /dev/null > /dev/null 2>&1 || true
  taskkill.exe /PID "$1" /F < /dev/null > /dev/null 2>&1 || true
}
