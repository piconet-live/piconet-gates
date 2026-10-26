"""replay-check.sh with stand-ins for the harness and the busy check, on a work folder of the test's own: one
playback after the other as ever, and AT_ONCE=N, a set of playbacks side by side. No game, no Windows program.

The stand-in harness notes, for each run, the name it was given for the harness (RECOMP_AGENT), the user folder of
its machine file, and when it began and ended; it writes the playback's log as the test's plan says
(<work>/plan/RUN: "cut" leaves the summary line out, as a playback that its time limit ended, "cut once" at its
first call only; "differs" has a step that differs; "late" writes no log at its first call, as a game that never
started)."""
import json
import os
import subprocess
import tempfile
import unittest

from judge_fixtures import gb, recording, windows

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "replay-check.sh")
MACHINE = ('schema = 1\nwork = "/w"\nrunner = "r.exe"\ngame = "port/game-native"\nuser = "port/user"\n'
           'user_pristine = "port/user-pristine"\nconfig = "port/user/Config/Dolphin.ini"\n')
HARNESS = r'''import json, os, re, sys, time
work, run = os.environ["PORT_WORK"], sys.argv[2]
machine = open(os.environ["RECOMP_MACHINE"]).read()
began = time.time()
plan = ""
if os.path.exists(f"{work}/plan/{run}"):
    plan = open(f"{work}/plan/{run}").read().strip()
time.sleep(0.4)
if plan == "late":
    os.remove(f"{work}/plan/{run}")
else:
    if plan == "cut once":
        os.remove(f"{work}/plan/{run}")
        plan = "cut"
    os.makedirs(f"{work}/port/runs/{run}", exist_ok=True)
    differed = 3 if plan == "differs" else 0
    lines = ["fzgx: step 50, official 100"]
    if plan == "refused":   # the runner's line, and no game (moderngekko_run.cpp: "fzgx: " and Prepare's problem)
        lines = [f"fzgx: the launch file is refused: \"debug.nothing\" is no key of the launch file (C:\\w\\port\\launch\\{run}.json)"]
    elif plan != "cut":
        lines.append(f"fzgx: playback: 100 of 100 steps compared with the recording, {differed} differed; rollbacks 0 (0 forced), deepest 0")
    open(f"{work}/port/runs/{run}/stderr.txt", "w").write("\n".join(lines) + "\n")
with open(f"{work}/harness.log", "a") as f:
    f.write(json.dumps({"run": run, "agent": os.environ.get("RECOMP_AGENT"), "began": began, "ended": time.time(),
                        "user": re.search(r'^user = "(.*)"', machine, re.M).group(1),
                        "config": re.search(r'^config = "(.*)"', machine, re.M).group(1),
                        "game": re.search(r'^game = "(.*)"', machine, re.M).group(1), "args": sys.argv[3:]}) + "\n")
'''


class Work(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = self.tmp.name
        self.env = dict(os.environ, PORT_WORK=self.work, PORT_WORK_WIN="C:\\w", PORT_LOCKS=self.work,
                        RECOMP_KIT=os.path.join(self.work, "kit"),
                        BUSY_CHECK=self.write("chk.sh", '#!/bin/bash\necho asked >> "$PORT_WORK/busy.log"\necho none\n', 0o755))
        for name in ("AT_ONCE", "MACHINE", "BUNDLE", "GAME", "BUILD", "CONFIG", "SET", "ARGS", "RUN_ENV", "MAXS", "SHOTS",
                     "FIELDS", "PORT_AGENT", "RECOMP_AGENT", "RECOMP_MACHINE", "RECOMP_MANIFEST", "PC_SHARING_SAID"):
            self.env.pop(name, None)
        self.env["PATH"] = windows(self.work) + os.pathsep + os.environ["PATH"]   # Windows' memory: a stand-in says
        self.write("kit/tools/harness/recomp.py", HARNESS)
        self.write("port/machine-n.toml", MACHINE)
        self.write("port/bundle-native/patches.json", "{}")   # the build's parts a playback needs (only looked for)
        self.write("port/game-native/sys/main.dol")
        os.makedirs(os.path.join(self.work, "port/launch"))
        self.files = [self.write(f"port/replays-test/r{n}.fzrp", recording(100)) for n in range(1, 6)]

    def write(self, path, content="x", mode=0o644):
        path = os.path.join(self.work, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(content, bytes) else "w") as f:
            f.write(content)
        os.chmod(path, mode)
        return path

    def check(self, *files, **env):
        done = subprocess.run(["bash", SCRIPT, "t", *files], env=dict(self.env, **env), capture_output=True, text=True,
                              timeout=120)
        return done.returncode, done.stdout, done.stderr

    def ran(self):
        with open(os.path.join(self.work, "harness.log")) as f:
            return [json.loads(line) for line in f]

    def busy_checks(self):
        with open(os.path.join(self.work, "busy.log")) as f:
            return len(f.read().split())


class WhatAPlaybackNeeds(Work):
    def test_each_missing_part_is_named_with_where_it_comes_from_and_nothing_starts(self):
        os.remove(os.path.join(self.work, "port/game-native/sys/main.dol"))
        os.remove(os.path.join(self.work, "port/machine-n.toml"))
        code, out, err = self.check(self.files[0], os.path.join(self.work, "none.fzrp"), HOME=self.work)
        # (HOME: no ~/.config/piconet, so no disc is set: pins.tsv has no default)
        self.assertEqual(code, 2, out)
        # first, once, what of this PC's machine sharing is left out (lib.sh pc_sharing: no PC folder is named here)
        note, said = err.split("\n", 1)
        self.assertTrue(note.startswith("note: left out, as this PC's machine sharing is not here: "), err)
        self.assertIn("(PC_SCRIPTS: none named)", note)                         # an empty pins row is empty
        self.assertTrue(said.startswith("replay-check t: not run: needs the machine file "), err)
        self.assertIn("the game folder " + os.path.join(self.work, "port/game-native"), err)
        self.assertIn("from your own disc", err)
        self.assertIn("no disc image set: set DISC_DEFAULT to your own F-Zero GX (USA) ISO: a row ", err)
        self.assertIn(" in ~/.config/piconet/pins.tsv", err)
        self.assertIn("the recording " + os.path.join(self.work, "none.fzrp"), err)
        self.assertNotIn("native bundle", err)                                   # what is there is not named
        self.assertFalse(os.path.exists(os.path.join(self.work, "harness.log")))  # no game
        self.assertFalse(os.path.exists(os.path.join(self.work, "busy.log")))    # not even the busy check

    def test_a_pc_without_the_busy_check_plays_back_and_says_so_once(self):
        code, out, err = self.check(*self.files[:2], BUSY_CHECK=os.path.join(self.work, "no-check.sh"))
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.splitlines()[-1], "replay-check t: PASS")
        self.assertEqual(err.count("the busy check (" + os.path.join(self.work, "no-check.sh") + ")"), 1, err)


class ARefusedLaunchFile(Work):
    def test_it_is_said_refused_with_the_runners_line_and_fails_and_is_not_played_again(self):
        self.write("plan/t-2", "refused")
        code, out, err = self.check(*self.files[:3], AT_ONCE="3")
        self.assertEqual(code, 1, out + err)
        line = next(l for l in out.splitlines() if l.startswith("t-2: "))
        self.assertTrue(line.endswith(": FAIL"), line)
        self.assertIn("refused: the runner started no game: the launch file is refused: \"debug.nothing\" is no key", line)
        self.assertNotIn("did not finish", out)
        self.assertEqual(sorted(r["run"] for r in self.ran()), ["t-1", "t-2", "t-3"])   # once each: no play again
        self.assertEqual(out.splitlines()[-1], "replay-check t: FAIL")


class OneAfterTheOther(Work):
    def test_as_ever_the_ports_name_and_user_folder_and_a_check_before_each(self):
        code, out, err = self.check(*self.files[:3])
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual([line.rsplit(": ", 1)[1] for line in out.splitlines()], ["PASS"] * 4)
        self.assertEqual(out.splitlines()[-1], "replay-check t: PASS")
        ran = self.ran()
        self.assertEqual([(r["run"], r["agent"], r["user"], r["config"], r["game"]) for r in ran],
                         [(f"t-{k}", "port", "port/user", "port/user/Config/Dolphin.ini", "port/game-native")
                          for k in (1, 2, 3)])
        for before, after in zip(ran, ran[1:]):
            self.assertLessEqual(before["ended"], after["began"])        # never two at once
        self.assertEqual(self.busy_checks(), 3)
        self.assertIn("--not-timing", ran[0]["args"])
        self.assertIn("SDL_JOYSTICK_HIDAPI_GAMECUBE=0", ran[0]["args"])

    def test_a_count_of_one_is_the_same(self):
        code, out, _ = self.check(*self.files[:2], AT_ONCE="1")
        self.assertEqual((code, [r["agent"] for r in self.ran()], self.busy_checks()), (0, ["port", "port"], 2))

    def test_one_after_the_other_a_playback_that_did_not_finish_is_not_played_again(self):
        self.write("plan/t-2", "cut once")
        code, out, _ = self.check(*self.files[:3])
        self.assertEqual((code, out.splitlines()[-1]), (4, "replay-check t: DID NOT FINISH"))
        self.assertNotIn("played again", out)
        self.assertEqual([r["run"] for r in self.ran()], ["t-1", "t-2", "t-3"])


class ASetSideBySide(Work):
    def test_each_of_a_set_has_its_own_name_and_user_folder_and_the_set_one_busy_check(self):
        code, out, err = self.check(*self.files, AT_ONCE="3")
        self.assertEqual((code, err), (0, ""), out)
        # five files: a set of three, then a set of two; the lines are in the files' order
        self.assertEqual([line.split(":")[0] for line in out.splitlines()], [f"t-{k}" for k in range(1, 6)] + ["replay-check t"])
        ran = sorted(self.ran(), key=lambda r: r["run"])
        self.assertEqual([(r["run"], r["agent"], r["user"], r["config"]) for r in ran],
                         [("t-1", "port-pb1", "port/user-pb1", "port/user-pb1/Config/Dolphin.ini"),
                          ("t-2", "port-pb2", "port/user-pb2", "port/user-pb2/Config/Dolphin.ini"),
                          ("t-3", "port-pb3", "port/user-pb3", "port/user-pb3/Config/Dolphin.ini"),
                          ("t-4", "port-pb1", "port/user-pb1", "port/user-pb1/Config/Dolphin.ini"),
                          ("t-5", "port-pb2", "port/user-pb2", "port/user-pb2/Config/Dolphin.ini")])
        first, second = ran[:3], ran[3:]
        self.assertLess(max(r["began"] for r in first), min(r["ended"] for r in first))     # the three ran together
        self.assertLess(max(r["began"] for r in second), min(r["ended"] for r in second))
        self.assertLessEqual(max(r["ended"] for r in first), min(r["began"] for r in second))  # a set after the other
        self.assertEqual(self.busy_checks(), 2)                          # one check for a set
        self.assertEqual({r["game"] for r in ran}, {"port/game-native"})

    NOTE = ("t-2: it did not finish beside the others of its set (50 of 100 steps (no summary line within the limit of "
            "178 s)): played again, alone")

    def test_one_of_a_set_that_did_not_finish_is_played_again_alone_once_and_says_so(self):
        self.write("plan/t-2", "cut once")
        code, out, err = self.check(*self.files[:3], AT_ONCE="3")
        self.assertEqual((code, err), (0, ""), out)
        told = out.splitlines()
        self.assertEqual(told[1], self.NOTE)                              # in plain words, before its line
        self.assertEqual([line.rsplit(": ", 1)[1] for line in told[:1] + told[2:]], ["PASS"] * 4)
        self.assertEqual([line.split(":")[0] for line in told], ["t-1", "t-2", "t-2", "t-3", "replay-check t"])
        ran = self.ran()
        again = ran[-1]
        self.assertEqual((again["run"], again["agent"], again["user"]), ("t-2", "port-pb1", "port/user-pb1"))
        self.assertEqual(sorted(r["run"] for r in ran), ["t-1", "t-2", "t-2", "t-3"])
        self.assertGreaterEqual(again["began"], max(r["ended"] for r in ran[:3]))   # alone: after the set had ended
        self.assertEqual(self.busy_checks(), 2)                          # and after a busy check of its own

    def test_one_that_does_not_finish_alone_either_reads_did_not_finish(self):
        self.write("plan/t-2", "cut")
        code, out, _ = self.check(*self.files[:3], AT_ONCE="3")
        self.assertEqual(code, 4)
        told = out.splitlines()
        self.assertTrue(told[0].endswith(": PASS") and told[3].endswith(": PASS"), out)
        self.assertEqual(told[1], self.NOTE)
        self.assertTrue(told[2].startswith("t-2: ") and told[2].endswith(": DID NOT FINISH"), out)
        self.assertEqual(told[4], "replay-check t: DID NOT FINISH")
        self.assertEqual([r["run"] for r in self.ran()].count("t-2"), 2)   # once more, and no third time

    def test_one_that_finished_and_differs_is_a_fail_and_is_never_played_again(self):
        self.write("plan/t-3", "differs")
        code, out, _ = self.check(*self.files[:3], AT_ONCE="3")
        self.assertEqual((code, out.splitlines()[-1]), (1, "replay-check t: FAIL"))
        self.assertTrue(out.splitlines()[2].startswith("t-3: ") and out.splitlines()[2].endswith(": FAIL"), out)
        self.assertNotIn("played again", out)
        self.assertEqual(sorted(r["run"] for r in self.ran()), ["t-1", "t-2", "t-3"])
        # and a failure outranks a playback that did not finish beside it
        self.write("plan/t-1", "cut")
        code, out, _ = self.check(*self.files[:3], AT_ONCE="3")
        self.assertEqual((code, out.splitlines()[-1]), (1, "replay-check t: FAIL"))

    def test_a_run_name_and_a_launch_file_for_each_file(self):
        # the playbacks of several rows of the gate table in one set, each under its row's own name
        code, out, err = self.check(self.files[0], self.files[0], self.files[1], AT_ONCE="3",
                                    NAMES="g-rt-1 g-rtr-1 g-fork-1", CONFIGS="playback scrubber forced-1x1")
        self.assertEqual((code, err), (0, ""), out)
        self.assertEqual([line.split(":")[0] for line in out.splitlines()], ["g-rt-1", "g-rtr-1", "g-fork-1", "replay-check t"])
        self.assertEqual(sorted(r["run"] for r in self.ran()), ["g-fork-1", "g-rt-1", "g-rtr-1"])
        kinds = {}
        for run in ("g-rt-1", "g-rtr-1", "g-fork-1"):
            with open(os.path.join(self.work, "port/runs", run, "launch.json")) as f:
                launch = json.load(f)
            # (every playback is as the race: no launch file names a view)
            self.assertNotIn("view", launch["replay"])
            kinds[run] = ("replayEndQuits" in json.dumps(launch), "forceRollback" in json.dumps(launch))
        self.assertEqual(kinds, {"g-rt-1": (False, False), "g-rtr-1": (True, False), "g-fork-1": (False, True)})
        for more in ({"NAMES": "one two"}, {"CONFIGS": "playback"}):
            code, _, err = self.check(*self.files[:3], AT_ONCE="3", **more)
            self.assertEqual(code, 2)
            self.assertRegex(err, r"^replay-check: (NAMES names 2 runs|CONFIGS names 1 launch files) for 3 files\n$")

    def test_a_game_of_the_set_that_never_started_is_started_again_alone_after_a_new_busy_check(self):
        self.write("bin/sleep", "#!/bin/bash\n", 0o755)                 # the twenty seconds before the next try
        self.write("plan/t-2", "late")
        code, out, _ = self.check(*self.files[:3], AT_ONCE="3", PATH=os.path.join(self.work, "bin") + os.pathsep + os.environ["PATH"])
        self.assertEqual((code, out.splitlines()[-1]), (0, "replay-check t: PASS"))
        self.assertEqual([r["run"] for r in self.ran()].count("t-2"), 2)
        self.assertEqual(sorted(r["run"] for r in self.ran()), ["t-1", "t-2", "t-2", "t-3"])
        self.assertEqual(self.busy_checks(), 2)

    def test_no_game_starts_when_windows_has_too_little_memory_left_for_the_set(self):
        # 5.5 GB left: two games (1.5 GB each and 2.5 GB that stays free), not three. Asked before every set.
        self.write("free-kb", gb(5.5))
        code, out, _ = self.check(*self.files[:3], AT_ONCE="3")
        self.assertEqual((code, out), (3, "t-1: not run: Windows has 5.5 GB of memory left to hand out, and 3 games need "
                                          "7.0 GB (1.5 GB a game, and 2.5 GB that stays free; port/gates/room-for-games.sh): "
                                          "close something, or wait until WSL has given memory back, and start again\n"))
        self.assertFalse(os.path.exists(os.path.join(self.work, "harness.log")))     # nothing was started
        code, out, _ = self.check(*self.files[:3], AT_ONCE="2")
        self.assertEqual((code, out.splitlines()[-1]), (0, "replay-check t: PASS"))
        with open(os.path.join(self.work, "asked")) as f:
            self.assertEqual(len(f.read().split()), 3)                  # the refused set, then a set of two and of one

    def test_a_count_that_is_none_is_refused(self):
        for count in ("0", "three", "-1"):
            code, _, err = self.check(*self.files[:2], AT_ONCE=count)
            self.assertEqual((code, err), (2, "replay-check: AT_ONCE is a count of playbacks side by side (1, 2, 3)\n"))


if __name__ == "__main__":
    unittest.main()
