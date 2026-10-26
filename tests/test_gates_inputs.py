"""gates.sh on a made-up work folder in which no game can start: which staged copy it gates, and what a row reads
when an input of its own is not there. gate-native.sh and time-native.sh with a stand-in for the harness: the machine
file they hand it. No game, no harness, no Windows program. Run by scripts/check.sh."""
import os
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..")
MACHINE = 'schema = 1\nwork = "/w"\nrunner = "ModernGekko/build/moderngekko-run.exe"\ngame = "port/game-native"\n'
# the stand-in harness: one line for each call, with the machine file it was given
HARNESS = ('import os, sys\nwith open(os.environ["PORT_WORK"] + "/harness.log", "a") as f:\n'
           '    f.write(os.environ.get("RECOMP_MACHINE", "-") + " " + " ".join(sys.argv[1:]) + "\\n")\n')


class Work(unittest.TestCase):
    """A made-up work folder. staged(): the parts under test, in a launcher folder and where the harness looks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = self.tmp.name
        # (the locks' folder too: nothing here may reach the PC's shared one, whatever a test gets wrong)
        self.env = dict(os.environ, PORT_WORK=self.work, PORT_WORK_WIN="C:\\w", PORT_LOCKS=self.work, TAG="tagin",
                        BUSY_CHECK=self.write("chk.sh", "#!/bin/bash\necho none\n", 0o755),
                        RECOMP_KIT=os.path.join(self.work, "kit"))
        # (PROGRESS_RUN: a pass here is no step of the run this test is run in; its own progress files go where its
        # locks are, in the made-up work folder)
        for name in ("ONLY", "MACHINE", "MIXED", "LAUNCHER", "BUNDLE", "GAME", "JUDGE_OUT", "PROGRESS_RUN", "PROGRESS_DIR"):
            self.env.pop(name, None)
        from judge_fixtures import windows
        self.env["PATH"] = windows(self.work) + os.pathsep + os.environ["PATH"]   # no row here asks Windows
        self.write("kit/tools/harness/recomp.py", HARNESS)

    def write(self, path, content="x", mode=0o644):
        path = os.path.join(self.work, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        os.chmod(path, mode)
        return path

    def staged(self, launcher="launcher-dev", runner="the runner"):
        self.write("work/mod-cg-n7/gGFZE01_recomp.dll", "the module")
        self.write(f"port/{launcher}/Launcher.App.exe")
        self.write(f"port/{launcher}/recomp/moderngekko-run.exe", runner)
        self.write(f"port/{launcher}/recomp/gGFZE01_recomp.dll", "the module")
        for name in ("mod.bin", "patches.json"):
            self.write(f"port/{launcher}/recomp/fzgx/{name}", "the image")
        self.write(f"port/{launcher}/recomp/fzgx/manifest.json", '{"image_sha1": "aa"}')
        self.write(f"port/{launcher}/recomp/game/sys/main.dol")
        self.write("kit-win/launch.ps1")
        self.write("port/user-pristine/GC/card.raw")
        self.write("port/machine-n.toml", MACHINE)
        self.write("port/machine-gate-n.toml", MACHINE.replace("port/game-native", "extracted/GFZE01"))

    def gates(self, *args, only="", **more):
        env = dict(self.env, **more, **({"ONLY": only} if only else {}))
        done = subprocess.run(["bash", os.path.join(SCRIPTS, "gates.sh"), "n7", *args], env=env, capture_output=True,
                              text=True, timeout=120)
        rows = {line[2:].split(":")[0]: line.split(" | ")[1:] for line in done.stdout.splitlines() if line.startswith("| ")}
        return done.returncode, rows, done.stdout + done.stderr

    def started(self):
        """The rows that started a command: each has a log."""
        folder = os.path.join(self.work, "port/scratch/gates/tagin")
        return sorted(n[:-4] for n in os.listdir(folder) if n.endswith(".log") and not n.endswith(".judge.log"))


class ARunOfItsOwn(Work):
    """A pass in this made-up work folder is no step of the run the test is run in (a full check is one, and says so
    in PROGRESS_RUN): it reports where its own lock files are."""

    def setUp(self):
        self.outer = tempfile.TemporaryDirectory()
        self.addCleanup(self.outer.cleanup)
        self.events = os.path.join(self.outer.name, "check-outer-20261012-000000.events")
        with open(self.events, "w") as f:
            f.write('1.0\tbegin\t{"run": "check-outer-20261012-000000", "kind": "check", "title": "A check", "agent": "outer", "pid": null, '
                    '"parent": null, "plan": [], "lanes": false, "whole": null, "again": null}\n')
        inherited = mock.patch.dict(os.environ, {"PROGRESS_RUN": self.events[:-7] + ".json", "PROGRESS_DIR": self.outer.name})
        inherited.start()
        self.addCleanup(inherited.stop)
        super().setUp()

    def test_a_pass_says_nothing_into_an_inherited_run_and_keeps_its_file_in_its_own_folder(self):
        self.gates(only="fork offline start")
        with open(self.events) as f:
            self.assertEqual(len(f.read().splitlines()), 1)                    # the outer run's file is as it was
        self.assertEqual(os.listdir(self.outer.name), [os.path.basename(self.events)])
        if not os.path.exists(os.path.join(SCRIPTS, "..", "..", "scripts", "progress.sh")):
            return   # a runner without the progress files (scripts/progress.sh) keeps none: gates-table.sh progress_rows
        own = [n for n in os.listdir(os.path.join(self.work, "progress")) if n.endswith(".json") and n.startswith("gates-")]
        self.assertEqual(len(own), 1)


class TheKeptPlaybacks(Work):
    """Rows fork, forced and control for real, with a stand-in harness that plays nothing: one call of
    replay-check.sh, three playbacks side by side, and each row's own log and verdict from it."""

    def setUp(self):
        super().setUp()
        from judge_fixtures import recording
        from test_replay_check import HARNESS as PLAYS
        self.staged()
        self.write("kit/tools/harness/recomp.py", PLAYS)
        self.write("port/machine-n.toml", MACHINE + 'user = "port/user"\nuser_pristine = "port/user-pristine"\n'
                                                    'config = "port/user/Config/Dolphin.ini"\n')   # as the real one
        os.makedirs(os.path.join(self.work, "port/launch"))
        for path in ("port/replays-test/20261004-155342-m32-hr.fzrp", "port/replays-test/20261004-014343-m32-P1.fzrp",
                     "port/runs/rm1/race.fzrp", "port/runs/qs0-1/replays/20261006-101707-m22.fzrp"):
            target = os.path.join(self.work, path)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "wb") as f:
                f.write(recording(100))
        self.write("plan/tagin-ctl-1", "differs")                         # the control's playback must differ

    def ran(self):
        import json
        with open(os.path.join(self.work, "harness.log")) as f:
            return [json.loads(line) for line in f]

    def log_of(self, row):
        with open(os.path.join(self.work, f"port/scratch/gates/tagin/{row}.log")) as f:
            return f.read()

    def test_one_set_call_three_at_a_time_and_each_row_judged_from_its_own_lines(self):
        status, rows, out = self.gates(only="fork forced control")
        self.assertEqual([rows[r][0] for r in ("fork", "forced", "control")], ["pass"] * 3, out)
        ran = self.ran()
        # the longest first, under the names the rows have always given them, three at a time
        self.assertEqual(sorted(r["run"] for r in sorted(ran, key=lambda r: r["began"])[:3]),
                         ["tagin-ctl-1", "tagin-f4-1", "tagin-f5-1"])
        self.assertEqual(sorted(r["run"] for r in ran),
                         sorted(["tagin-ctl-1", "tagin-fork-1"] + [f"tagin-f{k}-1" for k in range(1, 7)]))
        self.assertEqual({r["agent"] for r in ran}, {"port-pb1", "port-pb2", "port-pb3"})
        self.assertEqual(self.started(), ["control", "forced", "fork", "kept"])
        fork = self.log_of("fork").splitlines()
        self.assertTrue(fork[0].startswith("$ rows control forced fork, 3 playbacks side by side; this row's lines "
                                           "of: AT_ONCE=3 NAMES=\"tagin-ctl-1 tagin-f5-1 "), fork[0])
        self.assertEqual((len(fork), fork[1].split(":")[0], fork[2]), (3, "tagin-fork-1", "[gates] step 1 status 0"))
        forced = self.log_of("forced")
        self.assertEqual(sorted(line.split(":")[0] for line in forced.splitlines()[1:-1]), [f"tagin-f{k}-1" for k in range(1, 7)])
        self.assertTrue(forced.endswith("[gates] step 1 status 0\n"))
        self.assertTrue(self.log_of("control").endswith(": FAIL\n[gates] step 1 status 1\n"))   # as it must
        # the table: what each row was given and took, and whom it ran with; the whole pass's time
        self.assertEqual(rows["fork"][2], "1 min")
        self.assertRegex(rows["forced"][3], r"^0:\d\d \(with control fork\) \|$")
        self.assertRegex(out, r"(?m)^the whole pass took 0:\d\d \(a release pass is to take 30 minutes at most")

    def test_the_tables_count_of_playbacks_side_by_side(self):
        # AT_ONCE=2: sets of two (on the final build two slow each other by a fifth at most, three by up to a half)
        status, rows, out = self.gates(only="fork forced control", AT_ONCE="2")
        self.assertEqual([rows[r][0] for r in ("fork", "forced", "control")], ["pass"] * 3, out)
        self.assertEqual({r["agent"] for r in self.ran()}, {"port-pb1", "port-pb2"})
        self.assertIn("$ rows control forced fork, 2 playbacks side by side; this row's lines of: AT_ONCE=2 NAMES=",
                      self.log_of("fork"))
        status, rows, out = self.gates(only="fork", AT_ONCE="none")
        self.assertEqual((status, out), (2, "gates: AT_ONCE is a count of playbacks side by side (3)\n"))

    def test_a_playback_that_did_not_finish_beside_the_others_is_played_again_and_the_row_says_so(self):
        self.write("plan/tagin-f2-1", "cut once")
        self.write("plan/tagin-f3-1", "cut")
        status, rows, out = self.gates(only="fork forced control")
        self.assertEqual((rows["fork"][0], rows["forced"][0], rows["control"][0]), ("pass", "did not finish", "pass"), out)
        forced = self.log_of("forced")
        self.assertIn("tagin-f2-1: it did not finish beside the others of its set (50 of 100 steps (no summary line "
                      "within the limit of 178 s)): played again, alone\n", forced)
        self.assertRegex(forced, r"(?m)^tagin-f2-1: .*: PASS$")
        self.assertRegex(forced, r"(?m)^tagin-f3-1: .*: DID NOT FINISH$")
        self.assertTrue(forced.endswith("[gates] step 1 status 4\n"))
        self.assertTrue(self.log_of("fork").endswith("[gates] step 1 status 0\n"))   # another row's is not this row's

    def test_a_row_that_differs_fails_alone(self):
        self.write("plan/tagin-fork-1", "differs")
        status, rows, out = self.gates(only="fork forced control")
        self.assertEqual((rows["fork"][0], rows["forced"][0], rows["control"][0]), ("FAIL", "pass", "pass"), out)
        self.assertNotEqual(status, 0)


class ARowsOwnInputs(Work):
    def test_a_row_whose_input_is_missing_is_not_run_and_the_others_run(self):
        self.staged()
        self.write("port/runs/tagin-match/pace.csv", "F,1,10,0,2,36,5\n")   # what row start reads: row match's
        status, rows, out = self.gates(only="start roundtrip control")
        self.assertEqual(rows["start"][0], "manual", out)                    # its input is there: it ran
        self.assertEqual(rows["roundtrip"][0], "not run: needs row match's recording in this batch", out)
        self.assertIn(f"no {self.work}/port/runs/tagin-match/race.fzrp", rows["roundtrip"][1])
        # every part under test is there: the row names only the recording it plays back
        self.assertEqual(rows["control"][0], "not run: needs the recording of run qs0 (port/setup/kept.tsv)", out)
        self.assertEqual(self.started(), ["start"])
        self.assertIn("0 pass, 0 FAIL, 0 did not finish, 1 manual, 20 not run: NOT COMPLETE", out)
        self.assertNotEqual(status, 0)

    def test_row_mixed_is_manual_without_a_second_build_and_needs_its_staged_launcher(self):
        self.staged()
        status, rows, out = self.gates(only="mixed")
        self.assertEqual(rows["mixed"][0], "manual", out)
        self.assertIn("MIXED=<its launcher folder> ONLY=mixed port/gates/gates.sh n7 --launcher launcher-dev", rows["mixed"][1])
        status, rows, out = self.gates(only="mixed", MIXED="launcher-other")
        self.assertTrue(rows["mixed"][0].startswith("not run: needs "), out)
        self.assertIn("the other build's staged launcher (MIXED=NAME)", rows["mixed"][0])
        self.assertIn(f"no {self.work}/port/launcher-other/Launcher.App.exe", rows["mixed"][1])
        self.assertEqual(self.started(), [])
        # a dry run with one prints the two races, the roles swapped
        status, rows, out = self.gates("--dry-run", only="mixed", MIXED="launcher-other")
        self.assertIn("port/gates/runs/mixed-run.sh tagin-mixa launcher-other launcher-dev", out)
        self.assertIn("port/gates/runs/mixed-run.sh tagin-mixb launcher-dev launcher-other", out)
        self.assertIn("port/gates/gate-judge.py mixed tagin-mixa tagin-mixb --log", out)

    def test_an_empty_work_folder_starts_nothing_and_names_what_each_row_needs(self):
        status, rows, out = self.gates(only="fork offline start")
        for part in ("the runner under test", "module n7", "the native bundle", "the game folder", "the fork recording"):
            self.assertIn(part, rows["fork"][0], out)
        self.assertNotIn("launcher", rows["fork"][0])                        # a playback needs no launcher folder
        self.assertIn("the staged launcher launcher-dev", rows["offline"][0])
        self.assertNotIn("recording", rows["offline"][0])
        self.assertEqual(rows["start"][0], "not run: needs row match's pacing log in this batch")
        self.assertEqual(rows["pair"][0], "not run")                         # not asked for
        self.assertEqual(self.started(), [])
        self.assertIn("0 FAIL", out)
        self.assertNotEqual(status, 0)

    def test_a_judge_only_run_uses_no_input(self):
        self.write("port/scratch/gates/tagin/start.log", "$ command 1\n[gates] step 1 status 0\n")
        status, rows, out = self.gates("--judge-only", only="start", JUDGE_OUT=os.path.join(self.work, "judge"))
        self.assertEqual(rows["start"][0], "manual", out)


class TheStagedCopy(Work):
    def test_the_launcher_folder_named_gives_every_row_its_runner(self):
        self.staged("launcher-mine")
        status, rows, out = self.gates("--launcher", "launcher-mine", only="start")   # (a row that starts no game)
        for name, game in (("machine.toml", "port/game-native"), ("machine-gate.toml", "extracted/GFZE01")):
            with open(os.path.join(self.work, "port/scratch/gates/tagin", name)) as f:
                made = f.read().splitlines()
            self.assertEqual([l for l in made if l.startswith("runner")],
                             ['runner = "port/launcher-mine/recomp/moderngekko-run.exe"'])
            self.assertIn(f'game = "{game}"', made)                          # the rest is the port's file
        dry = self.gates("--launcher", f"{self.work}/port/launcher-mine", "--dry-run", only="offline")[2]
        self.assertIn("SHOTS=5200 port/gates/runs/launcher-run.sh tagin-offline", dry)
        self.assertNotIn("as things stand", dry)                             # the folder holds all the row needs
        self.assertIn(f"export BUILD=n7 BUNDLE={self.work}/port/launcher-mine/recomp/fzgx "
                      f"GAME={self.work}/port/launcher-mine/recomp/game LAUNCHER=launcher-mine "
                      f"MACHINE={self.work}/port/scratch/gates/tagin/machine.toml", dry)

    def test_the_checks_row_takes_its_turn_as_a_test_run_and_no_native_builds_lock(self):
        # full checks run side by side and beside a native build (the owner, 2026-10-25): the row takes the turn of
        # a test run (cpu-window.sh) and nothing more
        self.staged()
        pc = os.path.join(self.work, "pc-scripts")                          # this PC's own scripts (PC_SCRIPTS): a stand-in
        self.write("pc-scripts/cpu-window.sh", "")
        self.write("pc-scripts/native-build-lock.sh", "")                  # there, and still not taken by the row
        dry = self.gates("--dry-run", only="checks", PC_SCRIPTS=pc)[2]
        self.assertNotIn("native-build-lock.sh", dry)
        self.assertIn('( PORT_AGENT=port-checks; '
                      f'source {pc}/cpu-window.sh "port: each part\'s checks" 8; port/check.sh && ', dry)
        # each suite from its own folder (its global.json names the test runner that knows --solution)
        self.assertIn("( cd ../piconet-service/net && dotnet test --solution net.slnx ) && echo 'check: ok' )", dry)

    def test_a_machine_file_names_a_runner_in_no_launcher_folder(self):
        self.staged()
        self.write("port/scratch/mine/moderngekko-run.exe", "another runner")
        machine = self.write("port/scratch/mine/machine.toml", MACHINE.replace("ModernGekko/build", "port/scratch/mine"))
        dry = self.gates("--dry-run", only="control offline", MACHINE=machine)[2]
        self.assertIn(f"({self.work}/port/scratch/mine/moderngekko-run.exe)", dry.splitlines()[0])
        self.assertIn(f"MACHINE={machine}", dry)                             # the playbacks get the file as it is
        self.assertIn("runner = \"port/scratch/mine/moderngekko-run.exe\"'; } > "
                      f"{self.work}/port/scratch/gates/tagin/machine-gate.toml", dry)
        lines = [l for l in dry.splitlines() if "as things stand" in l]
        self.assertEqual(len(lines), 2, dry)
        # (control first: the playbacks of kept recordings run beside row checks, before the rows that need quiet)
        self.assertIn("not run: needs the recording of run qs0 (port/setup/kept.tsv) (no ", lines[0])  # control: only that
        self.assertIn("needs launcher folder launcher-dev holding the runner under test", lines[1])   # offline
        self.assertFalse(os.path.exists(os.path.join(self.work, "port/scratch/gates")))   # a dry run writes nothing

    def test_parts_of_two_images_and_a_folder_with_another_module_are_named(self):
        self.staged()
        self.write("work/cg-n7/manifest.json", '{"image_sha1": "bbbbbbbbbb"}')
        self.write("port/launcher-dev/recomp/gGFZE01_recomp.dll", "another module")
        status, rows, out = self.gates(only="control offline")
        self.assertIn("the bundle module n7 was built from (image bbbbbbbb;", rows["control"][0])
        self.assertIn("launcher folder launcher-dev holding module n7", rows["offline"][0])
        self.assertEqual(self.started(), [])

    def test_what_is_refused_before_anything(self):
        for args, more, said in ((("--runner", "x"), {}, "--runner has gone"), (("--launcher", "a/b"), {}, "names a folder"),
                                 ((), {"MACHINE": "/nowhere/m.toml"}, "no machine file /nowhere/m.toml")):
            status, rows, out = self.gates(*args, **more)
            self.assertEqual((status, rows), (2, {}), out)
            self.assertIn(said, out)


class TheHarnessesMachineFile(Work):
    """gate-native.sh and time-native.sh hand the harness the machine file MACHINE names, in the work folder asked."""

    def setUp(self):
        super().setUp()
        self.write("port/bundle-native/patches.json")
        self.write("port/Dolphin.ini.gate-nocheats", "EnableCheats = False\n")
        self.write("scratch/Dolphin.ini.single")
        self.write("user/Config/Dolphin.ini")
        self.write("port/machine-gate-n.toml", MACHINE)
        self.write("port/scratch/rp/quiet.sh", "#!/bin/bash\n", 0o755)

    def harness(self, script, **more):
        done = subprocess.run(["bash", os.path.join(SCRIPTS, script), "tagm", "n7", "1"], env=dict(self.env, **more),
                              capture_output=True, text=True, timeout=120)
        with open(os.path.join(self.work, "harness.log")) as f:
            calls = f.read().splitlines()
        os.remove(os.path.join(self.work, "harness.log"))
        return done.returncode, calls, done.stdout + done.stderr

    def test_the_default_is_the_work_folders_gate_file_and_machine_names_another(self):
        mine = self.write("port/scratch/mine/machine.toml", MACHINE)
        for script, runs in (("gate-native.sh", 8), ("time-native.sh", 4)):
            for more, want in (({}, f"{self.work}/port/machine-gate-n.toml"), ({"MACHINE": mine}, mine)):
                status, calls, out = self.harness(script, **more)
                self.assertEqual({c.split(" ")[0] for c in calls}, {want}, out)
                self.assertEqual(sum(1 for c in calls if c.split(" ")[1] == "run"), runs, out)

    def test_the_timing_batch_is_the_jit_and_the_module(self):
        status, calls, out = self.harness("time-native.sh")
        runs = [c for c in calls if c.split(" ")[1] == "run"]
        self.assertEqual(len(runs), 4, out)                                  # the JIT and the module, two scenes

    def test_a_machine_file_that_is_not_there_stops_the_batch_before_a_run(self):
        for script in ("gate-native.sh", "time-native.sh"):
            done = subprocess.run(["bash", os.path.join(SCRIPTS, script), "tagm", "n7", "1"],
                                  env=dict(self.env, MACHINE="/nowhere/m.toml"), capture_output=True, text=True, timeout=60)
            self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
            self.assertIn("no machine file /nowhere/m.toml", done.stderr)
            self.assertFalse(os.path.exists(os.path.join(self.work, "harness.log")))


if __name__ == "__main__":
    unittest.main()
