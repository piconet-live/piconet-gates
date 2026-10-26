"""board-run.sh's judge (reports/board-report.py): a run whose launcher saw everything passes; each thing missing is
named."""
import importlib.util
import json
import os
import shutil
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("board_report", os.path.join(HERE, "..", "reports", "board-report.py"))
br = importlib.util.module_from_spec(spec)
spec.loader.exec_module(br)

GOOD = [{"taken": True, "file": "game-1.board"}, {"phase": "Loading", "beat": 3}, {"phase": "Countdown", "beat": 500},
        {"phase": "Racing", "beat": 700}, {"snapshot": 200, "racers": 30, "localSeat": 0, "count": 1},
        {"snapshot": 800, "racers": 30, "localSeat": 0, "count": 601},
        {"kind": "Stands", "A": 2000, "B": 1, "Step": 1199, "ms": 30000, "lost": 0},
        {"frozen": True, "stood": 10.0, "phase": "Racing", "beat": 1500, "wholeProcess": False},
        {"frozen": False, "stood": 0, "phase": "Racing", "beat": 1501, "wholeProcess": False},
        {"ended": True, "phase": "Stopping", "beat": 5000, "stop": "Game", "lastFrame": "4800"}]


class Judge(unittest.TestCase):
    def run_of(self, values, launch=None):
        folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, folder)
        with open(os.path.join(folder, "stdout.txt"), "w", encoding="utf-8") as f:
            f.write("not json\n")
            for v in values:
                f.write(json.dumps({"event": "board", "values": v}) + "\n")
        with open(os.path.join(folder, "game-launch.json"), "w", encoding="utf-8") as f:
            json.dump(launch if launch is not None else {"board": "C:\\d\\boards\\game-1.board", "match": {}}, f)
        return br.judge(folder)[0]

    def test_a_run_that_saw_everything_passes(self):
        self.assertEqual(self.run_of(GOOD), [])

    def test_each_thing_missing_is_named(self):
        self.assertIn("the board was not taken", self.run_of(GOOD[1:]))
        self.assertIn("no phase Countdown", self.run_of([v for v in GOOD if v.get("phase") != "Countdown"]))
        self.assertIn("the game moving again was not seen", self.run_of([v for v in GOOD if v.get("frozen") is not False]))
        self.assertIn("the stand was not judged a freeze after 10 s", self.run_of([v for v in GOOD if "frozen" not in v]))
        self.assertIn("no last line", self.run_of(GOOD[:-1]))
        self.assertIn("the launch file names no board, or a live feed",
                      self.run_of(GOOD, {"board": "x.board", "match": {"live": "127.0.0.1:1"}}))


if __name__ == "__main__":
    unittest.main()
