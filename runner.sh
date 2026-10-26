# runner.sh (sourced by the gates' entry scripts: gates.sh, replay-check.sh, gate-native.sh, time-native.sh): root,
# the runner's checkout these gates test, from this folder's pins.tsv REPO_RUNNER (relative to this folder), and the
# runner's port/setup/lib.sh sourced from there (the work folder, the disc, the harness, the PC's locks). The runner
# names this checkout too (its pins.tsv REPO_GATES); the two must agree, for every gate script below reaches the
# runner's files by ../.. from here. Status 1 and one line when they do not.
_gates=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
_runner_pin=$(awk -F'\t' '$1 == "REPO_RUNNER" { print $2; f = 1 } END { exit !f }' "$_gates/pins.tsv") \
  || { echo "gates: $_gates/pins.tsv has no row REPO_RUNNER" >&2; return 1; }
root=$(cd "$_gates/$_runner_pin" 2> /dev/null && pwd) && [ -f "$root/port/setup/lib.sh" ] \
  || { echo "gates: no runner checkout at $_gates/$_runner_pin (pins.tsv REPO_RUNNER): check these gates out at the runner's port/setup/pins.tsv REPO_GATES" >&2; return 1; }
. "$root/port/setup/lib.sh"
[ "$GATES_DIR" -ef "$_gates" ] \
  || { echo "gates: the runner at $root names its gates at $GATES_DIR (its pins.tsv REPO_GATES), not $_gates: check these gates out there" >&2; return 1; }
unset _gates _runner_pin
