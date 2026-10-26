#!/usr/bin/env python3
"""stat-pack.py: the made-up stat packs of stat-pack-run.sh, and what a run's files say of them.

  stat-pack.py make CARDATA.lz OUT MACHINE FACTOR NAME
      Reads the disc's own packed car data and writes two files: OUT.cardata, the car data unpacked with three
      values changed (the machine's weight times FACTOR, the same machine's first hover point's X times 1.25, and
      the first body's weight plus 100), and OUT.json, the pack of those three values as a match start carries it
      ("setup.stats": name, fingerprint, values). The launcher's import of OUT.cardata must give the same
      fingerprint: the two are worked out apart. Prints the fingerprint and the changed weight.
  stat-pack.py whole CARDATA.lz OUT MACHINE NAME
      A pack the size of a whole replacement file: every word a pack may hold of all 116 blocks (5,104 values, the
      four bytes at 0x48 among them), as the disc's but for every machine's weight (times 1.02) and the first of
      MACHINE's two bytes at 0x48 (another of the values the disc's machines hold there, 1 to 7). Writes OUT.json
      as above and OUT.fzstats, the pack as the file a server is given (--stat-pack): its numbers are written so
      that they read back to the same bits.
  stat-pack.py wire PACK.fzstats OUT
      A pack file of the protocol's (protocol/packs; port/setup/app.sh's APP_PROTOCOL) as a match start carries it: reads the text here, a third way
      beside the launcher's and the server's reader, and writes OUT.json. Prints the pack's name, how many values
      it holds and its fingerprint, which must be the one the file's head comment says (exit status 1 otherwise).
  stat-pack.py bad OUT KIND MACHINE
      A match file (as the launcher is handed one with --play-match) whose stat pack nobody may take, with the
      fingerprint of its own values, so that the one value is all that is wrong with it. KIND denormal: MACHINE's
      weight is the bits 00000001; negative: its Grip1 is -50, below minus its most (-45; a negative grip down
      to that is taken since 2026-10-24); part: the first body's Grip2 is -10.5, past the size a part's value may have. Writes OUT.json
      and prints the pack's values (the base64 text) for stat-pack-refused.sh, which hands them to the game.
  stat-pack.py weights STATES PACK.json CARDATA.lz MACHINE
      Reads a game's dump of the machines' state (pair-run.sh STATES=, the game's debug.traceStates) and holds every
      racer's weight (its block +8) against its machine's (block +6): the pack's value where the pack has one, the
      disc's elsewhere. Says how many racers hold it and how many another weight (the first of those is named):
      whether the game gives a computer racer its machine's own weight at every level is not known, so a racer
      with another weight is said and not a failure. Exit status 1 when no racer on MACHINE holds the pack's
      weight for it, the pack has none for it, or the file holds no state.

No value of the disc is printed or kept but the weights the packs change. Standard library only."""
import base64
import hashlib
import json
import os
import struct
import sys
import tomllib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))
import mainrel   # noqa: E402  (unpack: how the disc's .lz files are packed)
import parts     # noqa: E402  (the protocol's checkout)

BLOCK, MACHINES, PARTS_AT, BYTES_AT = 0xB4, 41, 0x1F04, 0x48   # port/facts/game.tsv: CAR_BLOCK, CAR_MACHINES, ...
RACER, PROGRESS = 0x620, 0x1FC                                 # MACHINE_SIZE, PROGRESS_SIZE
BLOCKS, PARTS_OF_A_KIND = 116, 25
# a pack file's names of a block's words (handbook/stat-packs.md: the table of ranges; the test holds
# these against it); from 0x54 on, eight points of three words: Hover0X .. Hover3Z, Wall0X .. Wall3Z
NAMES = {0x04: "Weight", 0x08: "Acceleration", 0x0C: "MaxSpeed", 0x10: "Grip1", 0x14: "Grip3", 0x18: "TurnTension",
         0x1C: "DriftAcceleration", 0x20: "TurnMovement", 0x24: "StrafeTurn", 0x28: "Strafe", 0x2C: "TurnReaction",
         0x30: "Grip2", 0x34: "BoostStrength", 0x38: "BoostDuration", 0x3C: "TurnDeceleration", 0x40: "Drag",
         0x44: "Body", BYTES_AT: "Bytes48", 0x4C: "CameraReorienting", 0x50: "CameraRepositioning"}
POINTS_AT, WALL_AT = 0x54, 0x84


CONSTANT_BLOCK = 240   # a pack's game constants, by slot (the protocol's protocol/stats.toml)


def _constants():
    """Name -> (first slot, 64 bits): the one list (the protocol's protocol/stats.toml, in slot order: a 64-bit
    constant takes two slots), which the game's const_ranges.h is generated from."""
    with open(parts.path_in("REPO_PROTOCOL", "protocol/stats.toml"), "rb") as f:
        rows = tomllib.load(f)["constant"]
    out, slot = {}, 0
    for row in rows:
        out[row["name"]] = (slot, row["bits"] == 64)
        slot += 2 if row["bits"] == 64 else 1
    return out


CONSTANTS = _constants()
assert CONSTANTS["SpeedCap"] == (1, True) and CONSTANTS["DashPlateScale"] == (4, False) and CONSTANTS["AccelGain"][1]


def block_at(block):
    return block * BLOCK if block < MACHINES else PARTS_AT + (block - MACHINES) * BLOCK


def word(data, block, at):
    """A word of the car data file as a pack holds it: the file is low byte first, the four bytes at 0x48 as they are."""
    return struct.unpack_from(">I" if at == BYTES_AT else "<I", data, block_at(block) + at)[0]


def bits(value):
    return struct.unpack(">I", struct.pack(">f", value))[0]


def number(pattern):
    return struct.unpack(">f", struct.pack(">I", pattern))[0]


def wire(name, entries):
    """The pack as a match start carries it; entries: {(block, offset): 32 bits}."""
    values = b"".join(struct.pack(">BBI", block, at, entries[block, at]) for block, at in sorted(entries))
    return {"name": name, "fingerprint": hashlib.sha1(b"\x01" + values).hexdigest(), "values": base64.b64encode(values).decode()}


def entries_of(pack):
    values = base64.b64decode(pack["values"])
    return {(values[i], values[i + 1]): struct.unpack_from(">I", values, i + 2)[0] for i in range(0, len(values), 6)}


def make(car_data, machine, factor, name):
    """(the changed car data, the pack) of the disc's unpacked car data."""
    changes = {(machine, 0x04): bits(number(word(car_data, machine, 0x04)) * factor),
               (machine, 0x54): bits(number(word(car_data, machine, 0x54)) * 1.25),
               (MACHINES, 0x04): bits(number(word(car_data, MACHINES, 0x04)) + 100.0)}
    changed = bytearray(car_data)
    for (block, at), pattern in changes.items():
        struct.pack_into("<I", changed, block_at(block) + at, pattern)
    return bytes(changed), wire(name, changes)


def word_name(at):
    """A word of a block as a pack file names it."""
    if at < POINTS_AT:
        return NAMES[at]
    kind, first = ("Hover", POINTS_AT) if at < WALL_AT else ("Wall", WALL_AT)
    return f"{kind}{(at - first) // 12}{'XYZ'[(at - first) // 4 % 3]}"


def block_name(block):
    if block < MACHINES:
        return f"machine {block}"
    return f"{('body', 'cockpit', 'booster')[(block - MACHINES) // PARTS_OF_A_KIND]} {(block - MACHINES) % PARTS_OF_A_KIND}"


def file_text(name, entries):
    """The pack as a pack file (NAME.fzstats). A number is the 32-bit value's own decimal text, which reads back to
    the same bits; the two bytes at 0x48 are two whole numbers."""
    lines = ["fzstats 1", f"name {name}"]
    for (block, at), pattern in sorted(entries.items()):
        value = f"{pattern >> 24} {pattern >> 16 & 0xFF}" if at == BYTES_AT else repr(number(pattern))
        lines.append(f"{block_name(block)} {word_name(at)} {value}")
    return "\n".join(lines) + "\n"


def whole(car_data, machine, name):
    """(the pack, its entries): every word of every block, the weights and one byte changed."""
    entries = {(block, at): word(car_data, block, at) for block in range(BLOCKS) for at in range(4, BLOCK, 4)}
    for block in range(MACHINES):
        entries[block, 0x04] = bits(number(entries[block, 0x04]) * 1.02)
    first = entries[machine, BYTES_AT] >> 24
    entries[machine, BYTES_AT] = (entries[machine, BYTES_AT] & 0x00FFFFFF) | (first % 7 + 1) << 24
    return wire(name, entries), entries


# (the block, None: the player's machine; the offset; the bits): a machine's weight a denormal; a machine's Grip1
# -50 (its floor is -45); the first body's Grip2 -10.5 (a part's value is at most 10 from 0 there)
BAD = {"denormal": (None, 0x04, 0x00000001), "negative": (None, 0x10, 0xC2480000), "part": (MACHINES, 0x30, 0xC1280000)}


def read_file(text):
    """(name, author or None, entries) of a pack file's text: the lines a pack file has, and nothing checked but
    their shape (the programs check the values)."""
    lines = [line.strip() for line in text.split("\n") if line.strip() and not line.strip().startswith("#")]
    if len(lines) < 3 or lines[0] != "fzstats 1" or not lines[1].startswith("name "):
        raise ValueError("no pack file: it begins with fzstats 1 and the name")
    author = lines[2][7:] if lines[2].startswith("author ") else None
    offsets = {word_name(at): at for at in range(4, BLOCK, 4)}
    kinds = {"machine": 0, "body": MACHINES, "cockpit": MACHINES + PARTS_OF_A_KIND, "booster": MACHINES + 2 * PARTS_OF_A_KIND}
    entries = {}
    for line in lines[3 if author else 2:]:
        if line.startswith("constant "):
            # a game constant (handbook/stat-pack-constants.md): block 240, its slot; a 64-bit number two slots
            _, name, value = line.split()
            slot, double = CONSTANTS[name]
            if (CONSTANT_BLOCK, slot) in entries:
                raise ValueError(f"not a constant's line: {line}")
            if double:
                both = struct.unpack(">Q", struct.pack(">d", float(value)))[0]
                entries[CONSTANT_BLOCK, slot], entries[CONSTANT_BLOCK, slot + 1] = both >> 32, both & 0xFFFFFFFF
            else:
                entries[CONSTANT_BLOCK, slot] = bits(float(value))
            continue
        kind, number, stat, *value = line.split()
        key = kinds[kind] + int(number), offsets[stat]
        if key in entries or key[0] >= BLOCKS or (kind != "machine" and int(number) >= PARTS_OF_A_KIND) or len(value) != (2 if stat == "Bytes48" else 1):
            raise ValueError(f"not a value's line: {line}")
        entries[key] = int(value[0]) << 24 | int(value[1]) << 16 if stat == "Bytes48" else bits(float(value[0]))
    return lines[1][5:], author, entries


def bad_match(kind, machine):
    """A match file with a pack of one value that is refused: one player's race, a relay that is nobody's."""
    block, at, pattern = BAD[kind]
    pack = wire("Refused " + kind, {(machine if block is None else block, at): pattern})
    setup = {"course": 16, "laps": 1, "shuffleSeed": 4660, "cpuSeed": 305419896, "stats": pack,
             "seats": [{"seat": 0, "machine": machine, "playerId": "p1", "name": "PACK"}, {"seat": 1, "machine": 12, "cpu": True, "name": "CPU"}]}
    match = {"matchId": "refused", "seat": 0, "token": "1f2e3d4c5b6a7988", "relay": {"host": "127.0.0.1", "port": 47811}, "setup": setup}
    return {"match": match, "relayHost": "127.0.0.1", "delay": 2, "overclock": 6.0, "otherSounds": "quieter"}


def weights(states, pack, car_data, machine):
    """(lines, ok): every racer of every dumped state against the pack and the disc."""
    entries, seen, at = entries_of(pack), 0, 0
    racers = hold = drivers = 0
    first = ""
    while at + 16 <= len(states):
        mark, step, _, size = struct.unpack_from(">IIII", states, at)
        if mark != 0x465A5354 or size % (RACER + PROGRESS) != 0 or at + 16 + size > len(states):
            return [f"the state dump is broken at byte {at}"], False
        for racer in range(size // (RACER + PROGRESS)):
            ident, held = struct.unpack_from(">hI", states, at + 16 + racer * (RACER + PROGRESS) + 6)
            if not 0 <= ident < MACHINES:
                continue
            expected = entries.get((ident, 0x04), word(car_data, ident, 0x04))
            racers += 1
            hold += held == expected
            drivers += ident == machine and held == expected
            if held != expected and not first:
                first = f" (the first: step {step}, racer {racer} on machine {ident} holds {held:08X}, not {expected:08X})"
        seen += 1
        at += 16 + size
    if seen == 0:
        return ["the file holds no state"], False
    said = f"{seen} states: {hold} of {racers} racers hold their machines' weights, {racers - hold} another{first}; "
    changed = entries.get((machine, 0x04))
    if changed is None:
        # a pack that leaves the machine's weight as the disc has it (F-Zero GX+'s Super Piranha): a racer on it holds
        # the disc's
        disc = number(word(car_data, machine, 0x04))
        if drivers == 0:
            return [said + f"no racer on machine {machine} holds its weight, the disc's {disc:g} (the pack leaves it)"], False
        return [said + f"the pack leaves machine {machine}'s weight as the disc's, {disc:g}, and its racers hold it"], True
    if drivers == 0:
        return [said + f"no racer on machine {machine} holds the pack's weight for it, {number(changed):g}"], False
    return [said + f"machine {machine}'s is the pack's, {number(changed):g} (the disc's {number(word(car_data, machine, 0x04)):g})"], True


def read(path, text=False):
    with open(path, encoding="utf-8") if text else open(path, "rb") as f:
        return f.read()


def run_make(packed, out, machine, factor, name):
    car_data = mainrel.unpack(read(packed))
    changed, pack = make(car_data, int(machine), float(factor), name)
    with open(out + ".cardata", "wb") as f:
        f.write(changed)
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump(pack, f)
    print(f"stat pack {pack['name']}: fingerprint {pack['fingerprint']}; machine {machine}'s weight "
          f"{number(word(car_data, int(machine), 4)):g} becomes {number(word(changed, int(machine), 4)):g}")
    return 0


def run_whole(packed, out, machine, name):
    pack, entries = whole(mainrel.unpack(read(packed)), int(machine), name)
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump(pack, f)
    with open(out + ".fzstats", "w", encoding="utf-8", newline="\n") as f:
        f.write(file_text(name, entries))
    print(f"stat pack {name}: fingerprint {pack['fingerprint']}; {len(entries)} values, every machine's weight times 1.02")
    return 0


def run_wire(pack_file, out):
    text = read(pack_file, text=True)
    name, author, entries = read_file(text)
    pack = wire(name, entries)
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump(pack, f)
    said = pack["fingerprint"] in "".join(line for line in text.split("\n") if line.startswith("#"))
    print(f"stat pack {name}{' by ' + author if author else ''}: {len(entries)} values, fingerprint {pack['fingerprint']}"
          + ("" if said else ": NOT the fingerprint the file's head says"))
    return 0 if said else 1


def run_bad(out, kind, machine):
    if kind not in BAD:
        return __doc__
    match = bad_match(kind, int(machine))
    with open(out + ".json", "w", encoding="utf-8") as f:
        json.dump(match, f)
    print(match["match"]["setup"]["stats"]["values"])
    return 0


def run_weights(states, pack, packed, machine):
    lines, ok = weights(read(states), json.loads(read(pack, text=True)), mainrel.unpack(read(packed)), int(machine))
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    command, arguments = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ("", [])
    if (command, len(arguments)) == ("make", 5):
        sys.exit(run_make(*arguments))
    if (command, len(arguments)) == ("whole", 4):
        sys.exit(run_whole(*arguments))
    if (command, len(arguments)) == ("wire", 2):
        sys.exit(run_wire(*arguments))
    if (command, len(arguments)) == ("bad", 3):
        sys.exit(run_bad(*arguments))
    if (command, len(arguments)) == ("weights", 4):
        sys.exit(run_weights(*arguments))
    sys.exit(__doc__)
