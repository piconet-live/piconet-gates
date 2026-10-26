#!/bin/bash
# spectator-check.sh NAME FILE [FILE...]: the camera gate of the plan-control-room notes section 2 on replays. Each
# recording is played back as the race with the scrubber (port/configs/scrubber.json) while a script works the
# spectator controls (core spectator_frame.cpp; its entries: c:KIND a camera kind's button, w:RACER a racer clicked,
# b:BUTTONS pad buttons down for one frame): every camera kind in turn (chase views 1-3, the course's TV cameras, the
# automatic shots, the four fixed shots, and back to the chase camera), other racers followed, X (the leader), Y (the
# closest battle), Z, L held (scrub back), A (live), Start twice, again and again to the replay's end. The verdict is
# replay-check's: every step at the front edge and every step shown against the recorded checksums, 0 differing.
#   FRAMES (the script's last frame, default 9000), PERIOD (frames between two actions, default 150), SET, BUILD,
#   BUNDLE, GAME, MACHINE, MAXS, AT_ONCE: as replay-check.sh
# Output: <work>/port/runs/NAME-K, a line per file with the spectator's own line from its log.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../../setup/work-folder.env"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}
[ $# -ge 2 ] || { sed -n 2,11p "$0"; exit 2; }
name=$1; shift
script=$(python3 - "${FRAMES:-9000}" "${PERIOD:-150}" <<'PY'
import sys
last, period = int(sys.argv[1]), int(sys.argv[2])
X, Y, Z, L, A, START, LEFT, RIGHT, DOWN = 0x400, 0x800, 0x10, 0x40, 0x100, 0x1000, 0x1, 0x2, 0x4
# kinds: 0-2 chase views, 3 the course's cameras, 4 automatic, 5-8 fixed; back to chase between TV kinds
cycle = [("c", 3), ("w", 1), ("c", 4), ("b", X), ("c", 5), ("w", 2), ("c", 6), ("b", Y), ("c", 7), ("b", RIGHT),
         ("c", 8), ("c", 0), ("b", LEFT), ("c", 1), ("b", Y), ("c", 2), ("b", DOWN), ("b", DOWN), ("b", DOWN),
         ("w", 0), ("b", Z), ("b", Z), ("L", 60), ("b", A), ("b", START), ("b", START), ("c", 0)]
out, f, k = [], 200, 0
while f < last:
    what, n = cycle[k % len(cycle)]
    if what == "L":    # L held: one entry a frame
        out += [f"{f + i}:b:{L}" for i in range(n)]; f += n
    elif what == "w":  # another racer each round
        out.append(f"{f}:w:{(n + k // len(cycle)) % 6}")
    else:
        out.append(f"{f}:{what}:{n}")
    f += period; k += 1
out += [f"{last + 100 + 300 * j}:e" for j in range(4)]
print(",".join(out))
PY
)
CONFIG=scrubber SET="debug.replayScript=$script ${SET:-}" "$here/../replay-check.sh" "$name" "$@"
status=$?
k=0
for f in "$@"; do
  k=$((k + 1)); log=$W/port/runs/$name-$k/stderr.txt
  echo "$name-$k ($(basename "$f")):"
  grep -h "spectator: \|scrubber: checksums:" "$log" 2>/dev/null | sed 's/^.*fzgx: /  /'
done
echo "spectator-check $name: $([ $status = 0 ] && echo PASS || echo "FAIL (status $status)")"
exit $status
