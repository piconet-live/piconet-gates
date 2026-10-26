"""The judges of a race several games ran (gate-judge.py pair, desync, quickplay), on a made-up work folder.
Run by scripts/check.sh: python3 -m unittest discover -s port/gates/tests."""
import os
import unittest

from judge_fixtures import CRASH, LEFT, OBSERVED, OVER, SHORT, STOP, Work, recording, verdict


class Folders(Work, unittest.TestCase):
    """The judges that read the folders of several games of one race, on a made-up work folder."""

    def test_the_games_of_a_pair_and_of_quick_play_must_have_left_probe_and_pacing_log(self):
        ok = "pb-{0}-{1}: race.fzrp: 60 of 60 steps compared, 0 differed; rollbacks 0 (0 forced), deepest 0: PASS\n"
        for i in (1, 2):
            self.game_files(f"p-{i}")
            self.write(f"port/runs/p-{i}/race.fzrp", recording(60))
            self.launcher("q", i)
        pair = self.write("pair.log", "".join(ok.format("p", i) for i in (1, 2, 1, 2)))
        quick = self.write("quickplay.log", "".join(ok.format("q", f"{i}-1").replace("race.fzrp", "20261006-191326-m32.fzrp")
                                                  for i in (1, 2)))
        rows = (("pair", ["p", "--log", pair, "--playbacks", 4], "port/runs/p-2", "p-2"),
                ("quickplay", ["q", "--launchers", 2, "--races", 1, "--log", quick], "port/runs/q-2/race1", "launcher 2 (q-2), race 1 (m32)"))
        for kind, args, folder, who in rows:
            self.assertEqual(verdict(kind, *args)[0], 0, kind)
            for name, words in (("pace.csv", "no pacing log (pace.csv)"), ("probe.csv", "no probe (probe.csv")):
                path = os.path.join(self.tmp.name, folder, name)
                with open(path) as f:
                    kept = f.read()
                os.remove(path)
                status, out = verdict(kind, *args)
                self.assertEqual(status, 1, (kind, name))
                self.assertIn(f"FAIL {who}: {words}", out)
                self.write(os.path.join(folder, name), kept)

    OBSERVED = OBSERVED   # (the tests say self.OBSERVED)

    def desync(self, relay=None, sums=None, log2=LEFT, steps=120):
        """Run d: game 2 altered before step 40, so its checksums differ from there on; the relay found it at 59."""
        sums = sums or [i if i < 40 else i + 1000 for i in range(steps)]
        for i, log in ((1, LEFT), (2, log2)):
            self.game_files(f"d-{i}", log=log)
            self.write(f"port/runs/d-{i}/race.fzrp", recording(steps, sums=sums if i == 2 else None))
        self.write("port/scratch/pair/d.server.log", "19:05:17 race m32: go (30 player seats)\n" +
                   (self.OBSERVED.format(59) + self.OBSERVED.format(119) if relay is None else relay))
        return verdict("desync", "d", "--altered", 40)

    def test_desync_found_by_a_relay_that_observes_passes(self):
        status, out = self.desync()
        self.assertEqual(status, 0, out)
        self.assertIn("checksums differ at frame 59", out)
        self.assertIn("equal over steps 0 to 39, checksums differ at every step from 40 to 119", out)

    def test_desync_the_control_no_line_of_the_relay_fails(self):
        status, out = self.desync(relay="")
        self.assertEqual(status, 1)
        self.assertIn("FAIL the relay: its log has no 'checksums differ at frame' line: the difference was NOT found", out)
        # found, but a comparison too late: the relay compares every 60th step
        status, out = self.desync(relay=self.OBSERVED.format(119))
        self.assertEqual(status, 1)
        self.assertIn("FAIL the relay: it first found a difference at frame 119, not within", out)
        self.assertIn("(40 to 99)", out)

    def test_desync_nobody_is_disconnected(self):
        gone = "19:05:18 race m32: seat 28 desynced at frame 59; disconnected, the AI drives it\n"
        status, out = self.desync(relay=self.OBSERVED.format(59) + gone)
        self.assertEqual(status, 1)
        self.assertIn("FAIL the relay: it was to tell and disconnect nobody: 19:05:18 race m32: seat 28 desynced", out)
        against = self.OBSERVED.format(59).replace("no majority of the reporting seats: nobody is told or disconnected",
                                                   "against seat 7; disconnected")
        self.assertEqual(self.desync(relay=against)[0], 1)
        status, out = self.desync(log2=STOP)   # a game the relay put out of the race did not run on to its finish
        self.assertEqual(status, 1)
        self.assertIn("FAIL d-2: no end line 'the player left the results; stopping'", out)
        self.assertIn("FAIL d-2: its log holds 'the relay disconnected this game; stopping'", out)

    def test_desync_both_games_run_on_and_stay_different(self):
        status, out = self.desync(log2="")     # game 2 never ended its race
        self.assertEqual(status, 1)
        self.assertIn("FAIL d-2: no end line 'the player left the results; stopping'", out)
        status, out = self.desync(sums=list(range(120)))
        self.assertEqual(status, 1)
        self.assertIn("their checksums do NOT differ over 120 steps: nothing was altered", out)
        status, out = self.desync(sums=[i if i != 30 and i < 40 else i + 1000 for i in range(120)])
        self.assertEqual(status, 1)
        self.assertIn("they differ at step 30 (inputs or checksum), before the altered step 40", out)
        # equal again from step 90 on: something put the altered game back, which nothing may
        status, out = self.desync(sums=[i + 1000 if 40 <= i < 90 else i for i in range(120)])
        self.assertEqual(status, 1)
        self.assertIn("30 of the 80 steps from step 40 on have equal checksums again", out)
        os.remove(os.path.join(self.tmp.name, "port/runs/d-2/race.fzrp"))
        status, out = verdict("desync", "d", "--altered", 40)
        self.assertEqual(status, 1)
        self.assertIn("FAIL d-2: no recording (race.fzrp)", out)

    def test_quickplay_every_launcher_must_end_every_race(self):
        ok = "pb-q-{0}-1: 20261006-191326-m32.fzrp: 60 of 60 steps compared, 0 differed; rollbacks 0 (0 forced), deepest 0: PASS\n"
        log = self.write("thirty.log", "".join(ok.format(i) for i in (1, 2, 3)))
        for i in (1, 2, 3):
            self.launcher("q", i, steps=60 + i)
        status, out = verdict("quickplay", "q", "--launchers", 3, "--races", 1, "--log", log)
        self.assertEqual(status, 0, out)
        # launcher 3's game dies: its recording is cut, equal over the steps it holds, and plays back "PASS"
        self.launcher("q", 3, closed=False, steps=20)
        os.remove(os.path.join(self.tmp.name, "port/runs/q-3/race1/runner.log"))
        status, out = verdict("quickplay", "q", "--launchers", 3, "--races", 1, "--log", log)
        self.assertEqual(status, 1)
        for said in ("FAIL launcher 3: failed: the visit's time limit is over",
                     "launcher 3 (q-3), race 1 (m32): the game did not close",
                     "launcher 3 (q-3), race 1 (m32): crashed: 1 line(s)",
                     "launcher 3 (q-3), race 1 (m32): frozen:",
                     "launcher 3 (q-3), race 1 (m32): no final standings",
                     "launcher 3 recorded 20 steps of 62: cut short",
                     "the final standings from the launchers' own games are DIFFERENT or missing",
                     "verdict: FAIL | "):
            self.assertIn(said, out)

    def test_pair_reads_both_games_and_the_playbacks(self):
        ok = "pb-p-{0}: race.fzrp: 60 of 60 steps compared, 0 differed; rollbacks 0 (0 forced), deepest 0: PASS\n"
        log = self.write("pair.log", "".join(ok.format(i) for i in (1, 2, 1, 2)))
        for i in (1, 2):
            self.game_files(f"p-{i}")
            self.write(f"port/runs/p-{i}/race.fzrp", recording(60 + i))
        self.assertEqual(verdict("pair", "p", "--log", log, "--playbacks", 4)[0], 0)
        self.game_files("p-2", log=CRASH)
        self.write("port/runs/p-2/race.fzrp", recording(25, results=False))
        status, out = verdict("pair", "p", "--log", log, "--playbacks", 4)
        self.assertEqual(status, 1)
        self.assertIn("FAIL p-2: crashed", out)
        self.assertIn("p-2 recorded 25 steps of 61: cut short", out)

    def short(self, said=(3966, 3966), results=(SHORT, SHORT), twice=True):
        """Run s: the host's rule ended the race with game 2's own seat (1) still racing. `said`: the step each game's
        log names; `results`: each recording's; `twice`: the line is in both of a game's logs, as a real game has it."""
        ok = "pb-s-{0}: race.fzrp: 60 of 60 steps compared, 0 differed; rollbacks 0 (0 forced), deepest 0: PASS\n"
        log = self.write("pair.log", "".join(ok.format(i) for i in (1, 2, 1, 2)))
        for i in (1, 2):
            over = OVER.format(said[i - 1]) if said[i - 1] else ""
            self.game_files(f"s-{i}", log=over + LEFT)
            if twice:
                self.write(f"port/runs/s-{i}/stderr.txt", over)
            self.write(f"port/runs/s-{i}/race.fzrp", recording(60 + i, results=results[i - 1], seat=i - 1))
        return verdict("pair", "s", "--log", log, "--playbacks", 4, "--short", 2)

    def test_a_race_the_hosts_rule_ended_has_one_end_step_and_a_seat_short_of_the_line(self):
        status, out = self.short()
        self.assertEqual(status, 0, out)
        self.assertIn("the race's end: before step 3966 in every game, by the host's rule; seat 1 (game 2's own) short "
                      "of the line in all 2 recordings (not finished, not out)", out)
        # without --short nothing of it is asked: the row's judge of before
        self.assertEqual(verdict("pair", "s", "--playbacks", 0)[0], 0)

    def test_two_games_that_ended_the_race_before_different_steps_fail(self):
        status, out = self.short(said=(3966, 3967))
        self.assertEqual(status, 1)
        self.assertIn("FAIL the race's end: the games ended the race before different steps (3966, 3967)", out)
        # a game that never said it, and one that said it for two steps (the race ended twice)
        status, out = self.short(said=(3966, 0))
        self.assertEqual(status, 1)
        self.assertIn("FAIL s-2: its log says 'the race is over before step N' for 0 steps (none): one is expected", out)
        status, out = self.short()
        self.write("port/runs/s-1/stderr.txt", OVER.format(3966) + OVER.format(4100))
        status, out = verdict("pair", "s", "--short", 2)
        self.assertEqual(status, 1)
        self.assertIn("FAIL s-1: its log says 'the race is over before step N' for 2 steps (3966, 4100)", out)

    def test_a_seat_that_finished_or_went_out_is_not_short_of_the_line(self):
        def with_seat_1(**state):
            rows = [dict(r) for r in SHORT["results"]]
            rows[1].update(state)
            return {"results": rows}
        for state, word in ((dict(finished=True, timeMs=52008), "finished"), (dict(out=True), "out")):
            results = with_seat_1(**state)
            status, out = self.short(results=(results, results))
            self.assertEqual(status, 1, state)
            self.assertIn(f"FAIL s-1: its recording has seat 1 (game 2's own) {word}: the host's rule was to end the race "
                          "with that seat still racing (finished false, out false)", out)
            self.assertIn(f"FAIL s-2: its recording has seat 1 (game 2's own) {word}", out)
        # results that do not name the seat, and none at all (a recording cut short fails as it always did, too)
        status, out = self.short(results=({"results": SHORT["results"][:1]},) * 2)
        self.assertEqual(status, 1)
        self.assertIn("FAIL s-1: its recording's results hold 0 entries for seat 1 (game 2's own)", out)
        status, out = self.short(results=(SHORT, True))
        self.assertEqual(status, 1)
        self.assertIn("FAIL s-2: its recording's results hold 0 entries for seat 1", out)
        self.assertIn("the recordings (61, 62 steps) hold OTHER results", out)

    def test_a_difference_the_relay_found_fails_a_race_also_when_it_only_observed(self):
        ok = "pb-{0}-{1}: race.fzrp: 60 of 60 steps compared, 0 differed; rollbacks 0 (0 forced), deepest 0: PASS\n"
        for i in (1, 2):
            self.game_files(f"p-{i}")
            self.write(f"port/runs/p-{i}/race.fzrp", recording(60))
            self.launcher("q", i)
        pair = self.write("pair.log", "".join(ok.format("p", i) for i in (1, 2, 1, 2)))
        quick = self.write("quickplay.log", "".join(ok.format("q", f"{i}-1").replace("race.fzrp", "20261006-191326-m32.fzrp")
                                                  for i in (1, 2)))
        rows = (("pair", ["p", "--log", pair, "--playbacks", 4], "port/scratch/pair/p.server.log"),
                ("quickplay", ["q", "--launchers", 2, "--races", 1, "--log", quick], "port/scratch/qp/q.server.log"))
        for kind, args, server in rows:
            self.write(server, "19:05:17 race m32: go (30 player seats)\n")
            self.assertEqual(verdict(kind, *args)[0], 0, kind)
            for line in ("race m32: seat 28 desynced at frame 1559; disconnected, the AI drives it",          # disconnect
                         "race m32: desync, checksums differ at frame 1559: seat 3 = 0000000A, seat 7 = 0000000B; "
                         "no majority of the reporting seats: nobody is told or disconnected",
                         "race m32: desync, checksums differ at frame 1559: seats 3 4 = 0000000A, seat 7 = 0000000B; "
                         "against seat 7; observing: nobody is told or disconnected"):                      # the default
                self.write(server, f"19:05:17 race m32: go (30 player seats)\n19:05:18 {line}\n")
                status, out = verdict(kind, *args)
                self.assertEqual(status, 1, (kind, line))
                self.assertIn("FAIL the relay: 19:05:18 race m32: ", out)


if __name__ == "__main__":
    unittest.main()
