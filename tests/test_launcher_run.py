"""Tests for launcher-run.sh's watch over a game, with stand-ins for the two Windows programs it calls: no launcher,
no game, a work folder of the test's own. The stand-in launcher writes its process ID, then a probe as the test's
plan says, and exits when the script's stop command arrives.

The fault these hold: the script ended one second after it had started the launcher (a read of the probe failed while
the game had not written one yet), leaving the game running; no test ran the script at all."""

import json
import os
import subprocess
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "..", "runs", "launcher-run.sh")

# powershell.exe: the launcher. Its plan is <work>/plan: lines "SLEEP seconds", "PROBE file" (the probe becomes a
# copy of that file) and "GONE" (its process ends there, as a crashed game's); then it waits for the stop command
# (10 s at most) and is gone. The environment it was given (-Env) is kept in <work>/env.
LAUNCHER = r"""#!/bin/bash
run=""; prev=""
for a in "$@"; do [ "$prev" = -RunDir ] && run=${a//\\//}; [ "$prev" = -Env ] && printf '%s' "$a" > "$PORT_WORK/env"; [ "$prev" = -MaxSeconds ] && printf '%s' "$a" > "$PORT_WORK/max-seconds"; prev=$a; done
case "$*" in *FreeVirtualMemory*) cat "$PORT_WORK/free-kb" 2> /dev/null || echo 33554432; exit 0;; esac   # room-for-games.sh
[ -n "$run" ] || exit 0          # (another call of the script's, not the launcher's start)
work=$PORT_WORK
: > "$work/alive"; echo 4242 > "$run/pid.txt"
while read -r what value; do
  case "$what" in SLEEP) sleep "$value";; PROBE) cp "$work/$value" "$run/probe.tmp"; mv "$run/probe.tmp" "$run/probe.csv";;
    GONE) rm -f "$work/alive"; exit 0;; esac
done < "$work/plan"
for _ in $(seq 1 100); do [ -e "$run/auto/commands/zz-stop.txt" ] && break; sleep 0.1; done
rm -f "$work/alive"
"""
TASKLIST = '#!/bin/bash\n[ -e "$PORT_WORK/alive" ] && echo "Launcher.App.exe  4242 Console"\nexit 0\n'
HEAD = "field,ticks,module,mode,submode,race_frame,x,qpc_us"


def probe(frames):
    """A probe whose fields hold these (mode, race frame)."""
    return "\n".join([HEAD] + [f"{i},0,801ba660,{mode},36,{frame},0,{1000 + i * 16_683}"
                               for i, (mode, frame) in enumerate(frames)]) + "\n"


class TheWatch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = self.tmp.name
        for name, text in (("powershell.exe", LAUNCHER), ("tasklist.exe", TASKLIST), ("taskkill.exe", "#!/bin/bash\n")):
            path = os.path.join(self.work, "bin", name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
            os.chmod(path, 0o755)
        # the harness's launch.ps1 as install.sh puts it into the work folder: one that takes a time limit
        os.makedirs(os.path.join(self.work, "kit-win"))
        self.write("kit-win/launch.ps1", "param([int]$MaxSeconds = 180)\n")

    def write(self, name, text):
        with open(os.path.join(self.work, name), "w") as f:
            f.write(text)
        return os.path.join(self.work, name)

    def run_script(self, plan, scene="boot-menus", **env):
        self.write("plan", plan)
        env = dict(os.environ, PORT_WORK=self.work, PORT_WORK_WIN=self.work, HAVE_LOCK="1", CARD="0", SHOTS="",
                   EMU_LOG="0", PATH=os.path.join(self.work, "bin") + os.pathsep + os.environ["PATH"], **env)
        done = subprocess.run(["bash", SCRIPT, "t1", scene], env=env, capture_output=True, text=True, timeout=50)
        end = os.path.join(self.work, "port", "runs", "t1", "end.txt")
        said = ""
        if os.path.exists(end):
            with open(end) as f:
                said = f.read()
        self.assertFalse(os.path.exists(os.path.join(self.work, "alive")), "the stand-in launcher was left running")
        return done.returncode, said, done.stdout + done.stderr

    def test_the_script_watches_a_game_that_has_no_probe_yet_and_stops_it_at_its_last_field(self):
        self.write("fields", probe([("1", 0)] * 80))
        # more than a second with no probe: the script's first looks find no file
        status, said, out = self.run_script("SLEEP 1.5\nPROBE fields\n", FIELDS="60")
        self.assertIn("t1: launcher pid=4242", out)
        self.assertIn("t1: first field after", out)
        self.assertRegex(said, r"t1: game and launcher exited [0-9.]+s after the stop command; 81 fields")
        self.assertEqual(status, 0, out)
        # launch.ps1's own limit: the run's 170 s and 40 for the stop (the project's standing rule 4)
        with open(os.path.join(self.work, "max-seconds")) as f:
            self.assertEqual(f.read(), "210")

    def test_no_game_starts_through_a_launch_script_without_a_time_limit(self):
        self.write("kit-win/launch.ps1", "param([string]$Runner)\n")   # an older harness's
        status, said, out = self.run_script("PROBE fields\n")
        self.assertEqual(status, 2, out)
        self.assertIn("sets no time limit", out)
        self.assertFalse(os.path.exists(os.path.join(self.work, "port", "runs", "t1", "pid.txt")))

    def test_a_match_race_that_never_started_and_one_that_booted_again_are_told_apart(self):
        match = self.write("match.json", "{}")
        self.write("gate", probe([("0", 0)] * 8 + [("510", 33423870)] * 3 + [("2", 0)] * 2400))
        status, said, out = self.run_script("PROBE gate\n", scene="match-race", MATCH=match)
        self.assertIn("NOT STARTED: the race has not started by field 24", said)
        self.assertNotIn("RESET", said)
        self.assertEqual(status, 1, out)
        # racing to race frame 1585, then at the start gate again after a second boot (the game of 2026-10-06)
        self.write("racing", probe([("0", 0)] * 8 + [("510", 33423870)] * 3 + [("2", f) for f in range(1586)]))
        self.write("again", probe([("0", 0)] * 8 + [("510", 33423870)] * 3 + [("2", f) for f in range(1586)]
                                  + [("0", 0)] * 12 + [("510", 33423870)] * 3 + [("2", 0)] * 900))
        status, said, out = self.run_script("PROBE racing\nSLEEP 1\nPROBE again\n", scene="match-race", MATCH=match)
        self.assertIn("RESET: the game was at race frame 1585 and is at its start gate again at field 25", said)
        self.assertNotIn("NOT STARTED", said)
        self.assertEqual(status, 1, out)

    def test_the_games_test_settings_are_in_the_launch_file_and_none_in_its_environment(self):
        self.write("fields", probe([("1", 0)] * 80))
        match = self.write("match.json", "{}")
        status, _, out = self.run_script("PROBE fields\n", scene="match-race", MATCH=match, FIELDS="60", PACE="1",
                                         REFERENCE="1", AUTOPILOT="1", LAG="30", INPUT="0:0,900:1000:142:128",
                                         GAME_DEBUG='"rollbackLog":"rb.csv"')
        self.assertEqual(status, 0, out)
        run = os.path.join(self.work, "port", "runs", "t1")
        with open(os.path.join(run, "launch.json")) as f:
            debug = json.load(f)["debug"]
        folder = self.work + "\\port\\runs\\t1"
        # what the launcher hands on as the game's "debug" part: the game reads these there and nowhere else
        self.assertEqual(debug["game"], {"automation": True, "probe": folder + "\\probe.csv", "pad": "0:0,900:1000:142:128",
                                         "paceLog": folder + "\\pace.csv", "windowNoActivate": True, "jit": True,
                                         "rollbackLog": "rb.csv"})
        self.assertTrue(debug["autopilot"])
        self.assertEqual(debug["testLagMs"], 30)
        self.assertEqual(debug["runnerArguments"], ["--automation-dir", folder + "\\auto", "--mute", "--allow-interpreter"])
        # the environment holds what a library reads for itself, and no test setting of the game
        with open(os.path.join(self.work, "env")) as f:
            self.assertEqual(f.read(), "SDL_JOYSTICK_HIDAPI_GAMECUBE=0")

    def test_no_game_starts_when_windows_has_too_little_memory_left(self):
        self.write("free-kb", str(3 * 1024 * 1024))                    # 3 GB; a game needs 4 (room-for-games.sh)
        status, said, out = self.run_script("GONE\n")
        self.assertEqual(status, 3, out)
        self.assertEqual(said, "t1: NOT STARTED: Windows has 3.0 GB of memory left to hand out, and one game needs 4.0 GB "
                               "(1.5 GB a game, and 2.5 GB that stays free; port/gates/room-for-games.sh): close "
                               "something, or wait until WSL has given memory back, and start again\n")
        self.assertEqual(out, said)                                    # the last line, and the only one
        self.assertFalse(os.path.exists(os.path.join(self.work, "port", "runs", "t1", "pid.txt")))   # no launcher

    def test_a_test_setting_named_in_the_environment_is_refused(self):
        for variable in ("FZGX_PACE_LOG={run}\\pace.csv", "MODERNGEKKO_STATICRECOMP=0", "FZGX_REINTERPRET_REUSE=0"):
            status, said, out = self.run_script("", RUN_ENV=variable)
            self.assertEqual(status, 2, out)
            self.assertIn("RUN_ENV names a test setting of the game", out)
            self.assertFalse(os.path.exists(os.path.join(self.work, "port", "runs", "t1", "pid.txt")), "a game was started")

    def test_a_game_whose_process_ends_with_no_end_line_of_its_own_is_gone(self):
        self.write("fields", probe([("1", 0)] * 30))
        status, said, out = self.run_script("PROBE fields\nSLEEP 0.6\nGONE\n", FIELDS="100000")
        self.assertIn("GONE: the game's process ended", said)
        self.assertIn("with no end line of its own", said)
        self.assertEqual(status, 1, out)


if __name__ == "__main__":
    unittest.main()
