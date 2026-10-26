#!/bin/bash
# scrubber-check.sh NAME FILE [FILE...]: the replay scrubber as players get it (port/configs/scrubber.json, on unless a
# launch file says otherwise), each recording played back through replay-check.sh with a stress script of scrubs,
# jumps, pauses and frame steps (the same one for every file, made from SEED), on to the replay's end, where the
# playback stops (debug.replayEndQuits). Then, for each: replay-check's verdict (every step at the front edge and every
# step shown against the recorded checksums), the scrubber's checksum line, and its memory: the most the replay held
# beyond the game's own against its budget, and the frames it ended over the budget with nothing left that may go.
#   SEED (default 1), FRAMES (the script's
#   last frame, default 3800: about a minute of race after the go), SET="K=V .." more keys (debug.replayMemory=256)
#   BUILD, BUNDLE, GAME, MACHINE, MAXS: as replay-check.sh
# Exit status: 0 when every playback is PASS and none held more than its budget; 1 otherwise; replay-check's 3 and 4
# as they come. Output: <work>/port/runs/NAME-K, and these lines.
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../../setup/work-folder.env"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}
[ $# -ge 2 ] || { sed -n 2,13p "$0"; exit 2; }
name=$1; shift
script=$(python3 - "${SEED:-1}" "${FRAMES:-3800}" <<'PY'
import random, sys
rng = random.Random(int(sys.argv[1])); last = int(sys.argv[2])
out, f = [], 150
while f < last:
    kind = rng.choice("sssjjpvh")
    if kind == "s":   # a scrub: pressed, dragged at a few speeds both ways, released
        out.append(f"{f}:s:{rng.randrange(400, 9000)}"); g = f + 1
        for _ in range(rng.randrange(1, 4)):
            out.append(f"{g}:{rng.choice('fk')}:{rng.choice([1, 3, 7, 20, 60, 150, 400])}"); g += rng.randrange(8, 30)
        out.append(f"{g}:r"); f = g
    elif kind == "j":
        out.append(f"{f}:j:{rng.randrange(300, 9000)}")
    elif kind == "p":  # a pause of a few seconds
        out.append(f"{f}:p"); f += rng.randrange(20, 120); out.append(f"{f}:p")
    elif kind == "v":  # frame steps back, then on, paused, and play again
        out.append(f"{f}:p"); n = rng.randrange(5, 40)
        out += [f"{f + 1 + k}:v" for k in range(n)]; f += n + 2
        out += [f"{f + k}:n" for k in range(n // 2)]; f += n // 2 + 2; out.append(f"{f}:p")
    else:
        out.append(f"{f}:h")
    f += rng.randrange(20, 60)
out += [f"{last + 100 + 300 * k}:e" for k in range(4)]  # to the end (again, should the front not be there yet)
print(",".join(out))
PY
)
CONFIG=scrubber SET="debug.replayScript=$script ${SET:-}" "$here/../replay-check.sh" "$name" "$@"
status=$?
over=0; k=0
for f in "$@"; do
  k=$((k + 1)); log=$W/port/runs/$name-$k/stderr.txt
  echo "$name-$k ($(basename "$f")):"
  grep -h "scrubber: checksums:\|scrubber: frame steps:\|the process holds" "$log" 2>/dev/null | sed 's/^/  /'
  held=$(grep -o "the replay held [0-9.]* MiB at most in all (its budget [0-9]* MiB; [0-9]* frames over it" "$log" 2>/dev/null | tail -1)
  echo "  ${held:-no memory line}"
  most=; budget=; frames=
  read -r most budget frames < <(printf '%s\n' "$held" | sed -n 's/.*held \([0-9.]*\) MiB.*budget \([0-9]*\) MiB; \([0-9]*\) frames.*/\1 \2 \3/p')
  ok=1
  [ -n "${most:-}" ] && [ "${frames:-1}" = 0 ] || ok=0
  [ $ok = 0 ] || python3 -c "import sys; sys.exit(0 if float(sys.argv[1]) <= float(sys.argv[2]) else 1)" "$most" "$budget" || ok=0
  [ $ok = 1 ] || { over=1; echo "  OVER ITS BUDGET, or no memory line"; }
done
[ $status = 0 ] && [ $over = 1 ] && status=1
echo "scrubber-check $name: $([ $status = 0 ] && echo PASS || echo "FAIL (status $status)")"
exit $status
