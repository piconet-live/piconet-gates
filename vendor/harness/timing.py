"""Per-call times from the probe's log, in one table form.

Lifted from the first project's tasks.py, itrow.py and stats.py. The timed functions come from the manifest.
For each run: wall time per call of each timer, the same less the emulator's events ("guest code only"), and
per step the guest-code time summed over the timers, the timers' total, the events inside them, the CPU
thread's busy time and the run-loop dispatches per field.

Compare rows only within one interleaved batch, with the reference in the batch (rules/working-rules.md, 7).
"""
from __future__ import annotations

import probelog


def rate(rows: list[dict], fallback: float = 0) -> float:
    """Time-stamp ticks per second, from the log's own tsc and qpc_us columns (stats.py)."""
    rows = [r for r in rows if r.get("qpc_us") and r.get("tsc")]
    if len(rows) > 20:
        a, b = rows[10], rows[-1]
        seconds = (int(b["qpc_us"]) - int(a["qpc_us"])) / 1e6
        if seconds > 0:
            return (int(b["tsc"]) - int(a["tsc"])) / seconds
    if fallback:
        return fallback
    raise ValueError("the log is too short to measure the time-stamp rate, and the machine file gives no tsc_hz")


def measure(manifest, rows: list[dict], tsc_hz: float = 0) -> dict:
    """One run's figures. Times in microseconds per call and milliseconds per step."""
    cols = probelog.Columns(manifest)
    hz = tsc_hz or rate(rows)
    us = hz / 1e6
    sel = cols.selected(rows)
    n = len(sel)
    out: dict = {"fields": n, "tsc_ghz": hz / 1e9, "timers": {}}
    if n == 0:
        return out

    def total(col: str) -> int:
        return sum(int(r[col]) for r in sel if r.get(col))

    t_sum = e_sum = 0
    for timer in cols.timers:
        c = cols.timer(timer)
        if c["time"] not in sel[0]:
            continue
        t, calls = total(c["time"]), total(c["n"])
        e = total(c["events"]) if c["events"] in sel[0] else 0
        ticks = total(c["c"]) if c["c"] in sel[0] else 0
        t_sum += t
        e_sum += e
        out["timers"][timer["name"]] = {
            "us_per_call": t / us / max(calls, 1),
            "guest_us_per_call": (t - e) / us / max(calls, 1),
            "calls_per_field": calls / n,
            "kticks_per_call": ticks / max(calls, 1) / 1000,
        }
    out["timers_ms"] = t_sum / us / 1000 / n
    out["events_ms"] = e_sum / us / 1000 / n
    out["guest_ms"] = (t_sum - e_sum) / us / 1000 / n
    if "cpu_cycles" in sel[0]:
        out["cpu_ms"] = total("cpu_cycles") / us / 1000 / n
    if sel[0].get("dispatches"):
        out["dispatches"] = total("dispatches") / n
    return out


def header(manifest) -> str:
    names = [t["name"] for t in manifest.entries("probe.timer")]
    cells = [f"{'run':24s}"]
    cells += [f"{n[-10:]:>10s}" for n in names]
    cells += [f"{'g:' + n[-8:]:>10s}" for n in names]
    cells += [f"{'guest ms':>9s}", f"{'timers ms':>9s}", f"{'events':>7s}", f"{'CPU ms':>7s}", f"{'disp/field':>10s}",
              f"{'fields':>6s}"]
    return " ".join(cells)


def line(manifest, label: str, m: dict) -> str:
    names = [t["name"] for t in manifest.entries("probe.timer")]

    def cell(v, width, digits=2):
        return f"{v:{width}.{digits}f}" if v is not None else " " * (width - 1) + "-"

    cells = [f"{label[:24]:24s}"]
    cells += [cell(m["timers"].get(n, {}).get("us_per_call"), 10) for n in names]
    cells += [cell(m["timers"].get(n, {}).get("guest_us_per_call"), 10) for n in names]
    cells += [cell(m.get("guest_ms"), 9, 3), cell(m.get("timers_ms"), 9, 3), cell(m.get("events_ms"), 7, 3),
              cell(m.get("cpu_ms"), 7), cell(m.get("dispatches"), 10, 0), f"{m['fields']:6d}"]
    return " ".join(cells)


LEGEND = ("columns: per timer, wall microseconds per call; g: the same less emulator events (guest code only); then "
          "per step: guest code in the timers, the timers in all, events inside them, the CPU thread, dispatches")
