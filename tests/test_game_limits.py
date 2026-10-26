"""No test game outlives its time limit (the project's standing rule 4): every start of a game in this repository passes
one, and none passes more than its script or its gate row documents.

Games start in two ways. the harness's launch.ps1 (a launcher and its game) takes -MaxSeconds; its watchdog ends what it
started at that limit (180 s when none is given, which this check does not allow: a caller says what it needs). The
kit's harness (`recomp.py run`) takes --max-seconds and hands launch.ps1 that and a minute; its own default is 900 s,
so a run here always names its limit, 180 s at most (an agent's test is three minutes or less).

The fault this holds: on 14 October a muted test game ran about 11 minutes because its start command blocked and the
agent did not notice; nothing ended it."""

import os
import re
import subprocess
import unittest

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
SKIP = ("archive/", "research/", "inventory/", "scripts/moves/")
MARGIN = 60   # what a caller may add to its documented duration: its own stop (30 s) and the start's seconds

# Each script that starts games with launch.ps1: where its header states the duration, the variable that holds it
# (whose default must be that duration), and the limit it passes, built from that variable: (unit, margin). A new
# caller gets its row here.
CALLERS = {
    "port/gates/runs/launcher-run.sh": (r"Bounded: (\d+) s", r"^BOUND=(\d+)", r'-MaxSeconds "\$\(\(BOUND \+ (\d+)\)\)"', 1),
    "port/gates/runs/quickplay-run.sh": (r"MINUTES \((\d+)\)", r"MIN=\$\{MINUTES:-(\d+)\}",
                                         r'-MaxSeconds "\$\(\(MIN \* 60 \+ (\d+)\)\)"', 60),
}
# (watch-race.sh, pace-session.sh and taskbar-run.sh are this PC's own scripts since 2026-10-25, in no repository:
# their rows and case are with them, the PC folder's tests/test_local_limits.py)


def listed(folder, prefix=""):
    out = subprocess.run(["git", "ls-files"], cwd=folder, capture_output=True, text=True, check=True).stdout.split("\n")
    return [prefix + path for path in out if path]


def tracked():
    # the runner's files and the gates' (a repository of their own since the split, checked out at port/gates, which
    # the runner's git ignores), as paths of the runner's root
    gates = os.path.join(REPO, "port", "gates")
    out = listed(REPO) + listed(gates, "port/gates/")
    for path in out:
        if path and not path.startswith(SKIP) and path.endswith((".sh", ".py", ".ps1", ".cmd", ".md")) \
                and "/tests/" not in path:
            yield path


def commands(path):
    """Each line of the file with its continuation lines joined (a shell command over several lines)."""
    with open(os.path.join(REPO, path), encoding="utf-8", errors="replace") as file:
        lines = file.read().split("\n")
    number = 0
    while number < len(lines):
        start, text = number, lines[number]
        while text.endswith("\\") and number + 1 < len(lines):
            number += 1
            text = text[:-1] + " " + lines[number].strip()
        yield start + 1, text
        number += 1


def code(text):
    return not text.lstrip().startswith("#")


def launches():
    """(path, line, command) of every start through launch.ps1."""
    for path in tracked():
        for number, text in commands(path):
            if "launch.ps1" in text and "-Runner" in text and code(text):
                yield path, number, text


def harness_runs():
    """(path, line, command) of every `recomp.py run` in a script (by its path, or by $K that holds it), with the
    values of the script's variables it names put after it (gates.sh's run19 holds a row's arguments)."""
    for path in tracked():
        if not path.endswith(".sh"):
            continue
        with open(os.path.join(REPO, path), encoding="utf-8") as file:
            values = dict(re.findall(r'^\s*(\w+)="((?:[^"\\\n]|\\.)*)"', file.read(), re.M))
        for number, text in commands(path):
            if code(text) and re.search(r'(recomp\.py"?|\$K)\s+run\s', text):
                named = [values[v] for v in re.findall(r"\$\{?(\w+)", text) if v in values]
                yield path, number, " ".join([text] + named)


class EveryGameHasItsLimit(unittest.TestCase):
    def test_every_start_through_launch_ps1_passes_a_limit(self):
        found = list(launches())
        self.assertGreaterEqual(len(found), 2, "fewer starts through launch.ps1 than the two scripts: has the search gone blind?")
        for path, number, text in found:
            with self.subTest(file=path, line=number):
                self.assertIn("-MaxSeconds", text, "a game started with no limit of its own")
                if path.endswith(".md"):   # a command a handbook shows: an agent's test, three minutes at most
                    seconds = re.search(r"-MaxSeconds (\d+)", text)
                    self.assertTrue(seconds and int(seconds.group(1)) <= 180, text)
                else:
                    self.assertIn(path, CALLERS, "a new caller of launch.ps1: give it its row in CALLERS")

    def test_each_caller_passes_its_documented_duration_and_no_more_than_its_margin(self):
        for path, (doc, var, passed, unit) in CALLERS.items():
            with self.subTest(file=path):
                with open(os.path.join(REPO, path), encoding="utf-8") as file:
                    text = file.read()
                header = "\n".join(line for line in text.split("\n") if line.startswith("#"))
                stated = re.search(doc, header)
                self.assertTrue(stated, f"{path}'s header no longer states its duration ({doc})")
                default = re.search(var, text, re.M)
                self.assertTrue(default, f"{path} holds its duration in no variable ({var})")
                self.assertEqual(default.group(1), stated.group(1), "the variable's default is not the stated duration")
                limits = [re.search(passed, t) for p, _, t in launches() if p == path]
                self.assertTrue(limits, f"{path} starts no game through launch.ps1 any more: remove its row")
                for limit in limits:
                    self.assertTrue(limit, f"{path} passes a limit not built from its duration ({passed})")
                    self.assertLessEqual(int(limit.group(1) or 0), MARGIN, "a margin over a minute")

    def test_a_program_started_outside_launch_ps1_is_given_its_watchdog(self):
        """Under port/gates every Start-Process of a runner or launcher goes through launch.ps1, or is handed to
        the harness's time-limit.ps1 by its process ID in the same script (as the PC's own taskbar-windows.ps1 does:
        it needs the launcher's window shown); the watchdog's own start is the one other Start-Process."""
        gates = os.path.join(REPO, "port", "gates")
        starts = 0
        for folder, _, names in os.walk(gates):
            if os.sep + "tests" in folder[len(gates):] or "__pycache__" in folder:
                continue
            for name in names:
                if not name.endswith((".ps1", ".sh", ".py", ".cmd")):
                    continue
                path = os.path.relpath(os.path.join(folder, name), REPO)
                with open(os.path.join(REPO, path), encoding="utf-8", errors="replace") as file:
                    text = file.read()
                for number, line in commands(path):
                    if not code(line) or not re.search(r"Start-Process|Process\]::Start|Win32_Process.*Create", line):
                        continue
                    with self.subTest(file=path, line=number):
                        if re.search(r'-FilePath "powershell\.exe"', line):
                            later = text[text.index(line.split("\n")[0][:40]):][:600]
                            # the watchdog: its script (by name, or the -Watchdog parameter) and the start time it watches
                            self.assertRegex(later[:400], r"time-limit\.ps1|\$Watchdog", "a PowerShell that is not the watchdog")
                            self.assertIn('"-Started"', later[:400], "a PowerShell that is not the watchdog")
                            continue
                        starts += 1
                        own = re.match(r"\s*\$(\w+)\s*=\s*Start-Process", line)
                        self.assertTrue(own, "a program started with no handle on its process for the watchdog")
                        self.assertRegex(text, r'"-Id",\s*\$%s\.Id' % own.group(1), "its ID is never given to the watchdog")
                        self.assertIn("time-limit.ps1", text)
                        self.assertRegex(text, r'"-MaxSeconds",\s*\$MaxSeconds')
        self.assertGreaterEqual(starts, 1, "no Start-Process under port/gates: has the search gone blind?")

    def test_a_gate_row_gives_its_games_no_longer_than_its_row_says(self):
        """A row of gates.sh that sets a Quick Play visit's MINUTES: its line in port/gates/README.md states that limit."""
        with open(os.path.join(REPO, "port/gates/gates.sh"), encoding="utf-8") as file:
            gates = file.read()
        with open(os.path.join(REPO, "port/gates/README.md"), encoding="utf-8") as file:
            rows = {m.group(1): m.group(0) for m in re.finditer(r"^- \*\*`([\w-]+)`\*\*.*$", file.read(), re.M)}
        found = re.findall(r'\b(?:step|manual) (\w+) "[^"\n]*?MINUTES=(\d+)[^"\n]*quickplay-run\.sh', gates)
        self.assertGreaterEqual(len(found), 3, "fewer Quick Play rows than quickplay, thirty and service: has the search gone blind?")
        for row, minutes in found:
            with self.subTest(row=row):
                self.assertIn(row, rows, f"gate row {row} has no line in port/gates/README.md")
                stated = re.search(r"games' limit (\d+) min", rows[row])
                self.assertTrue(stated, f"port/gates/README.md's row {row} does not state its games' limit")
                self.assertLessEqual(int(minutes), int(stated.group(1)), f"row {row} gives its games more than it states")

    def test_every_harness_run_names_its_limit_of_three_minutes_or_less(self):
        found = list(harness_runs())
        self.assertGreaterEqual(len(found), 5, "fewer harness runs than the gates have: has the search gone blind?")
        for path, number, text in found:
            with self.subTest(file=path, line=number):
                seconds = re.search(r'--max-seconds "?(?:\$\{\w+:-)?(\d+)', text)
                self.assertTrue(seconds, "a harness run with no --max-seconds runs up to the kit's 900 s")
                self.assertLessEqual(int(seconds.group(1)), 180)


if __name__ == "__main__":
    unittest.main()
