#!/bin/bash
# server-up.sh [HOST] [LOG]: waits until the test server a script has just started answers its /health (TCP 47810 of
# HOST, default 127.0.0.1), 30 s at most; exit 1 with a line when it does not (LOG: the server's log, named in it).
# A server is up when it answers, not after a count of seconds: on a busy PC it listened 3.3 s after its start, and
# scripts that slept 2 s started no match (runs owner1, restg2a and restg2b, 2026-10-07).
host=${1:-127.0.0.1}; log=${2:-}
for _ in $(seq 1 60); do curl -s -m 1 -o /dev/null "http://$host:47810/health" && exit 0; sleep 0.5; done
echo "server-up: the test server at $host:47810 did not answer within 30 s${log:+ (see $log)}" >&2
exit 1
