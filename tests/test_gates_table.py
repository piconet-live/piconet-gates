"""gates.sh --judge-only on a made-up batch: the table, its tally and its exit status.
Run by scripts/check.sh: python3 -m unittest discover -s port/gates/tests."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from judge_fixtures import HERE, LEFT, OBSERVED, OVER, PACE, PLAYED, SHORT, Work, probe, recording

sys.path.insert(0, os.path.join(HERE, "..", "..", "setup"))
import parts  # noqa: E402  the service's checkout (port/setup/pins.tsv), where app.sh's APP_BUILD builds

# what port/setup/app.sh's APP_BUILD builds, as it names it: the service's solution in its checkout
SERVICE_SOLUTION = os.path.relpath(parts.path_in("REPO_SERVICE", "net/net.slnx"), parts.ROOT).replace(os.sep, "/")

ROWS_PASSING = ("checks batch match roundtrip offline pieces fork forced control crash pair desync quickplay "
                "thirty").split()
ROWS_MANUAL = "start roundtrip-jit mixed failures service movie timing".split()


class TheWholeTable(Work, unittest.TestCase):
    """gates.sh --judge-only on a whole made-up batch in which every row passes, and on that batch with one thing
    wrong: the tally and the exit status. (With ONLY the table is "NOT COMPLETE" whatever the code does.)"""

    T = "tagall"

    def log(self, row, *statuses, said=""):
        """The row's log as gates.sh writes it: one command for each status."""
        text = "".join(f"$ command {k}\n{said if k == 1 else ''}[gates] step {k} status {status}\n"
                       for k, status in enumerate(statuses, 1))
        return self.write(f"port/scratch/gates/{self.T}/{row}.log", text)

    def visit(self, run, i, matches):
        """A launcher's visit of several races (launcher() makes one of one race)."""
        door, folder = [], f"port/runs/{run}-{i}"
        for k, match in enumerate(matches, 1):
            door += [{"event": "match", "values": {"match": match}},
                     {"event": "game", "values": {"state": "closed", "match": match, "standings": ["1:finished:100"]}}]
            self.write(f"{folder}/race{k}/runner.log", "fzgx: go\n" + LEFT)
            self.write(f"{folder}/race{k}/probe.csv", probe([16_683] * 300))
            self.write(f"{folder}/race{k}/pace.csv", PACE)
            self.write(f"{folder}/replays/20261006-19132{k}-{match}.fzrp", recording(60))
        self.write(f"{folder}/door.jsonl", "".join(json.dumps(e) + "\n" for e in door))

    def batch(self):
        T, shutdown = self.T, "[staticrecomp] shutdown: native=1 fallback=0 smc_failed=1 verifications=3\n"
        self.log("checks", 0, said="check: port core tests\n555 checks, 0 failed\ncheck: ok\n")
        self.log("batch", 0)
        self.write(f"port/scratch/rp/gbatch-{T}.gates.txt", "pair: EXACT by 2 gate(s)\n" * 6 + "  PASS gate\n" * 30)
        for run in ("dual-core-race300-on-1", "single-core-race300-on-1"):
            self.game_files(f"{T}-{run}")
        self.game_files(f"{T}-match")
        self.write(f"port/runs/{T}-match/stderr.txt", shutdown)
        self.write(f"port/runs/{T}-match/race.fzrp", recording(60))
        self.log("match", 0, 0)
        self.log("start", 0)
        self.log("roundtrip", 0, said=PLAYED.format(f"{T}-rtr-1", "race.fzrp"))
        self.game_files(f"{T}-offline", log="")
        self.write(f"port/runs/{T}-offline/stderr.txt", shutdown)
        self.write(f"port/runs/{T}-offline/end.txt", f"{T}-offline: game and launcher exited 1.94s after the stop command; 5465 fields\n")
        self.log("offline", 0, 0, said="  race: 587 fields from field 4613, race frame up to 587; per field mean 16.683 ms, max 17.0 ms, over 24 ms: 0; measured before field 5200\n")
        self.log("fork", 0, said=PLAYED.format(f"{T}-fork-1", "a.fzrp"))
        self.log("forced", 0, 0, 0, 0, 0, 0, said="".join(PLAYED.format(f"{T}-f{k}-1", "a.fzrp") for k in range(1, 7)))
        self.log("control", 1, said=f"{T}-ctl-1: m22.fzrp: 9000 of 9418 steps compared, 44 differed; rollbacks 9 (9 forced), deepest 3: FAIL\n")
        self.game_files(f"{T}-crash-1", log="fzgx: undo log: guard on at its step 121: 4300 pages write-protected\n"
                        "fzgx: undo log check: 7400 steps compared with every page: the log the same at every step\n" + LEFT)
        self.log("crash", 0, said=PLAYED.format(f"{T}-crash-1", "20261006-w4b-1.fzrp"))
        for i in (1, 2):
            # (row pair's race is ended by the host's rule with game 2's seat short of the line: its judge asks for
            # the end's line in both logs and for that seat in both recordings' results)
            self.game_files(f"{T}-pair-{i}", log=OVER.format(3966) + LEFT)
            self.write(f"port/runs/{T}-pair-{i}/race.fzrp", recording(60, results=SHORT, seat=i - 1))
            self.game_files(f"{T}-alter-{i}")
            self.write(f"port/runs/{T}-alter-{i}/race.fzrp",
                       recording(1700, sums=[t if t < 1500 or i == 1 else t + 9000 for t in range(1700)]))
            self.visit(f"{T}-qp", i, ("m8", "m14"))
        self.log("pair", 0, 0, 0, said="".join(PLAYED.format(f"pb-{T}-pair-{i}", "race.fzrp") for i in (1, 2, 1, 2)))
        self.write(f"port/scratch/pair/{T}-alter.server.log", OBSERVED.format(1559))
        self.log("desync", 0, 1)
        self.log("quickplay", 0, 0, 0, said="".join(PLAYED.format(f"pb-{T}-qp-{i}-{k}", "x.fzrp") for i in (1, 2) for k in (1, 2)))
        for i in (1, 2, 3):
            self.launcher(f"{T}-q30", i)
        self.log("thirty", 0, 0, 0, said="".join(PLAYED.format(f"pb-{T}-q30-{i}-1", "x.fzrp") for i in (1, 2, 3)))
        self.write(f"port/scratch/gates/{T}/pieces.judge.log", "verdict: pass | (the batch's own)\n")   # the row ran

    def table(self):
        env = dict(os.environ, PORT_WORK=self.tmp.name, TAG=self.T, JUDGE_OUT=os.path.join(self.tmp.name, "judge"))
        env.pop("ONLY", None)
        env.pop("MIXED", None)
        done = subprocess.run(["bash", os.path.join(HERE, "..", "gates.sh"), "n7", "--judge-only"], env=env,
                              capture_output=True, text=True, timeout=120)
        rows = {line[2:].split(":")[0]: line.split(" | ")[1:] for line in done.stdout.splitlines() if line.startswith("| ")}
        return done.returncode, rows, done.stdout + done.stderr

    def tally(self, out):
        return [line for line in out.splitlines() if " pass, " in line and " FAIL, " in line][-1]

    def test_the_times_a_batch_kept_are_in_the_table_and_the_whole_pass(self):
        self.batch()
        self.write(f"port/scratch/gates/{self.T}/times.tsv", "checks\t5\t287\nbatch\t3.5\t192\nfork\t1\t231\nstart\t0\t\nall\t\t1680\n")
        status, rows, out = self.table()
        self.assertEqual((rows["checks"][2], rows["checks"][3]), ("5 min", "4:47 |"))
        self.assertEqual((rows["batch"][2], rows["batch"][3]), ("3.5 min", "3:12 |"))
        self.assertEqual(rows["pair"][2:], ["3 min", " |"])               # a row the file says nothing of: no time taken
        self.assertIn("\nthe whole pass took 28:00 (a release pass is to take 30 minutes at most; rows that ran side by "
                      "side each say the time of their set)\n", out)
        self.assertEqual(status, 0)

    def test_checks_that_read_the_landings_pass_say_so_and_still_built_the_test_server(self):
        self.batch()
        said = ("gates: the full check passed at the landing of these files (tree 1a2b3c4d, recorded 2026-10-11 as commit "
                "abc1234): not run again\n")
        self.log("checks", 0, said=said)
        status, rows, out = self.table()
        self.assertEqual(rows["checks"][0], "pass", out)
        self.assertEqual(rows["checks"][1], "the full check passed at the landing of these files (tree 1a2b3c4d, recorded "
                         "2026-10-11 as commit abc1234): not run again; built here: the test server and the simulated "
                         f"players (dotnet build {SERVICE_SOLUTION})")
        self.log("checks", 1, said=said + "Program.cs(1,1): error CS1002: ; expected\n")   # the build failed: no pass
        status, rows, out = self.table()
        self.assertEqual(rows["checks"][0], "FAIL", out)
        self.assertIn("the build ended with status 1: Program.cs(1,1): error CS1002", rows["checks"][1])
        self.assertNotEqual(status, 0)

    def test_every_row_passing_is_complete_and_status_0(self):
        self.batch()
        status, rows, out = self.table()
        for row in ROWS_PASSING:
            self.assertEqual(rows[row][0], "pass", (row, rows[row], out))
        for row in ROWS_MANUAL:
            self.assertEqual(rows[row][0], "manual", row)
        self.assertEqual(len(rows) - 1, len(ROWS_PASSING) + len(ROWS_MANUAL))   # (less the header)
        self.assertEqual(self.tally(out), f"{len(ROWS_PASSING)} pass, 0 FAIL, 0 did not finish, {len(ROWS_MANUAL)} manual, 0 not run: COMPLETE")
        self.assertEqual(status, 0)

    def test_row_mixed_is_judged_when_its_batch_ran_it(self):
        # (manual in a batch that did not, as every test of the whole table here shows)
        self.batch()
        self.mixed_race(f"{self.T}-mixa")
        self.mixed_race(f"{self.T}-mixb", modules=(self.NEW, self.OLD))
        self.log("mixed", 0, 0)
        status, rows, out = self.table()
        self.assertEqual(rows["mixed"][0], "pass", out)
        self.assertIn("game 2 (launcher-new: 11111111/bbbbbbbb/22222222): lag 90 ms", rows["mixed"][1])
        self.assertEqual(status, 0)
        # the swapped race differs from step 40 on: the row fails and names the step and both games' builds
        self.mixed_race(f"{self.T}-mixb", modules=(self.NEW, self.OLD), sums2=[i if i < 40 else i + 1000 for i in range(60)])
        status, rows, out = self.table()
        self.assertEqual(rows["mixed"][0], "FAIL", out)
        self.assertIn("game 1 (launcher-new: 11111111/bbbbbbbb/22222222) and game 2 (launcher-old: 11111111/aaaaaaaa/"
                      "22222222) differ first at step 40", rows["mixed"][1])
        self.assertNotEqual(status, 0)

    def test_one_playback_cut_short_is_not_a_pass_and_the_batch_is_not_complete(self):
        self.batch()
        self.log("fork", 4, said=f"{self.T}-fork-1: a.fzrp: did not finish: 2999 of 5873 steps (no summary line): DID NOT FINISH\n")
        status, rows, out = self.table()
        self.assertEqual(rows["fork"][0], "did not finish")
        self.assertEqual(self.tally(out), f"{len(ROWS_PASSING) - 1} pass, 0 FAIL, 1 did not finish, {len(ROWS_MANUAL)} manual, 0 not run: NOT COMPLETE")
        self.assertNotEqual(status, 0)

    def test_one_row_not_run_is_not_complete(self):
        self.batch()
        self.log("pair", 75, 1, 0, said="timing-lock: the machine is still taken after 40 minutes\n")
        status, rows, out = self.table()
        self.assertEqual(rows["pair"][0], "not run")
        self.assertEqual(self.tally(out), f"{len(ROWS_PASSING) - 1} pass, 0 FAIL, 0 did not finish, {len(ROWS_MANUAL)} manual, 1 not run: NOT COMPLETE")
        self.assertNotEqual(status, 0)

    def test_a_command_that_failed_fails_its_row_though_the_judge_passes(self):
        self.batch()
        self.log("match", 0, 1)                 # run-summary.py: the steps were not equal
        status, rows, out = self.table()
        self.assertEqual(rows["match"][0], "FAIL")
        self.assertIn("a command of the row ended with status 1", rows["match"][1])
        self.assertIn(f"{len(ROWS_PASSING) - 1} pass, 1 FAIL, ", self.tally(out))
        self.assertNotEqual(status, 0)

    def test_the_crash_row_reads_its_playbacks_screen_copies(self):
        wrong = "F,1,10,0,2,36,3944\n" + "E,1,5,1,0,0,0,128,128,5,01235fa0\n" * 3 + "E,1,5,1,0,0,0,640,448,5,01235fa0\n"
        for pace, said in ((wrong, "screen copies of two sizes to one destination: 01235fa0 (usually 128x128) got 640x448"),
                           (None, "no pacing log with a screen copy (pace.csv)")):
            self.batch()
            path = self.write(f"port/runs/{self.T}-crash-1/pace.csv", pace or "")
            if pace is None:
                os.remove(path)
            status, rows, out = self.table()
            self.assertEqual(rows["crash"][0], "FAIL", out)
            self.assertIn(said, rows["crash"][1])
            self.assertNotEqual(status, 0)

    def test_the_crash_row_reads_the_undo_logs_check(self):
        for log, said in (("fzgx: undo log check: 7400 steps compared with every page: the log different at 2 steps\n",
                           "the guard never went on"),
                          ("fzgx: undo log: guard on at its step 121\n"
                           "fzgx: undo log check: 7400 steps compared with every page: the log different at 2 steps\n",
                           "the log different at 2 steps")):
            self.batch()
            self.game_files(f"{self.T}-crash-1", log=log + LEFT)
            status, rows, out = self.table()
            self.assertEqual(rows["crash"][0], "FAIL", out)
            self.assertIn(said, rows["crash"][1])
            self.assertNotEqual(status, 0)

    def test_a_row_the_batch_has_no_log_of_was_not_run(self):
        self.batch()                            # a batch made with ONLY: nothing of rows fork, match, offline
        for name in ("fork.log", "match.log", "offline.log", "start.log", "roundtrip.log", "pieces.judge.log"):
            os.remove(os.path.join(self.tmp.name, f"port/scratch/gates/{self.T}/{name}"))
        status, rows, out = self.table()
        for row in ("fork", "match", "offline", "start", "roundtrip", "pieces"):
            self.assertEqual(rows[row][0], "not run", (row, rows[row]))
        self.assertIn("has no log of this row", rows["fork"][1])
        self.assertIn(" 0 FAIL, ", self.tally(out))
        self.assertNotEqual(status, 0)

    def test_roundtrip_and_pieces_of_a_batch_that_never_ran_them_are_not_run(self):
        # a batch made with ONLY="match offline": both rows' inputs are there, the two rows themselves never ran
        self.batch()
        folder = os.path.join(self.tmp.name, f"port/scratch/gates/{self.T}")
        os.remove(os.path.join(folder, "roundtrip.log"))
        os.remove(os.path.join(folder, "pieces.judge.log"))
        status, rows, out = self.table()
        self.assertEqual((rows["roundtrip"][0], rows["pieces"][0]), ("not run", "not run"), out)
        self.assertEqual((rows["match"][0], rows["offline"][0]), ("pass", "pass"))
        self.assertIn(" 0 FAIL, ", self.tally(out))
        # a batch that ran them: roundtrip with no recording from row match is a FAIL (it called no command), and
        # pieces of a run that left no log is one too
        self.batch()
        os.remove(os.path.join(folder, "roundtrip.log"))
        self.write(f"port/scratch/gates/{self.T}/roundtrip.judge.log", "verdict: FAIL | (the batch's own)\n")
        os.remove(os.path.join(self.tmp.name, f"port/runs/{self.T}-match/race.fzrp"))
        os.remove(os.path.join(self.tmp.name, f"port/runs/{self.T}-offline/stderr.txt"))
        os.remove(os.path.join(self.tmp.name, f"port/runs/{self.T}-offline/fzgx.log"))
        status, rows, out = self.table()
        self.assertEqual((rows["roundtrip"][0], rows["pieces"][0]), ("FAIL", "FAIL"), out)
        self.assertIn("no recording: row match did not leave one", rows["roundtrip"][1])

    def test_the_match_rows_game_must_have_left_its_probe_and_its_pacing_log(self):
        for name, said in (("pace.csv", "no pacing log (pace.csv)"), ("probe.csv", "no probe (probe.csv")):
            self.batch()
            os.remove(os.path.join(self.tmp.name, f"port/runs/{self.T}-match/{name}"))
            status, rows, out = self.table()
            self.assertEqual(rows["match"][0], "FAIL", out)
            self.assertIn(said, rows["match"][1])
            self.assertNotEqual(status, 0)

    def test_a_first_command_that_never_ran_does_not_hide_a_later_one_that_failed(self):
        five = "".join(PLAYED.format(f"{self.T}-f{k}-1", "a.fzrp") for k in range(2, 7))
        waited = f"{self.T}-f1-1: the busy check said wait for 20 minutes; not run\n"
        self.batch()
        self.log("forced", 3, 0, 0, 0, 0, 0, said=waited + five)
        self.assertEqual(self.table()[1]["forced"][0], "not run")
        failed = five.replace(f"{self.T}-f4-1: a.fzrp: 60 of 60 steps compared, 0 differed", f"{self.T}-f4-1: a.fzrp: 60 of 60 steps compared, 7 differed").replace("deepest 0: PASS\n", "deepest 0: FAIL\n", 3).replace("FAIL", "PASS", 2)
        self.assertEqual(failed.count("FAIL"), 1)
        self.log("forced", 3, 0, 0, 1, 0, 0, said=waited + failed)
        status, rows, out = self.table()
        self.assertEqual(rows["forced"][0], "FAIL")
        self.assertIn("a later command of the row ran and failed", rows["forced"][1])
        self.assertNotEqual(status, 0)


class TheTable(unittest.TestCase):
    """gates.sh --judge-only on a made-up batch: what a row reads when its first command never got the machine."""

    def table(self, first_status, said):
        with tempfile.TemporaryDirectory() as work:
            out = os.path.join(work, "port", "scratch", "gates", "tag75")
            os.makedirs(out)
            with open(os.path.join(out, "pair.log"), "w") as f:
                f.write("$ CLOCKRATE=1.0 port/gates/runs/pair-run.sh tag75-pair\n" + said + "\n"
                        f"[gates] step 1 status {first_status}\n"
                        "$ port/gates/replay-compare.py a b\nno such file\n[gates] step 2 status 1\n"
                        "$ port/gates/reports/pair-report.py tag75-pair\n[gates] step 3 status 0\n")
            env = dict(os.environ, PORT_WORK=work, TAG="tag75", ONLY="pair", JUDGE_OUT=os.path.join(work, "judge"))
            done = subprocess.run(["bash", os.path.join(HERE, "..", "gates.sh"), "n7", "--judge-only"], env=env,
                                  capture_output=True, text=True, timeout=120)
            row = [line for line in done.stdout.splitlines() if line.startswith("| pair:")]
            self.assertEqual(len(row), 1, done.stdout + done.stderr)
            return row[0], done.stdout

    def test_a_row_that_never_got_the_machine_is_not_run(self):
        # 75: the lock wait gave up (timing-lock.sh); 3: the busy check or the machine never free
        for status, said in ((75, "timing-lock: the machine is still taken after 40 minutes"),
                             (3, "tag75-pair: the machine was not free in 20 minutes:")):
            row, out = self.table(status, said)
            self.assertIn("| not run |", row)
            self.assertIn(f"(status {status}): {said}", row)
            self.assertIn("0 FAIL", out)
            self.assertIn("NOT COMPLETE", out)

    def test_a_row_whose_game_failed_is_still_a_fail(self):
        row, out = self.table(1, "tag75-pair-1: GONE: the game's process ended 40 s after the start")
        self.assertIn("| FAIL |", row)
        self.assertIn("1 FAIL", out)


if __name__ == "__main__":
    unittest.main()
