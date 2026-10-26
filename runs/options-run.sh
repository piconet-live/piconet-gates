#!/bin/bash
# options-run.sh RUN: do a player's own controller options reach an online race, and stay on that player's computer?
# Two games race each other as in pair-run.sh. Game 1 starts from the pristine save (the game's stock options); game
# 2 from a save options-save.py makes of it in <work>/port/user-options: the accelerator on B and the brake on A,
# dead zones of 2, scheme 0. Both are driven by one pad script, but game 1's presses A and game 2's presses B: with
# its options game 2 accelerates as game 1 does (without them B is the brake and it stands still), and its stick's
# small movements steer more. Both leave the results by themselves. Then options-report.py RUN reads the two recordings: what each game's own seat sent,
# that every step's inputs and checksum are the same in both, and what each game's log says of its options.
# Settings as pair-run.sh's (LAUNCHER, LAG, CLOCKRATE, CHECK, the playbacks' BUILD, BUNDLE and GAME); the same
# bounds: 170 s a game, muted. Exit status: pair-run.sh's, or 1 when the report says the options did not show.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. "$here/../../setup/work-folder.env"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}
R=${1:?options-run.sh RUN}; CARD=user-options; FILE="GC/USA/Card A/8P-GFZE-f_zero.dat.gci"
mkdir -p "$W/port/$CARD/$(dirname "$FILE")"
python3 "$here/options-save.py" "$W/port/user-pristine/$FILE" "$W/port/$CARD/$FILE"
# fields 1,500 to 4,500, the race: the button held, let go for four fields every two seconds (the accelerator's
# edge), the stick a little to the right, a little to the left and in the middle in turn, half a second each. Then A
# tapped every two seconds in both games, which leaves the results (a menu reads the buttons, not the settings).
pad() {
  python3 -c '
import sys
out = ["0:0"]
for k in range(100):
    field, x = 1500 + 30 * k, (142, 114, 128)[k % 3]
    if k % 4 == 2:
        out.append(f"{field}:0000:{x}:128"); field += 4
    out.append(f"{field}:{sys.argv[1]}:{x}:128")
for field in range(4500, 9000, 120):
    out += [f"{field}:0100", f"{field + 6}:0"]
print(",".join(out))' "$1"
}
status=0
CARD2=$CARD AUTO=0 FIELDS=${FIELDS:-7500} INPUT1="$(pad 0100)" INPUT2="$(pad 0200)" "$here/pair-run.sh" "$R" || status=$?
"$here/../reports/options-report.py" "$R" || status=1
exit $status
