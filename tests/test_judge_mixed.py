"""The judge of a race whose games ran different builds (gate-judge.py mixed), on a made-up work folder: the run's
record, each game's files and recording, its rollback log and its dump of the machines' state.
Run by scripts/check.sh: python3 -m unittest discover -s port/gates/tests."""
import os
import unittest

from judge_fixtures import LEFT, OBSERVED, Work, machine_states as state, recording, verdict   # noqa: F401


class Mixed(Work, unittest.TestCase):
    race = Work.mixed_race
    OLD, NEW, IMAGE = Work.OLD, Work.NEW, Work.IMAGE

    def test_two_builds_equal_at_every_step_pass_and_say_which_game_ran_which(self):
        self.race("ab")
        self.race("ba", modules=(self.NEW, self.OLD))
        status, out = verdict("mixed", "ab", "ba")
        self.assertEqual(status, 0, out)
        self.assertIn("ab: the recordings: 60 steps in each of 2, equal at every step, the same results", out)
        self.assertIn("game 1 (launcher-old: 11111111/aaaaaaaa/22222222): lag 30 ms, forced rollbacks 1 of depth 6, "
                      "1 of depth 12, its seat 0 on the wall: 3 hits by step 40", out)
        self.assertIn("game 2 (launcher-new: 11111111/bbbbbbbb/22222222): lag 90 ms, forced rollbacks 1 of depth 6, "
                      "1 of depth 12, its seat 1 across the line", out)
        self.assertIn("game 1 (launcher-new: 11111111/bbbbbbbb/22222222)", out)   # the roles swapped in run ba

    def test_a_difference_names_its_first_step_and_both_builds(self):
        sums = [i if i < 40 else i + 1000 for i in range(60)]
        self.race(sums2=sums)
        status, out = verdict("mixed", "m")
        self.assertEqual(status, 1)
        self.assertIn("FAIL the builds differ: game 1 (launcher-old: 11111111/aaaaaaaa/22222222) and game 2 "
                      "(launcher-new: 11111111/bbbbbbbb/22222222) differ first at step 40: checksums differ at 20 of "
                      "the 60 steps both recorded, first at 40; inputs equal", out)
        # the states both wrote are the same: the judge says how to get the state itself
        self.assertIn("no state both games wrote differs (steps 40 to 41, the last not written): for the state itself "
                      "run again with STATES=40,42", out)
        self.assertNotIn("(inputs or checksum)", out)   # said once, with the builds
        # and with the state of the step in both dumps: the first word that differs, by racer and offset
        at = 2 * (0x620 + 0x1FC) + 0x620 + 0x10
        self.race(sums2=sums, states=(state(40), state(40, word=(at + 3, 0x80))))
        status, out = verdict("mixed", "m")
        self.assertEqual(status, 1)
        self.assertIn("the machines' state at step 40: 1 word(s) the checksum covers differ, the first in racer 2, "
                      "progress +0x10 (00000000 in game 1, 00000080 in game 2)", out)
        # a word the checksum leaves out (a pointer: block +0x484) differs between equal games, and is no finding
        self.race(sums2=sums, states=(state(40), state(40, word=(0x484, 0x81))))
        self.assertIn("no state both games wrote differs", verdict("mixed", "m")[1])

    def test_one_build_in_both_games_is_not_a_mixed_race(self):
        self.race(modules=(self.OLD, self.OLD))
        status, out = verdict("mixed", "m")
        self.assertEqual(status, 1)
        self.assertIn("FAIL the builds: 1 build(s) in 2 games, 2 are wanted", out)
        self.assertEqual(verdict("mixed", "m", "--builds", 1)[0], 0)   # the same race as a base line
        # a game whose recording names another module than its folder held ran nobody knows what
        self.race(said2={"module_sha1": self.OLD, "mod_sha1": self.IMAGE})
        status, out = verdict("mixed", "m")
        self.assertEqual(status, 1)
        self.assertIn("FAIL m-2: its recording says module aaaaaaaa, and launcher-new held bbbbbbbb when the run began", out)

    def test_a_race_without_its_conditions_is_no_pass(self):
        cases = ((dict(rollbacks="at_us,step,depth,forced\n1,10,6,1\n2,17,12,0\n"), "FAIL m-1: no forced rollback 12 steps deep"),
                 (dict(states=(state(40, hits=0), state(40))), "FAIL m-1: its seat 0 was to be driven into the wall, and its state dump counts 0 wall hits (steps 40)"),
                 (dict(states=(b"", b"")), "FAIL m-1: its seat 0 was to be driven into the wall, and its state dump holds no state"),
                 (dict(results={"results": [{"seat": 0, "finished": False, "out": False}, {"seat": 1, "finished": False, "out": True}]}),
                  "FAIL m-2: its seat 1, which the game's AI drove, has no finish in its results"),
                 (dict(log="fzgx: go (x)\n" + LEFT), "FAIL m-2: its log does not say 'test lag 90 ms': the lag was not on"),
                 (dict(log="fzgx: network session, test lag 30 ms, test lag 90 ms\n" + LEFT), "FAIL m-1: its log has no 'go' line"),
                 (dict(relay=OBSERVED.format(59)), "FAIL the relay: 1 line(s) of a difference in its log, the first: 19:05:18 race m32: desync, checksums differ at frame 59"))
        for change, said in cases:
            self.race(**change)
            status, out = verdict("mixed", "m")
            self.assertEqual(status, 1, said)
            self.assertIn(said, out)

    def test_a_run_without_its_record_or_a_recording_fails(self):
        status, out = verdict("mixed", "none")
        self.assertEqual(status, 1)
        self.assertIn("FAIL none: no record of its games (port/scratch/mixed/none.games.tsv", out)
        self.race()
        os.remove(os.path.join(self.tmp.name, "port/runs/m-2/race.fzrp"))
        status, out = verdict("mixed", "m")
        self.assertEqual(status, 1)
        self.assertIn("FAIL m-2: no recording (race.fzrp)", out)


if __name__ == "__main__":
    unittest.main()
