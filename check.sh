#!/usr/bin/env bash
# The checks of the port's gates, run by the runner's port/check.sh when they are checked out at its port/gates.
# The gates' judges (gate-judge.py and its judge_*.py, replay-compare.py) on made-up logs: what counts as a game
# that ran and ended, a whole recording, a playback that finished; gates.sh and the scripts on made-up work folders.
# No game, no work folder.
set -euo pipefail
cd "$(dirname "$0")/../.."   # the runner's root: this checkout is the runner's port/gates (pins.tsv REPO_GATES)

need() { [[ -e $1 ]] || { echo "check: $1 is missing (moved? correct port/gates/check.sh)" >&2; exit 1; }; }
need port/gates/gate-judge.py
need port/gates/replay-compare.py
need port/gates/tests
echo "check: the gates' judges"
# plain unittest (the monorepo's scripts/limit.sh and unittest_limited.py, which ran four files side by side with a
# limit for each test, stayed there); the whole run has one limit
timeout 1200 python3 -W error -m unittest discover -s port/gates/tests -q
[[ ! -f port/gates/pins.tsv ]] || awk -F'\t' 'NF != 3 { print FILENAME ": line " FNR " has " NF " cells (3 expected)"; bad = 1 } END { exit bad }' port/gates/pins.tsv
