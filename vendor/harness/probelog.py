"""Reading the probe's log (one CSV row per display field) with the column names the manifest gives.

Under the probe contract (docs/probe.md) a value or hash has its own name as its column, and a timer named N
has t_N (host time-stamp ticks), n_N (calls), c_N (emulated ticks) and e_N (the part of t_N spent in emulator
events). A probe that predates the contract names its timer columns by `legacy_column`.
"""
from __future__ import annotations

import csv

LOG_NAME = "probe.csv"


def read(path: str) -> list[dict]:
    """The log's rows. A last row cut short by a run that is still writing, or was stopped, is dropped."""
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        text = f.read()
    lines = text.split("\n")
    if lines and lines[-1] != "":
        lines = lines[:-1]  # no final newline: the last row is not complete
    lines = [x.rstrip("\r") for x in lines]  # a log written on Windows
    rows = []
    for row in csv.DictReader(lines):
        if None in row or any(v is None for v in row.values()):
            continue  # too many or too few cells
        rows.append(row)
    return rows


class Columns:
    def __init__(self, manifest):
        self.m = manifest
        probe = manifest.table("probe")
        self.select_value = probe.get("select_value")
        self.select_equals = probe.get("select_equals")
        self.skip = probe.get("skip_fields", 0)
        self.total_suffix = probe.get("legacy_total_column")
        self.timers = manifest.entries("probe.timer")

    def step(self) -> str:
        """The column holding the step counter: the logged value at exactness.step_counter."""
        counter = self.m.resolve(self.m.table("exactness")["step_counter"])
        for v in self.m.entries("probe.value"):
            if self.m.resolve(v["at"]) == counter:
                return v["name"]
        raise KeyError("no [[probe.value]] logs the step counter (exactness.step_counter)")

    def timer(self, timer: dict) -> dict[str, str]:
        suffix = timer.get("legacy_column")
        if suffix:
            return {"time": "t" + suffix, "n": "n" + suffix, "c": "c" + suffix, "events": "e" + suffix}
        name = timer["name"]
        return {"time": f"t_{name}", "n": f"n_{name}", "c": f"c_{name}", "events": f"e_{name}"}

    def total(self) -> dict[str, str]:
        s = self.total_suffix
        if s:
            return {"time": "t" + s, "n": "n" + s, "c": "c" + s, "events": "e" + s}
        return {"time": "t_all", "n": "n_all", "c": "c_all", "events": "e_all"}

    def selected(self, rows: list[dict]) -> list[dict]:
        """The rows worth measuring: complete, in the selected state, after the first `skip_fields`."""
        out = [r for r in rows if r.get("qpc_us")]
        if self.select_value:
            out = [r for r in out if r.get(self.select_value) == str(self.select_equals)]
        return out[self.skip:]
