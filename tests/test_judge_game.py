"""The judges that read one game's folder (gate-judge.py game, runs, playback), on a made-up work folder: a clean
game, and each fault by its name. Run by scripts/check.sh: python3 -m unittest discover -s port/gates/tests."""
import json
import os
import unittest

from judge_fixtures import CRASH, LEFT, PACE, SUMMARY, Work, gj, probe, verdict


class Folders(Work, unittest.TestCase):
    """The judges that read run folders, on a made-up work folder."""

    def test_a_clean_game_passes_and_each_fault_is_named(self):
        self.game_files("clean")
        self.assertEqual(verdict("game", "clean", "--end", "results")[0], 0)
        self.game_files("crashed", log=CRASH)
        status, out = verdict("game", "crashed", "--end", "results")
        self.assertEqual(status, 1)
        self.assertIn("crashed: 1 line(s) like '[staticrecomp] unknown guest instruction", out)
        self.assertIn("no end line 'the player left the results; stopping'", out)
        self.game_files("stuck", gaps=[16_683] * 300 + [2_000_000] * 30)
        self.assertIn("FAIL stuck: frozen:", verdict("game", "stuck")[1])
        self.game_files("copies", pace="F,1,10,0,2,36,5\n" + "E,1,5,1,0,0,0,128,128,5,01235fa0\n" * 3 + "E,1,5,1,0,0,0,640,448,4,01235fa0\n")
        self.assertIn("screen copies of two sizes", verdict("game", "copies", "--end", "results")[1])
        self.write("port/runs/silent/probe.csv", probe([16_683] * 300))
        self.assertIn("no log of the game was kept", verdict("game", "silent")[1])

    def test_a_game_that_booted_twice_is_a_reset_in_its_own_words(self):
        boot = "fzgx: the game's code: 70 words written, 3 already patched, 0 refused\n"
        # the game of 2026-10-06 (rgrAB-bg2-2): racing at race frame 1585, then its start gate again, in mode 0
        lines = ["field,ticks,module,mode,submode,race_frame,x,qpc_us"]
        frames = [(0, 0)] * 8 + [(510, 33423870)] * 3 + [(0, 0)] * 20 + [(2, f) for f in range(1586)] + [(0, 0)] * 12 \
            + [(510, 33423870)] * 3 + [(2, 0)] * 17
        lines += [f"{i},0,801ba660,{mode},36,{frame},0,{1000 + i * 16_683}" for i, (mode, frame) in enumerate(frames)]
        self.write("port/runs/twice/fzgx.log", boot + "fzgx: go\n" + boot)
        self.write("port/runs/twice/stderr.txt", boot + "fzgx: go\n" + boot)
        self.write("port/runs/twice/probe.csv", "\n".join(lines) + "\n")
        self.write("port/runs/twice/pace.csv", PACE)
        status, out = verdict("runs", "twice")           # no word of launcher-run.sh's: seen by itself
        self.assertEqual(status, 1)
        self.assertIn("FAIL twice: RESET: the game booted again at field 1617 after race frame 1585 (2 boots in its log)", out)
        # launcher-run.sh's line is in end.txt and in the run's log: said once
        said = "twice: RESET: the game was at race frame 1585 and is at its start gate again at field 1629 (it booted again); stopping\n"
        self.write("port/runs/twice/end.txt", said)
        status, out = verdict("game", "twice", "--end", "results", "--log", self.write("run.log", said))
        self.assertEqual(out.count("is at its start gate again"), 2)      # once as a finding, once in the verdict
        # either sign alone
        self.write("port/runs/twice/fzgx.log", boot + "fzgx: go\n")
        self.write("port/runs/twice/stderr.txt", "")
        os.remove(os.path.join(self.tmp.name, "port/runs/twice/end.txt"))
        self.assertIn("RESET: the game booted again at field 1617 after race frame 1585 (its race frame is back at 0)",
                      verdict("game", "twice", "--end", "results")[1])
        self.assertNotIn("RESET", verdict("game", "twice")[1])   # not a match race: offline play goes from race to race
        self.game_files("logonly", log=boot + boot + LEFT)
        self.assertIn("RESET: the game booted again (2 lines 'fzgx: the game's code:' in one log", verdict("runs", "logonly")[1])
        # one boot named in two logs, a rollback's steps back, and a boot's stray race frame: no reset
        self.game_files("once", log=boot + LEFT)
        self.write("port/runs/once/stderr.txt", boot)
        back = [(0, 0)] * 8 + [(510, 33423870)] * 3 + [(0, 0)] * 20 + [(2, f) for f in range(300)] + [(2, 287)] + [(2, f) for f in range(288, 400)]
        self.write("port/runs/once/probe.csv", "\n".join([lines[0]] + [f"{i},0,801ba660,{m},36,{f},0,{1000 + i * 16_683}" for i, (m, f) in enumerate(back)]) + "\n")
        status, out = verdict("game", "once", "--end", "results", "--must", "probe", "pace")
        self.assertEqual(status, 0, out)

    def test_a_game_that_spun_without_idling_was_waiting_on_the_graphics_side(self):
        def pace(*idles):   # race fields from race frame 61 on, the CPU thread's idles in each
            rows = ["# pacing log", "E,1,5,1,0,0,0,128,128,5,01235fa0"]
            rows += [f"F,{1000 + k},{2000 + k},0,2,36,{61 + k}," + ",".join(["0"] * 15) + f",{n},0,,," for k, n in enumerate(idles)]
            return "\n".join(rows) + "\n"
        healthy = [545, 544, 3, 2, 550] * 40                     # frames that overran their field: rows of 2
        self.assertIsNone(gj.spun(pace(*healthy).splitlines()))
        self.assertIsNone(gj.spun(pace(*([550] * 20 + [0] * 9 + [550] * 20)).splitlines()))
        said = gj.spun(pace(*([550] * 20 + [0, 5, 1, 0, 0, 2, 0, 0, 0, 4] + [0] * 50 + [550] * 20)).splitlines())
        self.assertIn("the game spun without idling for 60 fields from field 2020: it was waiting on the graphics side", said)
        # not race fields: the start gate (race frame 0), a menu (mode 1)
        gate = "\n".join(f"F,{k},{k},0,2,36,0," + ",".join(["0"] * 15) + ",0,0,,," for k in range(100))
        menu = "\n".join(f"F,{k},{k},0,1,36,500," + ",".join(["0"] * 15) + ",0,0,,," for k in range(100))
        self.assertIsNone(gj.spun((gate + "\n" + menu).splitlines()))
        self.assertIsNone(gj.spun(["F,1,10,0,2,36,5000"] * 50))    # an older log's short records: nothing to read
        # a log that counts no idles at all (a JIT run's; an older log's short records): not checked, and said so
        for blind in (pace(*([0] * 400)), "F,1,10,0,2,36,5000\n" * 50 + "E,1,5,1,0,0,0,128,128,5,01235fa0\n"):
            self.assertEqual(gj.spin(blind.splitlines()), (None, False))
            self.game_files("blind", pace=blind)
            status, out = verdict("game", "blind", "--end", "results")
            self.assertEqual(status, 0)
            self.assertIn("its pacing log counts no idles: spin not checked", out)
            status, out = verdict("game", "blind", "--end", "results", "--must", "probe", "pace")
            self.assertEqual(status, 1)
            self.assertIn("FAIL blind: its pacing log counts no idles (pace.csv): whether the game spun was not checked", out)
        self.assertEqual(gj.spin(pace(*healthy).splitlines()), (None, True))
        self.game_files("spun", pace=pace(*([550] * 20 + [0] * 23 + [550] * 20)))
        status, out = verdict("game", "spun", "--end", "results")
        self.assertEqual(status, 1)
        self.assertIn("FAIL spun: the game spun without idling for 23 fields from field 2020", out)
        self.game_files("fine", pace=pace(*healthy))
        self.assertEqual(verdict("game", "fine", "--end", "results", "--must", "probe", "pace")[0], 0)

    def test_an_offline_game_must_exit_after_the_stop_command(self):
        self.game_files("off", log="")
        self.assertEqual(verdict("game", "off", "--end", "stop")[0], 1)
        self.write("port/runs/off/end.txt", "off: game and launcher exited 1.94s after the stop command; 5465 fields\n")
        self.assertEqual(verdict("game", "off", "--end", "stop")[0], 0)
        self.write("port/runs/off/end.txt", "off: GONE: the game's process ended 80s after the start with no end line of its own\n")
        status, out = verdict("game", "off", "--end", "stop")
        self.assertEqual(status, 1)
        self.assertIn("FAIL off: GONE: the game's process ended", out)

    def test_a_check_that_was_not_made_is_said_and_fails_where_the_file_is_always_written(self):
        said = "one size for each screen-copy destination"
        self.game_files("whole")
        status, out = verdict("game", "whole", "--end", "results", "--must", "probe", "pace")
        self.assertEqual(status, 0)
        self.assertIn("whole: no crash line, not frozen, ended as asked (results), " + said, out)
        for pace, words in ((None, "no pacing log: copies not checked"), ("# pacing log\n", "its pacing log holds no screen copy: copies not checked"),
                            ("F,1,10,0,2,36,5\n", "its pacing log holds no screen copy: copies not checked")):
            self.game_files("nopace")
            path = os.path.join(self.tmp.name, "port/runs/nopace/pace.csv")
            os.remove(path)
            if pace:
                self.write("port/runs/nopace/pace.csv", pace)
            status, out = verdict("game", "nopace", "--end", "results")       # offline: no pacing log is written
            self.assertEqual(status, 0)
            self.assertIn(words, out)
            self.assertNotIn(said, out)
            status, out = verdict("game", "nopace", "--end", "results", "--must", "probe", "pace")
            self.assertEqual(status, 1)
            self.assertIn(f"FAIL nopace: {words.split(':')[0]} (pace.csv)", out)
        self.game_files("noprobe")
        for content in (None, "field,qpc_us,race_frame\n"):
            os.remove(os.path.join(self.tmp.name, "port/runs/noprobe/probe.csv"))
            if content:
                self.write("port/runs/noprobe/probe.csv", content)
            status, out = verdict("game", "noprobe", "--end", "results")
            self.assertEqual(status, 0)
            self.assertIn("no probe: freeze not checked", out)
            self.assertNotIn("not frozen", out)
            status, out = verdict("game", "noprobe", "--end", "results", "--must", "probe")
            self.assertEqual(status, 1)
            self.assertIn("FAIL noprobe: no probe (probe.csv is missing or holds no field)", out)
            self.write("port/runs/noprobe/probe.csv", "x")
        status, out = verdict("runs", "noprobe", "whole")
        self.assertEqual(status, 0)
        self.assertIn("2 runs: no crash line, 1 not frozen, 1 with no probe: freeze not checked", out)

    def test_a_playback_with_a_pacing_log_fails_on_its_screen_copies(self):
        self.write("port/runs/pb-1/stderr.txt", "fzgx: " + SUMMARY.format(60, 60, 0) + "\n")
        self.write("port/runs/pb-1/probe.csv", probe([16_683] * 300))
        self.assertEqual(verdict("playback", "pb-1", "no-such.fzrp")[0], 0)          # no pacing log: as before
        self.write("port/runs/pb-1/pace.csv", "F,1,10,0,2,36,5\n" + "E,1,5,1,0,0,0,128,128,5,01235fa0\n" * 3)
        self.assertEqual(verdict("playback", "pb-1", "no-such.fzrp")[0], 0)
        self.write("port/runs/pb-1/pace.csv", "F,1,10,0,2,36,5\n" + "E,1,5,1,0,0,0,128,128,5,01235fa0\n" * 3 + "E,1,5,1,0,0,0,640,448,4,01235fa0\n")
        status, out = verdict("playback", "pb-1", "no-such.fzrp")
        self.assertEqual(status, 1)
        self.assertIn("60 of 60 steps compared, 0 differed", out)
        self.assertIn("screen copies of two sizes to one destination", out)
        self.assertTrue(out.rstrip().endswith(": FAIL"))

    def test_a_jit_reference_run_may_have_an_empty_log_and_no_other_game_may(self):
        # the batch row's reference runs: the JIT prints nothing of its own, only a line for a second that ran slow
        for run, kind in (("t-dual-core-race300-ref-1", "reference"), ("t-dual-core-race300-on-1", "native")):
            self.write(f"port/runs/{run}/stderr.txt", "" if kind == "reference" else "fzgx: native form: image 62b3d9bf\n")
            self.write(f"port/runs/{run}/probe.csv", probe([16_683] * 300))
            self.write(f"port/runs/{run}/run.json", json.dumps({"run": run, "kind": kind, "build": None}))
        status, out = verdict("runs", "t-dual-core-*")
        self.assertEqual(status, 0, out)
        self.assertIn("2 runs: no crash line, none frozen; 1 of them JIT reference runs whose log is empty", out)
        # a native run with an empty log, a reference run with no log file at all, a reference run that crashed
        self.write("port/runs/t-dual-core-race300-on-1/stderr.txt", "")
        status, out = verdict("runs", "t-dual-core-*")
        self.assertEqual(status, 1)
        self.assertIn("FAIL t-dual-core-race300-on-1: no log of the game was kept", out)
        self.assertNotIn("FAIL t-dual-core-race300-ref-1", out)
        os.remove(os.path.join(self.tmp.name, "port/runs/t-dual-core-race300-ref-1/stderr.txt"))
        self.assertIn("FAIL t-dual-core-race300-ref-1: no log of the game was kept", verdict("runs", "t-dual-core-*")[1])
        self.write("port/runs/t-dual-core-race300-ref-1/stderr.txt", "[zero-access] read of 00000000 at 8006dbe0\n")
        self.assertIn("FAIL t-dual-core-race300-ref-1: crashed", verdict("runs", "t-dual-core-*")[1])
        # and no game that must end in a way of its own is excused: its end line has to be somewhere
        self.write("port/runs/t-dual-core-race300-ref-1/stderr.txt", "")
        self.assertIn("no log of the game was kept", verdict("game", "t-dual-core-race300-ref-1", "--end", "results")[1])

    def test_runs_reads_every_folder_of_a_pattern(self):
        self.game_files("t-scene-race300")
        self.game_files("t-scene-racego", log=CRASH)
        status, out = verdict("runs", "t-scene-*")
        self.assertEqual(status, 1)
        self.assertIn("FAIL t-scene-racego: crashed", out)
        self.assertEqual(verdict("runs", "nothing-*")[0], 1)


if __name__ == "__main__":
    unittest.main()
