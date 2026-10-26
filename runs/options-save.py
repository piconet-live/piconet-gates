#!/usr/bin/env python3
"""options-save.py FROM TO: a save file with controller options a player set, for options-run.sh.

FROM is the game's own save file as the emulator keeps it (the work folder's pristine one, which holds the stock
options); TO gets the same bytes with port 1's options changed the way the game's Options screens would change them,
and the checksum the game would write (the port-traps handbook, "controller options"; the places: protocol/formats.md
section 5):
  - button settings, the standard pad's set: the accelerator on B and the brake on A (stock: A and B);
  - the stick's dead zones: 2 and 2 (stock: 8 and 8);
  - the control scheme: 0 (stock: 1).
Refuses a FROM that is not the game's save, whose checksum is wrong, or that does not hold the stock values at those
places. The file made is game data: it stays in the work folder and is never committed."""
import struct
import sys

ENTRY, SAVE, BLOCK = 0x40, 0x8000, 0x40 + 0x2060
ACCELERATOR, BRAKE, DEAD_ZONES, SCHEME = BLOCK + 0x50 + 8, BLOCK + 0x50 + 12, BLOCK + 0x48, BLOCK + 0x5556
A, B = 0x100, 0x200


def checksum(data):
    """The game's own (main.rel fn_1_1563E8): reflected CRC-16, polynomial 0x8408, from 0xFFFF, inverted."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def main(source, target):
    save = bytearray(open(source, "rb").read())
    if len(save) != ENTRY + SAVE or save[:6] != b"GFZE8P" or save[8:19] != b"f_zero.dat\0":
        sys.exit(f"options-save: {source} is not F-Zero GX's save file")
    if struct.unpack(">H", save[ENTRY:ENTRY + 2])[0] != checksum(save[ENTRY + 2:]):
        sys.exit(f"options-save: {source}: its checksum is not its bytes'")
    stock = (struct.unpack(">II", save[ACCELERATOR:ACCELERATOR + 8]), bytes(save[DEAD_ZONES:DEAD_ZONES + 2]), save[SCHEME])
    if stock != ((A, B), b"\x08\x08", 1):
        sys.exit(f"options-save: {source} does not hold the stock options (found {stock})")
    save[ACCELERATOR:ACCELERATOR + 8] = struct.pack(">II", B, A)
    save[DEAD_ZONES:DEAD_ZONES + 2] = b"\x02\x02"
    save[SCHEME] = 0
    save[ENTRY:ENTRY + 2] = struct.pack(">H", checksum(save[ENTRY + 2:]))
    with open(target, "wb") as f:
        f.write(save)
    print(f"options-save: {target}: accelerator on B, brake on A, dead zones 2, scheme 0 (port 1)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
