"""The batch row's memory gate with dead_stacks on v030's racego dumps (gv030-024218): the pair whose JIT run left a
pad-read path's frames in an ended thread's stack passes, and says the 23 words; every other pair is as before.
Needs the harness's deadstack.py (port/gates/vendor/harness, or RECOMP_KIT's) and the runs in the work folder: else
skipped, with the reason."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
HARNESS = (os.path.join(os.environ["RECOMP_KIT"], "tools", "harness") if os.environ.get("RECOMP_KIT")
           else os.path.join(ROOT, "port", "gates", "vendor", "harness"))   # as port/setup/lib.sh says
sys.path.insert(0, os.path.join(ROOT, "port", "setup"))   # work_folder.py: the work folder, this PC's over the default
import work_folder  # noqa: E402

RUNS = os.path.join(os.environ.get("PORT_WORK") or work_folder.WORK_DEFAULT, "port", "runs")
RUN = "gv030-024218-dual-core-racego-{}"
HAVE_KIT = os.path.isfile(os.path.join(HARNESS, "deadstack.py"))
HAVE_RUNS = os.path.isfile(os.path.join(RUNS, RUN.format("on-2"), "probe.csv.task300.ram"))


@unittest.skipUnless(HAVE_KIT and HAVE_RUNS, f"needs the harness's deadstack.py ({HARNESS}) and the runs ({RUNS})")
class DeadStacksOnV030(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, HARNESS)
        sys.path.insert(0, os.path.join(os.path.dirname(HARNESS), "manifest"))   # (a recomp-kit checkout's manifest.py)
        from manifest import Manifest
        import gate
        self.gate, self.m = gate, Manifest.load(os.path.join(ROOT, "recomp", "manifest.toml"))

    def pair(self, i):
        return self.gate.apply(self.m, os.path.join(RUNS, RUN.format(f"ref-{i}")), os.path.join(RUNS, RUN.format(f"on-{i}")),
                               "reference", "dual-core", "racego")

    def test_the_pair_with_an_ended_threads_old_frames_passes_and_says_them(self):
        ok, lines = self.pair(2)
        text = "\n".join(lines)
        self.assertTrue(ok, text)
        for step in (300, 900, 1500):
            self.assertIn(f"module-data at step {step}:", text)
        self.assertEqual(text.count("23 below a thread's stack pointer (dead stack)"), 3)

    def test_the_other_pair_has_no_dead_word_to_leave_out(self):
        ok, lines = self.pair(1)
        self.assertTrue(ok, "\n".join(lines))
        self.assertNotIn("dead stack", "\n".join(lines))

    def test_the_ended_thread_is_found_and_the_running_one_is_not_left_out(self):
        import deadstack
        with open(os.path.join(RUNS, RUN.format("ref-2"), "probe.csv.task300.ram"), "rb") as f:
            dump = f.read()
        found = {t["at"]: t for t in deadstack.threads(dump)}
        self.assertEqual((found[0x803FA238]["state"], found[0x803FA238]["r1"]), (0, 0x803FB520))   # .bss+0x85B98
        main = found[0x8015C430]                                     # the game's main thread, running at the dump
        self.assertTrue(main["current"])
        ranges = deadstack.dead_ranges(dump)
        self.assertIn((0x803FA564, 0x803FB520), ranges)
        self.assertFalse(any(main["end"] <= s < main["base"] for s, _ in ranges))


if __name__ == "__main__":
    unittest.main()
