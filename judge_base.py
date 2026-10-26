"""What every judge of gate-judge.py uses: the work folder, the logs a game leaves and its end lines, a file's
text, a module beside this one, and the verdict a judge fills."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "setup"))   # work_folder.py: the one place that says where the work folder is
import work_folder   # noqa: E402

W = work_folder.WORK_DEFAULT   # the work folder: gate-judge.py, the program, sets it from PORT_WORK
ENDS = {"results": "the player left the results; stopping", "desync": "the relay disconnected this game; stopping"}
LOGS = ("fzgx.log", "stderr.txt", "runner.log")


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text_of(*paths):
    out = ""
    for p in paths:
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                out += f.read()
    return out


class Verdict:
    """Findings of one judge: failures, playbacks cut short, and figures for the table."""

    def __init__(self):
        self.bad, self.cut, self.figures = [], [], []

    def fail(self, who, why):
        self.bad.append(f"{who}: {why}")
        print(f"  FAIL {who}: {why}")

    def unfinished(self, who, why):
        self.cut.append(f"{who}: {why}")
        print(f"  DID NOT FINISH {who}: {why}")

    def note(self, text):
        self.figures.append(text)
        print(f"  {text}")

    def close(self):
        result = "FAIL" if self.bad else "did not finish" if self.cut else "pass"
        said = self.bad + self.cut if self.bad or self.cut else self.figures
        more = f"; and {len(said) - 6} more (the judge's log has them)" if len(said) > 6 else ""
        print(f"verdict: {result} | {'; '.join(said[:6])}{more}")
        return 1 if self.bad else 4 if self.cut else 0
