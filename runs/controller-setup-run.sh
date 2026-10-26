#!/bin/bash
# controller-setup-run.sh RUN change|leave: the start that opens the game's own controller options (the launcher's
# "Set up in the game": --play-controller-setup, the game's "controllerSetup"), end to end through a staged launcher.
# The game boots as offline play does, from a save with a player's own options (<work>/port/user-options, which
# options-save.py makes of the pristine save: the accelerator on B), goes to its controller menu by itself, and a
# pad script (a test may press; the feature presses nothing) does one of two visits:
#   change   Controller Rumble, port 1's rumble turned off, the game's "save?" answered yes, then B out of the menu
#   leave    B out of the menu at once
# The run passes when the game closed by itself on the core's own line (the player left the controller options),
# and the save file in the run's data folder is, for `change`: another file than the one the game started from, with
# the rumble byte changed (0x0F to 0x0E), which the game's own reader of a save takes (the core's test program,
# --save-options: its checksum, version and every option in range) with the same options as before (the accelerator
# still on B: the game saved the save it had loaded, not its defaults), and the same as the file it started from,
# byte for byte, outside the places a save of this change writes (below); for `leave`: the same file, byte for byte.
# The places, of the file's 32,832 bytes (a 64-byte directory entry, then the save): the setting, 1 byte; the save's
# checksum, 2; and what every save by the game stamps, whatever was changed, 46: the entry's time of the last change
# (0x28, 4) and first block (0x36, 2: the game writes a new file and deletes the old one, which the emulator keeps
# as .deleted), the date in the save's comment (its second line: the save's 0x24, 32), and the card's serial number
# in four words of the save (0x2060, 0x2066, 0x2200, 0x7580: the emulator writes them at every load from its card's
# header, which it makes from the clock, and an offline start runs on the PC's clock). Read from a save the game
# made in a visit by hand on 2026-10-10: it differed from the file it had loaded in these places and no other.
# Bounded: launcher-run.sh's 170 s (the game closes after some 30 s, or 20), muted, the test's name in the window's
# title. Leaves <work>/port/runs/RUN (its last line: PASS or FAIL and why) and screenshots of the menu.
#   LAUNCHER=NAME   the staged launcher (default launcher-dev: its runner must know "controllerSetup")
# The fields: the controller menu stands at field 549 (runs ctlb3, ctlb4), or by 870 when the title has begun
# loading its demonstration race before the request is taken (260 fields; seen with the request written later by
# hand). The pad script starts at 960.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$here/../../.." && pwd)
. "$here/../../setup/work-folder.env"; W=${PORT_WORK:-$PORT_WORK_DEFAULT}
R=${1:?controller-setup-run.sh RUN change|leave}; VISIT=${2:?controller-setup-run.sh RUN change|leave}
CARD=user-options; FILE="GC/USA/Card A/8P-GFZE-f_zero.dat.gci"; L=${LAUNCHER:-launcher-dev}; DN=$L-setup-data
mkdir -p "$W/port/$CARD/$(dirname "$FILE")"
python3 "$here/options-save.py" "$W/port/user-pristine/$FILE" "$W/port/$CARD/$FILE"
case "$VISIT" in
  # Up (the cursor goes round to Controller Rumble), A; A on port 1; Right (off); B; B (the game asks to save); A (yes);
  # the game saves and is back in the menu by itself; B
  change) INPUT="0:0,960:8,966:0,1020:100,1026:0,1100:100,1106:0,1160:2,1166:0,1220:200,1226:0,1280:200,1286:0,1340:100,1346:0,1640:200,1646:0"; SHOTS="900 1190 1310" ;;
  leave)  INPUT="0:0,960:200,966:0"; SHOTS="900" ;;
  *) echo "controller-setup-run.sh: the visit is change or leave, not $VISIT" >&2; exit 2 ;;
esac
status=0
SETUP=1 INPUT=$INPUT FIELDS=2400 SHOTS=$SHOTS CARD_FROM=$CARD DATA_NAME=$DN LAUNCHER=$L \
  TITLE="Controller-setup-test-$R--agent--closes-by-itself" "$here/launcher-run.sh" "$R" || status=$?
RUN=$W/port/runs/$R; BEFORE="$W/port/$CARD/$FILE"; AFTER="$W/port/$DN/recomp-user/$FILE"
verdict() { echo "controller setup $R ($VISIT): $*" | tee -a "$RUN/end.txt"; }
grep -aq "fzgx: controller setup: the player left the controller options; the game saved .* stopping" "$RUN/fzgx.log" 2> /dev/null \
  || { verdict "FAIL: the game did not close on the core's own line (launcher-run.sh: status $status; $(tail -1 "$RUN/end.txt" 2> /dev/null))"; exit 1; }
[ $status = 0 ] || { verdict "FAIL: launcher-run.sh ended with status $status"; exit 1; }
said=$(grep -a "fzgx: controller setup: the player left" "$RUN/fzgx.log" | tail -1 | tr -d '\r' | sed 's/.*fzgx: //')
if [ "$VISIT" = leave ]; then
  cmp -s "$BEFORE" "$AFTER" || { verdict "FAIL: the save file changed in a visit that changed nothing"; exit 1; }
  verdict "PASS: the game closed by itself ($said); the save file is the same, byte for byte"; exit 0
fi
# the game's own reader, from the core's test program (built here once a run: its own tests run too)
B=$W/port/scratch/controller-setup/core; mkdir -p "$B" "$B.cards"
TMPDIR=${TMPDIR:-/tmp} "$repo/port/core/tests/run.sh" "$B" > "$B.log" 2>&1 || { verdict "FAIL: the core's test program did not build or pass ($B.log)"; exit 1; }
reader() { "$B/test_core" --save-options "$(dirname "$1")"; }
was=$(reader "$BEFORE") || { verdict "FAIL: the save the game started from is refused: $was"; exit 1; }
now=$(reader "$AFTER") || { verdict "FAIL: the reader refuses the save the game wrote: $now"; exit 1; }
[ "${was#*: port 1}" = "${now#*: port 1}" ] || { verdict "FAIL: the options a race reads changed: before${was#*: port 1}; after${now#*: port 1}"; exit 1; }
same=$(python3 - "$BEFORE" "$AFTER" <<'PY'
import sys
before, after = (open(p, "rb").read() for p in sys.argv[1:3])
ENTRY = 64                    # the file's directory entry; the save follows
RUMBLE = ENTRY + 0x2060 + 2   # the save's block, its third byte: a bit a port, set while the port rumbles
if before == after:
    sys.exit("the save file is the one the game started from: nothing was written")
if len(after) != len(before):
    sys.exit(f"the save file has {len(after)} bytes (it had {len(before)})")
if (before[RUMBLE], after[RUMBLE]) != (0x0F, 0x0E):
    sys.exit(f"the rumble byte is {after[RUMBLE]:#04x} (it was {before[RUMBLE]:#04x}); 0x0e is port 1 off")
# what a save of this change may write (the head of this script): the change, and what every save stamps
change = {RUMBLE, ENTRY, ENTRY + 1}
stamps = {
    "the entry's time": range(0x28, 0x2C),
    "the entry's first block": range(0x36, 0x38),
    "the comment's date": range(ENTRY + 0x24, ENTRY + 0x44),
    "the card's serial": [ENTRY + at + i for at in (0x2060, 0x2066, 0x2200, 0x7580) for i in (0, 1)],
}
differs = [i for i in range(len(before)) if before[i] != after[i]]
other = [i for i in differs if i not in change.union(*stamps.values())]
if other:
    sys.exit(f"the save file differs from the one the game started from in {len(other)} bytes that a save of this "
             "change does not write: " + ", ".join(f"{i:#06x} ({before[i]:#04x} to {after[i]:#04x})" for i in other[:16])
             + (", ..." if len(other) > 16 else ""))
stamped = [f"{name} {n}" for name, places in stamps.items() if (n := sum(i in differs for i in places))]
print(f"{len(differs)} bytes differ: the setting 1, the checksum {sum(i in differs for i in (ENTRY, ENTRY + 1))}"
      + "".join(f", {text}" for text in stamped))
PY
) || { verdict "FAIL: the save file is not the one the game started from with this change alone (above)"; exit 1; }
verdict "PASS: the game closed by itself ($said); the save file holds the change (port 1's rumble off), the game's reader takes it, the options a race reads are as before, and the file differs from the one it started from nowhere else than a save writes ($same)"
