"""The parts of the gates' judges, which read text and rows: crash lines, a frozen probe, screen copies, the
recordings of one race (and replay-compare.py's lengths), a playback's result.
Run by scripts/check.sh: python3 -m unittest discover -s port/gates/tests."""
import contextlib
import io
import json
import os
import struct
import tempfile
import unittest

from judge_fixtures import CRASH, LEFT, SUMMARY, compare, gj, probe, recording


class Parts(unittest.TestCase):
    def test_the_undo_logs_check_passes_only_when_the_guard_went_on_and_never_differed(self):
        on = "fzgx: undo log: guard on at its step 121: 4300 pages write-protected, 160 watched\n"
        same = "fzgx: undo log check: 7400 steps compared with every page: the log the same at every step\n"
        self.assertIsNone(gj.undo_check(on + same))
        self.assertIn("never went on", gj.undo_check(same))
        self.assertIn("no guard (the host", gj.undo_check("fzgx: undo log: no guard (the host does not say) x\n" + same))
        self.assertIn("no line of the undo log's check", gj.undo_check(on))
        self.assertIn("the log different at 3 steps",
                      gj.undo_check(on + "fzgx: undo log check: 7400 steps compared with every page: the log different at 3 steps\n"))
        self.assertIn("0 steps compared", gj.undo_check(on + "fzgx: undo log check: 0 steps compared with every page: the log the same at every step\n"))

    def test_crash_lines_are_the_two_kinds_only(self):
        text = "[staticrecomp] core init\n" + CRASH + "[zero-access] read of 00000000 at 8006dbe0\nfzgx: go\n"
        self.assertEqual(len(gj.crash_lines(text)), 2)
        self.assertEqual(gj.crash_lines("[staticrecomp] busy-wait loop detected at 8000b4b4\n" + LEFT), [])

    def test_frozen_is_a_slow_end_not_a_slow_middle(self):
        steady = [16_683] * 600
        read = lambda text: gj.probe_fields(self.write("probe.csv", text))
        self.assertIsNone(gj.frozen(read(probe(steady))))
        # a wait of 13 s at the start gate, then the race: not frozen
        self.assertIsNone(gj.frozen(read(probe(steady + [13_000_000] + steady))))
        # ten seconds of slow fields at the end: under the limit
        self.assertIsNone(gj.frozen(read(probe(steady + [2_000_000] * 5))))
        frames = list(range(601)) + [600] * 20
        said = gj.frozen(read(probe(steady + [1_700_000] * 20, frames)))
        self.assertIn("frozen: its last 20 fields took 34 s", said)
        self.assertIn("race frame 600 stood still", said)
        self.assertIsNone(gj.frozen([]))

    def test_screen_copies_one_size_for_each_destination(self):
        small = ["F,1,10,0,2,36,2338", "E,1,5,1,0,0,0,128,128,5,01235fa0", "E,1,5,1,0,0,0,128,128,5,01235fa0",
                 "E,1,5,1,0,0,0,640,448,5,00095ec0", "E,1,5,1,0,0,0,640,448,4,00095ec0"]   # two formats, one size
        self.assertEqual(gj.screen_copies(small), [])
        bad = gj.screen_copies(small + ["F,1,11,0,2,36,2339", "E,1,5,1,0,0,0,640,448,4,01235fa0"])
        self.assertEqual(len(bad), 1)
        self.assertIn("01235fa0 (usually 128x128) got 640x448 after race frame 2339", bad[0])

    def rec(self, steps, results=True, sums=None):
        return compare.read(self.write(f"r{steps}{results}{bool(sums)}.fzrp", recording(steps, results, sums)))

    def write(self, name, content):
        path = os.path.join(self.tmp.name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(content, bytes) else "w") as f:
            f.write(content)
        return path

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def recordings(self, *games):
        v = gj.Verdict()
        with contextlib.redirect_stdout(io.StringIO()):
            gj.recordings(list(games), v)
        return v

    def test_recordings_of_equal_length_pass(self):
        v = self.recordings(("game 1", self.rec(50), True), ("game 2", self.rec(50), True))
        self.assertEqual(v.bad, [])
        self.assertIn("50 steps in each of 2, equal at every step, the same results", v.figures[0])

    def test_recordings_of_other_lengths_pass_only_when_every_game_left_its_results(self):
        v = self.recordings(("game 1", self.rec(57), True), ("game 2", self.rec(50), True))
        self.assertEqual(v.bad, [])
        self.assertIn("each game records until its own player leaves the results", v.figures[0])
        # the dead game of 2026-10-06: equal over the steps it holds, no results, no end line
        v = self.recordings(("game 1", self.rec(8357), True), ("game 3", self.rec(2735, results=False), False))
        self.assertEqual(len(v.bad), 1)
        self.assertIn("game 3 recorded 2735 steps of 8357: cut short", v.bad[0])
        self.assertIn("holds no results", v.bad[0])
        self.assertIn("never logged", v.bad[0])
        # results in the file, yet its game never said that it left
        v = self.recordings(("game 1", self.rec(57), True), ("game 2", self.rec(50), False))
        self.assertIn("game 2 recorded 50 steps of 57", v.bad[0])

    def test_games_that_log_when_their_results_could_be_left_are_each_timed_from_there(self):
        # The thirty row of v030 (gv030-024218-q30): 26th, 11th and 6th left 8711, 8892 and 9075 steps, one press
        # (180 steps) apart each, as their pages opened by standing. Across the games that is 364 steps, more than
        # the old bound; from its own moment each left at the next press. (Those logs are from before the line: the
        # moments here are a press before each leave, where the game's rows put them.)
        q30 = [("launcher 1", 8711, 8531), ("launcher 2", 8892, 8712), ("launcher 3", 9075, 8895)]
        v = self.recordings(*((name, self.rec(n), True, at) for name, n, at in q30))
        self.assertEqual(v.bad, [])
        self.assertIn("each left 180, 180, 180 steps after its results could be left", v.figures[0])
        self.assertGreater(9075 - 8711, gj.MAX_SHORTER)                       # failed the bound across games
        v = self.recordings(*((name, self.rec(n), True) for name, n, _ in q30))
        self.assertIn("launcher 1 recorded 8711 steps of 9075: 364 short", v.bad[0])
        # 0.2.2's thirty row (gv022-214152): 14th left first, 6th and 7th one press later, 9 steps apart
        gv022 = [("launcher 1", 8887, 8707), ("launcher 2", 8896, 8707), ("launcher 3", 8708, 8528)]
        v = self.recordings(*((name, self.rec(n), True, at) for name, n, at in gv022))
        self.assertEqual(v.bad, [])
        self.assertIn("each left 180, 189, 180 steps after", v.figures[0])

    def test_a_game_that_leaves_its_results_one_press_later_passes(self):
        # row pair's grid-p1 (2026-10-23): its games left 241 and 244 steps after their moments, one press late
        v = self.recordings(("grid-p1-1", self.rec(3048), True, 2807), ("grid-p1-2", self.rec(3052), True, 2808))
        self.assertEqual(v.bad, [])
        self.assertIn("each left 241, 244 steps after its results could be left", v.figures[0])

    def test_a_game_that_leaves_its_results_much_later_than_it_could_fails(self):
        # a press lost, or a game that hung on its results page: 544 steps after its own moment, whatever the others
        v = self.recordings(("launcher 1", self.rec(8711), True, 8531), ("launcher 2", self.rec(9075), True, 8531))
        self.assertEqual(len(v.bad), 1)
        self.assertIn("launcher 2 recorded 9075 steps: it left its results 544 steps after they could first be left "
                      f"(step 8531), and a game leaves them within {gj.LEAVE_WITHIN}", v.bad[0])
        # a moment after the recording's end is no moment of this race
        v = self.recordings(("launcher 1", self.rec(8711), True, 8531), ("launcher 2", self.rec(8711), True, 8800))
        self.assertIn("launcher 2 recorded 8711 steps: it left its results -89 steps after", v.bad[0])
        # one game of a build before the line: the bound across games, for all
        v = self.recordings(("launcher 1", self.rec(8711), True, 8531), ("launcher 2", self.rec(9075), True))
        self.assertIn("launcher 1 recorded 8711 steps of 9075: 364 short", v.bad[0])

    def test_recordings_of_equal_length_are_asked_the_same_questions(self):
        # two files of no step, or cut at the same step with no results: equal, and no race
        v = self.recordings(("game 1", self.rec(0, results=False), True), ("game 2", self.rec(0, results=False), True))
        self.assertIn("game 1's recording holds no step", v.bad[0])
        self.assertEqual(len([b for b in v.bad if "holds no step" in b]), 2)
        v = self.recordings(("game 1", self.rec(1000, results=False), True), ("game 2", self.rec(1000, results=False), True))
        self.assertEqual(len(v.bad), 2)
        self.assertIn("game 1 recorded 1000 steps of 1000: its recording holds no results", v.bad[0])
        one = compare.read(self.write("other.fzrp", recording(50)[:-20] + b'{"first": 4}' + struct.pack(">I", 12) + b"FZRS"))
        v = self.recordings(("game 1", self.rec(50), True), ("game 2", one, True))
        self.assertIn("hold OTHER results", v.bad[0])

    def test_a_recording_much_shorter_or_cut_inside_a_step_fails_whatever_its_trailer_says(self):
        # 100 steps with a results trailer against a whole race
        v = self.recordings(("game 1", self.rec(100), True), ("game 2", self.rec(3687), True))
        self.assertEqual(len(v.bad), 1)
        self.assertIn("game 1 recorded 100 steps of 3687: 3587 short", v.bad[0])
        self.assertEqual(self.recordings(("game 1", self.rec(3687 - gj.MAX_SHORTER), True), ("game 2", self.rec(3687), True)).bad, [])
        self.assertEqual(len(self.recordings(("game 1", self.rec(3686 - gj.MAX_SHORTER), True), ("game 2", self.rec(3687), True)).bad), 1)
        whole = recording(50)
        tail = len(json.dumps({"first": 3})) + 8
        cut = compare.read(self.write("cut.fzrp", whole[:-tail - 7] + whole[-tail:]))   # seven bytes of the last step gone
        self.assertFalse(cut["whole"])
        v = self.recordings(("game 1", cut, True), ("game 2", self.rec(50), True))
        self.assertIn("game 1's recording is cut inside a step (after 49 whole steps)", v.bad[0])

    def test_recordings_that_differ_fail(self):
        sums = list(range(50))
        sums[30] = 999
        v = self.recordings(("game 1", self.rec(50), True), ("game 2", self.rec(50, sums=sums), True))
        self.assertIn("differ first at step 30", v.bad[0])

    def test_replay_compare_reads_a_compact_file_with_a_whole_one(self):
        rf = compare.replay_file

        def file(steps, sums=None, compact=True):   # a recording with a lineup (the game's), made compact
            data = recording(steps, sums=sums)
            at = data.index(b"FZRF") + 12
            data = data[:at] + b"FZRL" + struct.pack(">I", 124) + bytes(124) + data[at:]
            return rf.compact(data) if compact else data

        whole, small = self.write("w.fzrp", file(130, compact=False)), self.write("c.fzrp", file(130))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(compare.main(["--same-length", whole, small]), 0)
        self.assertIn("130 steps, compact, course 1", out.getvalue())
        self.assertIn("130 steps in both; inputs equal; checksums equal at every step", out.getvalue())
        for step, change, first in ((70, 1, 70), (120, 0x01010101, 120), (70, 0x01010101, None)):
            sums = list(range(130))
            sums[step] ^= change    # (the last: a change the folded byte cannot see, at a step that keeps only the byte)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(compare.main([whole, self.write("d.fzrp", file(130, sums=sums))]), 0 if first is None else 1)
            self.assertIn("checksums equal at every step" if first is None else f"differ first at step {first}", out.getvalue())

    def test_replay_compare_shows_the_lengths_and_can_require_them(self):
        a, b = self.write("a.fzrp", recording(80)), self.write("b.fzrp", recording(27, results=False))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(compare.main([a, b]), 0)            # equal over the common steps, as before
            self.assertEqual(compare.main(["--same-length", a, b]), 1)
            self.assertEqual(compare.main(["--same-length", a, a]), 0)
        self.assertIn("27 steps in both; inputs equal; checksums equal at every step", out.getvalue())
        self.assertIn("LENGTHS DIFFER: 80 and 27 steps (file 2 is 53 short)", out.getvalue())

    def test_playback_results(self):
        self.assertEqual(gj.playback(SUMMARY.format(5641, 5841, 0), 5841, 178)[0], "PASS")
        result, said = gj.playback("warning: fzgx: the replay differs from the recording first at step 1614 (a, b)\n"
                                   + SUMMARY.format(9000, 9418, 44), 9418, 178)
        self.assertEqual(result, "FAIL")
        self.assertIn("44 differed (first at step 1614)", said)
        self.assertEqual(gj.playback(SUMMARY.format(0, 100, 0), 100, 178)[0], "FAIL")   # nothing compared
        # the race's results against the recording's (the runner's CheckResults): a difference fails, none compared passes,
        # and so does one in a recording from before version 7, whose results the runner does not judge
        for said, verdict in (("DIFFER from the recording's", "FAIL"), ("the recording's", "PASS"),
                              ("other, not judged (a recording from before 0.4.0)", "PASS"),
                              ("not in the recording", "PASS"), ("not reached", "PASS")):
            result, line = gj.playback(SUMMARY.format(100, 100, 0) + f"fzgx: playback: results {said}\n", 100, 178)
            self.assertEqual(result, verdict, said)
            self.assertEqual("results DIFFER" in line, verdict == "FAIL")
        self.assertEqual(gj.playback(CRASH + SUMMARY.format(10, 10, 0), 10, 178)[0], "FAIL")

    def test_a_playback_cut_short_is_its_own_result(self):
        log = ("fzgx: step 1799, official 5873, rollbacks 712\nfzgx: step 2999, official 5873, rollbacks 1312\n"
               "[slow] 18:46:44 23 fields in 1.03 s; PC 100% busy; x\n[slow] 18:46:45 21 fields in 1.03 s; PC 40% busy; x\n"
               "warning: fzgx: the replay differs from the recording first at step 1614 (a, b)\n")
        result, said = gj.playback(log, 5873, 178)
        self.assertEqual(result, "DID NOT FINISH")
        self.assertIn("did not finish: 2999 of 5873 steps", said)
        self.assertIn("limit of 178 s", said)
        self.assertIn("95% busy or more in 1 of its 2 slow seconds", said)
        self.assertIn("before the cut: differs from the recording first at step 1614", said)
        self.assertNotIn("differed", said)
        self.assertIn("2999 of 5873", gj.playback(log, None, 0)[1])   # the length from the log when no file is given

    def rows(self, text, expect, control=False):
        v = gj.Verdict()
        with contextlib.redirect_stdout(io.StringIO()):
            gj.playbacks(text, v, expect, control)
        return v

    def test_playback_rows(self):
        ok = "t-f{}-1: a.fzrp: 5623 of 5841 steps compared, 0 differed; rollbacks 9 (9 forced), deepest 17: PASS\n"
        cut = "t-f5-1: race.fzrp: did not finish: 2999 of 5873 steps (no summary line): DID NOT FINISH\n"
        five = "".join(ok.format(k) for k in (1, 2, 3, 4, 6)) + "replay-check t-f1: PASS\n"
        v = self.rows(five + cut, 6)
        self.assertEqual((v.bad, len(v.cut)), ([], 1))
        self.assertEqual(len(self.rows(five, 6).bad), 1)                  # one playback never reported
        old = "t-f5-1: race.fzrp: the playback did not finish (no summary line; 191 lines of log): FAIL\n"
        v = self.rows(five + old, 6)
        self.assertEqual((v.bad, len(v.cut)), ([], 1))                    # an older log's wording: not a FAIL
        differs = "t-ctl-1: m22.fzrp: 9000 of 9418 steps compared, {} differed; rollbacks 9 (9 forced), deepest 3: {}\n"
        self.assertEqual(self.rows(differs.format(44, "FAIL"), 1, control=True).bad, [])
        self.assertEqual(len(self.rows(differs.format(1, "FAIL"), 1, control=True).bad), 1)    # the recording's own
        self.assertEqual(len(self.rows(differs.format(0, "PASS"), 1, control=True).bad), 1)
        v = self.rows("t-ctl-1: m22.fzrp: did not finish: 7799 of 9418 steps (x): DID NOT FINISH\n", 1, control=True)
        self.assertEqual((v.bad, len(v.cut)), ([], 1))

    def test_pieces_counts_like_with_like(self):
        text = "".join(f"[staticrecomp] SMC: chunk [0x805A{k:04X},0x805B0000) hash mismatch; x ({k} failed)\n" for k in (1, 1, 2))
        text += "[staticrecomp] shutdown: native=1 fallback=0 smc_failed=2 verifications=3\n"
        self.assertEqual(gj.pieces(text), (2, 3, 2, 0))
        own = "[staticrecomp] SMC: chunk [0x80012340,0x80012380) hash mismatch; x (1 failed)\n"
        self.assertEqual(gj.pieces(text + own)[3], 1)


class NeverAPass(unittest.TestCase):
    """A playback cut by its time limit is its own result, in the judge's verdict and in its exit status."""

    def test_a_cut_playback_closes_as_did_not_finish_with_status_4(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            v = gj.Verdict()
            v.note("5 PASS")
            v.unfinished("t-f5-1", "did not finish: 2999 of 5873 steps")
            status = v.close()
        self.assertEqual(status, 4)
        self.assertIn("verdict: did not finish | t-f5-1: did not finish: 2999 of 5873 steps", out.getvalue())
        self.assertNotIn("verdict: pass", out.getvalue())
        with contextlib.redirect_stdout(out):
            v.fail("t-f6-1", "44 differed")              # a failure outranks it
            self.assertEqual(v.close(), 1)
            self.assertEqual(gj.Verdict().close(), 0)


if __name__ == "__main__":
    unittest.main()
