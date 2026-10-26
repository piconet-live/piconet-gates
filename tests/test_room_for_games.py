"""room-for-games.sh: no game is started when Windows has too little memory left to hand out (its free commit), and
the scripts that start games ask it first. powershell.exe is a stand-in (judge_fixtures.windows): no test asks
Windows, and no game, server or harness is started.

The playbacks' sets: test_replay_check.py. One game through a launcher: test_launcher_run.py."""
import os
import subprocess
import tempfile
import unittest

from judge_fixtures import gb, windows

HERE = os.path.dirname(os.path.abspath(__file__))
GATES = os.path.normpath(os.path.join(HERE, ".."))
REST = (" (1.5 GB a game, and 2.5 GB that stays free; port/gates/room-for-games.sh): close something, or wait until WSL "
        "has given memory back, and start again\n")


class Work(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = self.tmp.name
        self.locks = os.path.join(self.work, "locks")
        os.mkdir(self.locks)
        self.env = dict(os.environ, PATH=windows(self.work) + os.pathsep + os.environ["PATH"], PORT_WORK=self.work,
                        PORT_WORK_WIN="C:\\w", PORT_LOCKS=self.locks, PORT_AGENT="me")
        for name in ("LAUNCHERS", "WATCHER", "MACHINE", "BUNDLE", "BUSY_CHECK", "IGNORE_REQUESTS", "RECOMP_KIT"):
            self.env.pop(name, None)

    def write(self, path, content="", mode=0o644):
        path = os.path.join(self.work, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        os.chmod(path, mode)
        return path

    def run_script(self, script, *args, **env):
        done = subprocess.run(["bash", os.path.join(GATES, script), *args], env=dict(self.env, **env), capture_output=True,
                              text=True, timeout=60)
        return done.returncode, done.stdout, done.stderr

    def asked(self):
        try:
            with open(os.path.join(self.work, "asked")) as f:
                return len(f.read().split())
        except FileNotFoundError:
            return 0


class TheQuestion(Work):
    def room(self, games, **env):
        return self.run_script("room-for-games.sh", str(games), **env)

    def test_a_game_needs_a_gigabyte_and_a_half_and_two_and_a_half_stay_free(self):
        for free, games, room in ((4, 1, True), (3.99, 1, False), (5.5, 2, True), (5.49, 2, False), (7, 3, True),
                                  (6.99, 3, False), (64, 30, True)):
            self.write("free-kb", gb(free))
            code, out, err = self.room(games)
            self.assertEqual((code, out == "", err), (0 if room else 1, room, ""), (free, games, out))
        self.assertEqual(self.asked(), 7)

    def test_the_refusal_is_one_sentence_with_what_is_left_and_what_is_needed(self):
        self.write("free-kb", gb(3.29) + "\r\n")          # as Windows ends its lines; stated rounded down
        self.assertEqual(self.room(1), (1, "Windows has 3.2 GB of memory left to hand out, and one game needs 4.0 GB" + REST, ""))
        self.assertEqual(self.room(3), (1, "Windows has 3.2 GB of memory left to hand out, and 3 games need 7.0 GB" + REST, ""))

    def test_no_game_is_started_blind_when_windows_does_not_say(self):
        for answer in ("", "Get-CimInstance : Access denied\n"):
            self.write("free-kb", answer)
            code, out, err = self.room(1)
            self.assertEqual((code, err), (1, ""))
            self.assertRegex(out, r"^Windows did not say how much memory it has left \(powershell\.exe, FreeVirtualMemory, "
                                  r"answered \".*\"\), and no game is started blind: start again\n$")

    def test_a_pc_that_is_not_windows_is_not_asked(self):
        self.assertEqual(self.room(3, PATH="/usr/bin:/bin"), (0, "", ""))
        self.assertEqual(self.asked(), 0)

    def test_a_count_that_is_none_is_a_mistake_of_the_caller(self):
        for games in ("0", "three", ""):
            code, out, err = self.room(games)
            self.assertEqual((code, out, err), (2, "", "room-for-games: usage: room-for-games.sh GAMES (a count: 1, 2, 3)\n"))


class TheScriptsThatStartGames(Work):
    """Each asks before it starts anything, and ends with status 3 (not run: as a PC that is not free)."""

    def setUp(self):
        super().setUp()
        self.write("bin/sleep", "#!/bin/bash\n", 0o755)                 # the locks' waits
        self.env["BUSY_CHECK"] = self.write("port/scratch/rp/chk.sh", "#!/bin/bash\necho none\n", 0o755)

    def left(self):
        return sorted(os.listdir(self.locks))

    def test_two_games(self):
        self.write("free-kb", gb(5))
        code, out, err = self.run_script("runs/pair-run.sh", "r")
        self.assertEqual((code, err), (3, "pair-run r: not started: Windows has 5.0 GB of memory left to hand out, and 2 "
                                          "games need 5.5 GB" + REST))
        self.assertEqual((self.left(), os.listdir(os.path.join(self.work, "port/scratch/pair"))), ([], []))

    def test_quick_play_counts_every_launcher_and_the_watcher(self):
        self.write("free-kb", gb(8))                                    # three launchers: 7 GB; with the watcher 8.5
        code, out, err = self.run_script("runs/quickplay-run.sh", "r", LAUNCHERS="3", WATCHER="1")
        self.assertEqual(code, 3, out + err)
        self.assertRegex(out.splitlines()[-1], r"^r: \d\d:\d\d:\d\d not started: Windows has 8\.0 GB of memory left to "
                                               r"hand out, and 4 games need 8\.5 GB \(")
        self.assertEqual((self.left(), self.asked()), ([], 1))
        self.assertFalse(os.path.exists(os.path.join(self.work, "port/scratch/qp/r.server.log")))

    def test_the_gate_scenes_and_the_timings_stop_their_batch(self):
        self.write("free-kb", gb(3))
        self.write("port/bundle-native/patches.json", "{}")
        self.write("port/machine-gate-n.toml", "schema = 1\n")
        self.write("port/Dolphin.ini.gate-nocheats", "EnableCheats = False\n")
        self.write("user/Config/Dolphin.ini", "as it was\n")
        self.write("port/scratch/rp/quiet.sh", "#!/bin/bash\n", 0o755)
        for script in ("gate-native.sh", "time-native.sh"):
            code, out, err = self.run_script(script, "t", "n7")
            self.assertEqual((code, out), (3, "Windows has 3.0 GB of memory left to hand out, and one game needs 4.0 GB"
                                              + REST[:-1] + ": batch stopped\n"), script + err)
            self.assertFalse(os.path.exists(os.path.join(self.work, "port/launch")), script)   # no launch file, no run


if __name__ == "__main__":
    unittest.main()
