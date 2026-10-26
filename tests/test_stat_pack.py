"""Tests for the proving run of stat packs: stat-pack.py (the made-up packs, the racers' weights in a state dump)
and stat-pack-report.py (what the parts' files must say), on made-up car data and logs. No game, no disc."""

import contextlib
import importlib.util
import io
import json
import os
import re
import struct
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "..", path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parts = load("parts", "../setup/parts.py")   # the other parts' checkouts (port/setup/pins.tsv)
sp = load("stat_pack", "runs/stat-pack.py")
report = load("stat_pack_report", "reports/stat-pack-report.py")


def car_data():
    """Made-up car data: every word of every block a number of its own, low byte first."""
    data = bytearray(0x549A)
    for block in range(116):
        for at in range(4, 0xB4, 4):
            struct.pack_into("<f", data, sp.block_at(block) + at, 100.0 + block + at / 256)
    return bytes(data)


def states(step, racers):
    body = b""
    for machine, weight in racers:
        block = bytearray(0x620 + 0x1FC)
        struct.pack_into(">hI", block, 6, machine, weight)
        body += block
    return struct.pack(">IIII", 0x465A5354, step, 0, len(body)) + body


def result(status, out=""):
    return types.SimpleNamespace(returncode=status, stdout=out, stderr="")


class ThePacks(unittest.TestCase):
    def test_a_pack_travels_as_the_game_and_the_launcher_read_it(self):
        """The made-up pack of the game's tests (port/core/tests/stat_packs.h) and the launcher's
        (net/tests/Protocol.Tests/StatPackTests.cs): the same bytes and the same fingerprint, worked out a third time."""
        made = {(6, 0x04): sp.bits(2520.0), (6, 0x48): 0x03010000, (40, 0x5C): sp.bits(-1.5), (41, 0x04): sp.bits(500.0),
                (115, 0x34): sp.bits(14.0)}
        pack = sp.wire("p", made)
        self.assertEqual(pack["values"], "BgRFHYAABkgDAQAAKFy/wAAAKQRD+gAAczRBYAAA")
        self.assertEqual(pack["fingerprint"], "8472faeb0e46573e5c279e752ecf65c50452d8ee")
        self.assertEqual(sp.entries_of(pack), made)

    def test_the_made_up_pack_is_three_changed_words_and_no_name(self):
        disc = car_data()
        changed, pack = sp.make(disc, 6, 2, "Made up A")
        entries = sp.entries_of(pack)
        self.assertEqual(sorted(entries), [(6, 0x04), (6, 0x54), (41, 0x04)])
        self.assertEqual(sp.number(entries[6, 0x04]), 2 * sp.number(sp.word(disc, 6, 0x04)))
        self.assertEqual(sp.number(entries[41, 0x04]), sp.number(sp.word(disc, 41, 0x04)) + 100)
        differing = [at for at in range(0, len(disc), 4) if disc[at:at + 4] != changed[at:at + 4]]
        self.assertEqual(differing, [sp.block_at(6) + 4, sp.block_at(6) + 0x54, sp.block_at(41) + 4])
        self.assertNotEqual(sp.make(disc, 6, 3, "Made up B")[1]["fingerprint"], pack["fingerprint"])
        self.assertEqual((sp.block_at(40), sp.block_at(41), sp.block_at(115) + 0xB4), (40 * 0xB4, 0x1F04, 0x53C0))

    def test_the_whole_pack_is_every_word_and_reads_back_from_its_file(self):
        disc = bytearray(car_data())
        for block in range(116):   # (made-up bytes at 0x48, as the disc's machines hold them: 1 to 7, and 0 to 3)
            struct.pack_into(">I", disc, sp.block_at(block) + 0x48, (block % 7 + 1) << 24 | (block % 4) << 16)
        disc = bytes(disc)
        pack, entries = sp.whole(disc, 6, "Made up W")
        self.assertEqual(len(entries), 116 * 44)
        self.assertEqual(sp.entries_of(pack), entries)
        changed = sorted(key for key in entries if entries[key] != sp.word(disc, *key))
        self.assertEqual(changed, sorted([(block, 0x04) for block in range(41)] + [(6, 0x48)]))
        self.assertEqual(entries[6, 0x48], 1 << 24 | 2 << 16)   # the first byte 7 becomes 1, the second stays
        self.assertEqual(entries[3, 0x04], sp.bits(sp.number(sp.word(disc, 3, 0x04)) * 1.02))
        # the file: a line a value, and every number's text is the 32-bit value's own
        lines = sp.file_text("Made up W", entries).splitlines()
        self.assertEqual(lines[:2], ["fzstats 1", "name Made up W"])
        self.assertEqual(len(lines), 2 + 116 * 44)
        self.assertIn("machine 6 Bytes48 1 2", lines)
        self.assertIn("booster 24 Wall3Z " + repr(sp.number(entries[115, 0xB0])), lines)
        for line in lines[2:]:
            kind, number, name, *value = line.split()
            if name != "Bytes48":
                self.assertEqual(sp.bits(float(value[0])), entries[int(number) if kind == "machine" else
                                                                   41 + ("body", "cockpit", "booster").index(kind) * 25 + int(number), self.offset(name)])

    @staticmethod
    def offset(name):
        return next(at for at in range(4, 0xB4, 4) if sp.word_name(at) == name)

    def test_the_names_of_a_pack_files_words_are_the_handbooks(self):
        """handbook/stat-packs.md (the protocol's: its checkout, port/setup/parts.py): the table of ranges names every
        word a pack file may hold."""
        with open(parts.path_in("REPO_PROTOCOL", "handbook/stat-packs.md"), encoding="utf-8") as f:
            table = f.read().split("| At | Name in a pack |")[1].split("\n\n")[0]
        rows = dict(re.findall(r"^\| 0x([0-9A-F]{2}) \| (\S+)(?: to \S+)? \|", table, re.M))
        self.assertEqual(len(rows), 22)
        self.assertEqual({int(at, 16): name for at, name in rows.items()}, {**sp.NAMES, 0x54: "Hover0X", 0x84: "Wall0X"})
        self.assertEqual([sp.word_name(at) for at in (0x54, 0x58, 0x5C, 0x60, 0x80, 0x84, 0xB0)],
                         ["Hover0X", "Hover0Y", "Hover0Z", "Hover1X", "Hover3Z", "Wall0X", "Wall3Z"])
        self.assertEqual([sp.block_name(block) for block in (0, 40, 41, 65, 66, 90, 91, 115)],
                         ["machine 0", "machine 40", "body 0", "body 24", "cockpit 0", "cockpit 24", "booster 0", "booster 24"])

    def test_a_pack_file_is_read_here_a_third_way(self):
        """stat-pack.py wire: a pack file of the repository as a match start carries it, read by this script."""
        entries = {(6, 0x04): sp.bits(1620.0), (6, 0x48): 0x03010000, (40, 0x5C): sp.bits(-1.5), (41, 0x30): sp.bits(-0.05),
                   (66, 0x20): sp.bits(-26.0), (115, 0x34): sp.bits(18.8)}
        text = "# by A Maker, with permission\n" + sp.file_text("Made Up", entries).replace("name Made Up\n", "name Made Up\nauthor A Maker\n")
        self.assertEqual(sp.read_file(text), ("Made Up", "A Maker", entries))
        self.assertEqual(sp.read_file(sp.file_text("Made Up", entries)), ("Made Up", None, entries))
        self.assertIn("cockpit 0 TurnMovement -26.0", text)
        for wrong in ("name x\nmachine 6 Weight 9\n", "fzstats 1\nname x\nmachine 6 Weight 9\nmachine 6 Weight 9\n",
                      "fzstats 1\nname x\nbody 25 Weight 9\n", "fzstats 1\nname x\nmachine 6 Bytes48 3\n"):
            with self.assertRaises((ValueError, KeyError), msg=wrong):
                sp.read_file(wrong)
        with tempfile.TemporaryDirectory() as folder:
            pack = sp.wire("Made Up", entries)
            for head, status in ((f"# fingerprint {pack['fingerprint']}\n", 0), ("# fingerprint " + "0" * 40 + "\n", 1)):
                with open(os.path.join(folder, "p.fzstats"), "w", encoding="utf-8") as f:
                    f.write(head + sp.file_text("Made Up", entries))
                with contextlib.redirect_stdout(io.StringIO()) as said:
                    self.assertEqual(sp.run_wire(os.path.join(folder, "p.fzstats"), os.path.join(folder, "out")), status)
                self.assertIn(f"stat pack Made Up: 6 values, fingerprint {pack['fingerprint']}", said.getvalue())
                with open(os.path.join(folder, "out.json"), encoding="utf-8") as f:
                    self.assertEqual(json.load(f), pack)

    def test_a_match_file_with_a_pack_nobody_takes(self):
        part = sp.bad_match("part", 6)["match"]["setup"]["stats"]
        self.assertEqual(sp.entries_of(part), {(41, 0x30): sp.bits(-10.5)})          # a body's Grip2, past a part's size
        for kind, values in (("denormal", "BgQAAAAB"), ("negative", "BhDCSAAA")):
            match = sp.bad_match(kind, 6)
            stats = match["match"]["setup"]["stats"]
            self.assertEqual(stats["values"], values)
            self.assertEqual(stats, sp.wire("Refused " + kind, sp.entries_of(stats)))   # its own fingerprint
            self.assertEqual(match["match"]["setup"]["seats"][0]["machine"], 6)

    def test_the_racers_weights_are_held_against_the_pack_and_the_disc(self):
        disc = car_data()
        _, pack = sp.make(disc, 6, 2, "p")
        doubled, twelve = sp.entries_of(pack)[6, 4], sp.word(disc, 12, 4)
        lines, ok = sp.weights(states(300, [(6, doubled), (12, twelve), (41, 7)]) + states(301, [(6, doubled)]), pack, disc, 6)
        self.assertTrue(ok)
        self.assertIn("2 states: 3 of 3 racers hold their machines' weights, 0 another; machine 6's is the pack's", lines[-1])
        # a racer with another weight is said, and no failure (a computer racer's may not be its machine's)
        lines, ok = sp.weights(states(300, [(6, doubled), (12, twelve + 1)]), pack, disc, 6)
        self.assertTrue(ok)
        self.assertIn("1 of 2 racers hold their machines' weights, 1 another (the first: step 300, racer 1 on machine 12 holds", lines[-1])
        for dump, said in [(states(300, [(6, sp.word(disc, 6, 4)), (12, twelve)]), "no racer on machine 6 holds the pack's weight for it"),
                           (states(300, [(12, twelve)]), "no racer on machine 6 holds the pack's weight for it"),
                           (b"", "the file holds no state"),
                           (states(300, [(6, doubled)])[:-5], "the state dump is broken at byte 0")]:
            lines, ok = sp.weights(dump, pack, disc, 6)
            self.assertFalse(ok)
            self.assertIn(said, "\n".join(lines))
        # a machine whose weight the pack leaves: a racer on it holds the disc's
        seven = sp.word(disc, 7, 4)
        lines, ok = sp.weights(states(300, [(6, doubled), (7, seven)]), pack, disc, 7)
        self.assertTrue(ok)
        self.assertIn("the pack leaves machine 7's weight as the disc's", lines[-1])
        lines, ok = sp.weights(states(300, [(6, doubled), (7, seven + 1)]), pack, disc, 7)
        self.assertFalse(ok)
        self.assertIn("no racer on machine 7 holds its weight", lines[-1])


class TheReport(unittest.TestCase):
    PACK = {"name": "Made up A", "fingerprint": "f601e0748c2b0ee9b1cf212793f41318f60e4aec", "values": ""}
    LOG = ("fzgx: stat pack Made up A (f601e074): 3 of its 3 values written over the game's car data\n"
           "fzgx: stat pack Made up A (f601e074): its 3 values are in the game's car data; of 30 racers 30 hold their "
           "machines' weights from it and 0 another\n")

    def replay(self, folder, version, stats, name="race.fzrp", cpu=22, level=3):
        seats = [{"seat": i, "playerId": f"p{i}"} for i in range(30 - cpu)] + [{"seat": 30 - cpu + i, "cpu": True} for i in range(cpu)]
        setup = {"course": 1, "seats": seats, "rules": {"cpuLevel": level}, **({"stats": stats} if stats else {})}
        header = json.dumps({"match": {"setup": setup}}).encode()
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, name), "wb") as f:
            f.write(b"FZRP" + struct.pack(">HI", version, len(header)) + header + b"FZRF")

    @staticmethod
    def write(path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_what_a_games_log_says_of_its_pack(self):
        self.assertEqual(report.laid(self.LOG, self.PACK)[0], True)
        self.assertEqual(report.laid(self.LOG.splitlines()[0], self.PACK)[0], False)          # laid, never let go
        self.assertEqual(report.laid(self.LOG, dict(self.PACK, fingerprint="0" * 40))[0], False)   # another pack's lines
        refused = self.LOG + "fzgx: stat pack: racer 0 (machine 6) holds the weight 0: the race is refused; stopping\n"
        self.assertEqual(report.laid(refused, self.PACK)[0], False)
        other = self.LOG.replace("30 hold their machines' weights from it and 0 another", "22 hold their machines' weights from it and 8 another")
        self.assertEqual(report.laid(other, self.PACK)[0], True)   # what the racers hold is said, not judged
        self.assertIn("and 8 another", report.laid(other, self.PACK)[1])
        lost = self.LOG + "fzgx: stat pack Made up A: 1 of its values are not in the game's car data while the race runs\n"
        self.assertEqual(report.laid(lost, self.PACK)[0], False)
        self.assertEqual(report.laid("", self.PACK), (False, "no line of a stat pack"))

    ROLLED = "at_us,step,depth,forced\n1,300,0,0\n2,301,3,1\n"
    PLAYED = "fzgx: playback: 900 of 900 steps compared with the recording, 0 differed; rollbacks 0\n"
    EQUAL = result(0, "files 1 and 2: 900 steps in both; inputs equal; checksums equal at every step; the same lineup\n")
    APART = result(1, "files 1 and 2: 900 steps in both; inputs equal; checksums differ first at step 0 (900 steps differ)\n")

    def test_the_races_on_a_pack(self):
        with tempfile.TemporaryDirectory() as work:
            runs = os.path.join(work, "r")
            for i in (1, 2):
                for race in ("pack", "two"):
                    self.replay(f"{runs}-{race}-{i}", 3, self.PACK)
                    self.write(f"{runs}-{race}-{i}/fzgx.log", self.LOG)
                self.write(f"{runs}-pack-{i}/rb.csv", self.ROLLED)
            self.replay(f"{runs}-plain", 2, None)
            self.assertEqual(report.replay_pack(f"{runs}-pack-1/race.fzrp"), (3, self.PACK))
            self.assertEqual(report.replay_pack(f"{runs}-plain/race.fzrp"), (2, None))
            self.assertEqual(report.replay_pack(f"{runs}-none/race.fzrp"), (0, None))
            self.assertEqual(report.computer_racers(f"{runs}-pack-1/race.fzrp"), (22, 3))
            self.assertEqual((report.rollbacks(f"{runs}-pack-1"), report.rollbacks(f"{runs}-plain")), (1, -1))
            good = report.Report()
            report.plain(good, runs, "nmj", result(0, "  racers_hash by step: steps equal (2431 of 2431)\n"))
            report.same(good, runs, self.PACK, lambda replays: self.EQUAL, [result(0, "2 states: 30 of 30 racers hold")] * 2, [self.PLAYED] * 2)
            report.differ(good, runs, [self.PACK, self.PACK], self.APART, "race m1: go\nrace m1: checksums differ at frame 0: desync\n")
            self.assertEqual(good.failed, 0, good.lines)
            self.assertEqual(good.checks, 3 + 12 + 4)
            self.assertIn("ok   pack: 22 computer racers at CPU level 3", good.lines)
            # and each thing that must fail: a plain race that differs or holds a pack, recordings that differ, a
            # playback that differs or did not finish, no rollback, a weight that is not the pack's, two packs that
            # ran as one race, a relay that saw nothing, a race that was not run
            bad = report.Report()
            self.replay(f"{runs}-plain", 3, self.PACK)
            report.plain(bad, runs, "nmj", result(1, "  racers_hash by step: 12 steps differ\n"))
            os.remove(f"{runs}-pack-2/rb.csv")
            report.same(bad, runs, self.PACK, lambda replays: self.APART, [result(1, "no racer on machine 6 holds"), result(1, "")],
                        [self.PLAYED.replace("0 differed", "3 differed"), ""])
            report.differ(bad, runs, [self.PACK, self.PACK], self.EQUAL, "race m1: go\n")
            report.differ(bad, os.path.join(work, "none"), [self.PACK, self.PACK], self.EQUAL, "")
            failed = [line for line in bad.lines if line.startswith("FAIL")]
            self.assertEqual(len(failed), 2 + 6 + 2 + 1, bad.lines)
            self.assertIn("FAIL not run: RUN-two (two games handed different packs)", bad.lines)

    def test_the_races_without_a_pack_and_the_older_builds_recordings(self):
        with tempfile.TemporaryDirectory() as work:
            runs = os.path.join(work, "r")
            for i in (1, 2):
                self.replay(f"{runs}-plain2-{i}", 2, None)
                self.write(f"{runs}-plain2-{i}/fzgx.log", "fzgx: match m1: seat 0\n")
                self.write(f"{runs}-plain2-{i}/rb.csv", self.ROLLED)
                self.replay(f"{work}/old-{i}/replays", 2, None, name="m8.fzrp", cpu=24)
            names = [f"{work}/old-{i}/replays/m8.fzrp" for i in (1, 2)]
            good = report.Report()
            report.plain_pair(good, runs, self.EQUAL, [self.PLAYED] * 2)
            report.old(good, names, [self.PLAYED] * 2)
            self.assertEqual((good.failed, good.checks), (0, 10 + 2), good.lines)
            self.assertIn("ok   old: old-1/replays/m8.fzrp (24 computer racers, level 3), rollbacks forced: playback: 900 of 900 steps "
                          "compared with the recording, 0 differed", good.lines)
            # what must fail: a line of a stat pack in a game without one, a version 3 recording, a playback of the
            # older build that differs, recordings that are not one race, a race without computer racers
            bad = report.Report()
            self.write(f"{runs}-plain2-1/fzgx.log", self.LOG)
            self.replay(f"{runs}-plain2-2", 3, self.PACK)
            self.replay(f"{runs}-plain2-1", 2, None, cpu=0)
            report.plain_pair(bad, runs, self.APART, [self.PLAYED.replace("0 differed", "1 differed"), self.PLAYED])
            report.old(bad, names, ["", self.PLAYED])
            report.old(bad, [], [])
            report.plain_pair(bad, os.path.join(work, "none"), self.EQUAL, [])
            self.assertEqual(len([line for line in bad.lines if line.startswith("FAIL")]), 5 + 1 + 1 + 1, bad.lines)

    def test_the_race_from_a_server(self):
        whole = {"name": "Made up W", "fingerprint": "ab" * 20, "values": "A" * (8 * 5104)}
        log = self.LOG.replace("Made up A (f601e074)", "Made up W (abababab)").replace("3 of its 3", "42 of its 5104").replace("its 3 values", "its 5104 values")
        started = "Test: every race runs on the stat pack Made up W (5104 values, fingerprint " + "ab" * 20 + ").\n"
        with tempfile.TemporaryDirectory() as work:
            runs = os.path.join(work, "r")
            for i in (1, 2):
                self.replay(f"{runs}-srv-{i}/replays", 3, whole, name="20261011-m1.fzrp", cpu=28, level=1)
                self.write(f"{runs}-srv-{i}/race1/runner.log", log)
                self.write(f"{runs}-srv-{i}/race1/rb.csv", self.ROLLED)
            good = report.Report()
            report.served(good, runs, whole, started)
            level = report.same(good, runs, whole, lambda replays: self.EQUAL if all("replays/20261011-m1.fzrp" in r for r in replays) else self.APART,
                                [result(0, "2 states: 30 of 30 racers hold")] * 2, [self.PLAYED] * 2, race="srv")
            self.assertEqual((good.failed, good.checks, level), (0, 2 + 12, 1), good.lines)
            self.assertIn("ok   srv: both games hold all 5104 values at the go (written over the disc's: 42)", good.lines)
            self.assertIn("ok   srv: 28 computer racers at CPU level 1", good.lines)
            # a server that named no pack, a game that wrote another count of it, a launcher that kept no replay
            bad = report.Report()
            self.write(f"{runs}-srv-2/race1/runner.log", log.replace("42 of its 5104", "41 of its 5104"))   # the games wrote unlike counts
            os.remove(f"{runs}-srv-1/replays/20261011-m1.fzrp")
            report.served(bad, runs, whole, "Test: no stat pack: races run on the original stats.\n")
            report.same(bad, runs, whole, lambda replays: self.APART, [result(0, "")] * 2, [self.PLAYED] * 2, race="srv")
            report.same(bad, os.path.join(work, "none"), whole, None, [], [], race="srv")
            failed = [line for line in bad.lines if line.startswith("FAIL")]
            self.assertEqual(len(failed), 2 + 3 + 1, bad.lines)   # (and the first game's replay, the race, its computer racers)
            self.assertIn("FAIL not run: RUN-srv (the pack from a server, through Quick Play)", failed)

    def test_the_packs_nobody_takes(self):
        with tempfile.TemporaryDirectory() as work:
            runs = os.path.join(work, "r")
            self.assertEqual(report.REFUSED, tuple(sp.BAD))
            for kind in report.REFUSED:
                self.write(f"{runs}-no-{kind}/stderr.txt", "The match's stat pack is not one this launcher takes: machine 6 Weight is the bits 00000001.\r\n")
                self.write(f"{runs}-game-{kind}/stderr.txt", "fzgx: D:\\m.json: the race's stat pack is refused: machine 6 Weight is the bits 00000001\n")
            good = report.Report()
            report.refused(good, runs)
            self.assertEqual((good.failed, good.checks), (0, 6), good.lines)
            # a launcher that started the game all the same, a game that said nothing
            bad = report.Report()
            self.write(f"{runs}-no-denormal/probe.csv", "field,a\n1,0\n2,0\n")
            self.write(f"{runs}-no-negative/stderr.txt", "")
            self.write(f"{runs}-game-negative/stderr.txt", "fzgx: match m1\n")
            report.refused(bad, runs)
            report.refused(bad, os.path.join(work, "none"))
            self.assertEqual(len([line for line in bad.lines if line.startswith("FAIL")]), 3 + 1, bad.lines)

    def test_a_race_on_a_pack_of_the_repository_is_judged_as_the_made_up_packs_race(self):
        with tempfile.TemporaryDirectory() as work:
            runs = os.path.join(work, "r")
            for i in (1, 2):
                self.replay(f"{runs}-real-{i}", 3, self.PACK)
                self.write(f"{runs}-real-{i}/fzgx.log", self.LOG)
                self.write(f"{runs}-real-{i}/rb.csv", self.ROLLED)
            good = report.Report()
            report.same(good, runs, self.PACK, lambda replays: self.EQUAL, [result(0, "2 states: 60 of 60 racers hold")] * 2, [self.PLAYED] * 2, race="real")
            self.assertEqual((good.failed, good.checks), (0, 12), good.lines)
            self.assertIn("ok   real: 22 computer racers at CPU level 3", good.lines)
            bad = report.Report()
            report.same(bad, os.path.join(work, "none"), self.PACK, None, [], [], race="real")
            self.assertEqual(bad.lines, ["FAIL not run: RUN-real (two games on a pack of the repository)"])


if __name__ == "__main__":
    unittest.main()
