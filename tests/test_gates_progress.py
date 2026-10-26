"""The gate table's steps as the progress file hears them (gates-table.sh: progress_rows, head_row, put, finish's
last word; scripts/progress.py): the rows that take time are the run's steps, a row that fails is said and the pass
goes on, a pass of some rows is a kind of its own, and a dry run or a judge-only run says nothing. gates-table.sh is
sourced with the variables gates.sh gives it; no game, no work folder, a folder of the test's own for the files."""
import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GATES = """
set -u
root='{root}'; here="$root/port/gates"; M=t1; T=gt1-000000; OUT="$BASE/out"; DRY="{dry}"; JUDGE="{judge}"
ORDER=(checks batch match start roundtrip roundtrip-jit offline pieces fork forced control crash pair desync
       quickplay thirty failures service movie timing)
declare -A TITLE RES FIG NSTEP UNKNOWN FIRST NOLOG RANBAD LACKS STATED BEGAN TOOK ROWS
for id in "${{ORDER[@]}}"; do TITLE[$id]="row $id"; done
source "$here/gates-table.sh"
progress_rows
{rows}
progress_end "{status}" "$OUT/table.md"
"""


class GateRows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / "locks").mkdir()
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("PROGRESS_", "PORT_", "ONLY"))}
        self.env = {**clean, "PORT_LOCKS": str(self.base / "locks"), "BASE": str(self.base)}

    def tearDown(self):
        deadline = time.time() + 5
        while time.time() < deadline and subprocess.run(["pgrep", "-f", f"progress.py watch {self.base}"], capture_output=True).stdout:
            time.sleep(0.2)
        self.tmp.cleanup()

    def table(self, rows, status=0, dry="", judge="", **env):
        text = GATES.format(root=ROOT, rows=rows, status=status, dry=dry, judge=judge)
        done = subprocess.run(["bash", "-c", text], env={**self.env, **env}, capture_output=True, text=True, timeout=40)
        self.assertEqual(done.returncode, 0, done.stderr)
        runs = sorted((self.base / "locks" / "progress").glob("gates*.json"))
        return json.loads(runs[-1].read_text()) if runs else None

    # The progress file is written only through the monorepo's scripts/progress.sh (gates-table.sh progress_rows):
    # the split runner has none (the gates' README), so there is nothing of it to hear. The dry and judge-only
    # case below runs either way.
    WINDOW = unittest.skipUnless((ROOT / "scripts" / "progress.sh").is_file(),
                                 "no scripts/progress.sh in this runner: the gate table writes no progress file")

    @WINDOW
    def test_the_rows_that_take_time_are_the_steps_and_a_row_that_fails_is_said(self):
        said = self.table('head_row pair 3 > /dev/null; put pair pass "equal"; head_row start 0 > /dev/null; put start manual "no limit"\n'
                          'head_row desync 2 > /dev/null; put desync FAIL "no line of the relay"; head_row fork 1 > /dev/null; put fork "did not finish" "cut"', status=1)
        self.assertEqual((said["kind"], said["title"], said["steps"], said["state"]), ("gates", "Gate table, t1", 13, "stopped: needs someone"))
        self.assertEqual([(s["id"], s["name"], s["result"]) for s in said["done"]],
                         [("fork", "Fork replay", "failed"), ("pair", "Two-game race", "done"), ("desync", "Desync on purpose", "failed")])
        self.assertEqual((said["stopped"]["name"], said["stopped"]["log"]), ("Fork replay", str(self.base / "out" / "table.md")))
        self.assertEqual(len(said["left_out"]), 10)                                # the rows this made-up pass never reached

    @WINDOW
    def test_a_pass_of_some_rows_is_a_kind_of_its_own_with_those_rows(self):
        said = self.table('head_row pair 3 > /dev/null; put pair pass ""; head_row desync 2 > /dev/null; put desync pass ""', ONLY="pair desync")
        self.assertEqual((said["kind"], said["steps"], said["state"]), ("gates-pair-desync", 2, "done"))
        self.assertEqual([s["result"] for s in said["done"]], ["done", "done"])

    def test_a_dry_run_and_a_judge_only_run_say_nothing(self):
        self.assertIsNone(self.table('head_row pair 3 > /dev/null', dry="1"))
        self.assertIsNone(self.table('head_row pair 3 > /dev/null', judge="1"))


if __name__ == "__main__":
    unittest.main()
