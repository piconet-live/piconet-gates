#!/bin/bash
# server-up.sh [HOST] [LOG] [PID]: waits until the test server a script has just started is up (TCP TEST_PORT of HOST,
# default 127.0.0.1), UP_SECONDS at most (default 90); exit 1 with a line when it is not.
# Up is the server's ready line in LOG ("NAME: coordinator on TCP ... Ctrl+C stops.", which it writes once it listens)
# or an answer of its /health, whichever comes first; a server that has ended (PID gone) is not waited for.
# A server is up when it says so, not after a count of seconds: on a busy PC it listened 3.3 s after its start, and
# scripts that slept 2 s started no match (runs owner1, restg2a and restg2b, 2026-10-07); a start of about 43 s was
# seen where the wait was 30 s, and the server left running then held the relay's port 47811 for the next run.
# PID: the process ID the caller wrote for that server (its `setsid timeout ... dotnet` start). When the server is
# not up, that process and nothing else is stopped (by its ID, checked to be still a test server), and waited for
# up to 10 s, so that no leftover holds the port.
# With LOG only the ready line counts: another server already on the port answers /health too (2026-10-30: the test
# server had died on the taken port and the bots joined the owner's server).
host=${1:-127.0.0.1}; log=${2:-}; pid=${3:-}; port=${TEST_PORT:-47810}
limit=${UP_SECONDS:-90}
ready() { [ -n "$log" ] && grep -qs ': coordinator on TCP .*Ctrl+C stops\.' "$log"; }
# whether the process is still running (one that has ended but is not yet reaped by its parent is not)
alive() { kill -0 "$1" 2> /dev/null && [ "$(awk '{ print $3 }' "/proc/$1/stat" 2> /dev/null)" != Z ]; }
for _ in $(seq 1 $((limit * 2))); do
  ready && exit 0
  [ -n "$log" ] || ! curl -s -m 1 -o /dev/null "http://$host:$port/health" || exit 0
  if [ -n "$pid" ] && ! alive "$pid"; then
    echo "server-up: the test server (process $pid) ended before it was up${log:+ (see $log)}" >&2
    exit 1
  fi
  sleep 0.5
done
echo "server-up: the test server at $host:$port was not up within $limit s${log:+ (see $log)}" >&2
if [ -n "$pid" ] && grep -qs "Online.Server" "/proc/$pid/cmdline"; then
  kill "$pid" 2> /dev/null || true
  for _ in $(seq 1 20); do alive "$pid" || break; sleep 0.5; done
  ! alive "$pid" || echo "server-up: process $pid did not end within 10 s" >&2
fi
exit 1
