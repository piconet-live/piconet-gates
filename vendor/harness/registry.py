"""The run registry: every process the harness starts, so that what an agent left running when it vanished can be
found and stopped, and nothing else is ever touched (rules/interruptions.md).

One small JSON file per process under <work>/harness-registry/. An entry records the process ID, the process's
own start time as the operating system reports it, its image name, the run and the label. `cleanup` stops an
entry's process only when a process with that ID, that image name and that start time is still running: process
IDs are reused, and a process that merely has the same number is not ours.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import time

DIR = "harness-registry"
PRUNE_AFTER = 86400          # ended entries are deleted after a day
START_TOLERANCE = 3          # seconds between the recorded and the reported start of the same process


def _folder(work: str) -> str:
    return os.path.join(work, DIR)


def windows_process(pid: int) -> dict | None:
    """{"name", "started"} of a running Windows process, or None. The default process table."""
    script = (f"$p = Get-Process -Id {int(pid)} -ErrorAction SilentlyContinue; "
              "if ($p) { $p.ProcessName + '|' + ([DateTimeOffset]$p.StartTime).ToUnixTimeSeconds() }")
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], capture_output=True, text=True,
                             timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if "|" not in out:
        return None
    name, started = out.rsplit("|", 1)
    try:
        return {"name": name, "started": int(started)}
    except ValueError:
        return None


def record(work: str, pid: int, image: str, label: str, run: str = "", run_dir: str = "", owner: str = "",
           table=windows_process, now: float | None = None) -> str:
    """Register a process just started. Returns the entry's path, for `finish`."""
    now = time.time() if now is None else now
    seen = table(pid)
    entry = {"pid": int(pid), "image": image, "label": label, "run": run, "run_dir": run_dir, "owner": owner,
             "host": socket.gethostname(), "recorded": int(now),
             "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(now)),
             "process_started": seen["started"] if seen else None, "ended": None}
    os.makedirs(_folder(work), exist_ok=True)
    path = os.path.join(_folder(work), f"{int(now)}-{int(pid)}.json")
    _write(path, entry)
    return path


def _write(path: str, entry: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=1)
    os.replace(tmp, path)


def finish(path: str, how: str = "ended", now: float | None = None) -> None:
    """Mark an entry's process as ended (by the harness itself, or found gone, or stopped by cleanup)."""
    try:
        with open(path, encoding="utf-8") as f:
            entry = json.load(f)
    except (OSError, ValueError):
        return
    entry["ended"] = int(time.time() if now is None else now)
    entry["how"] = how
    _write(path, entry)


def entries(work: str) -> list[tuple[str, dict]]:
    out = []
    try:
        names = sorted(os.listdir(_folder(work)))
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        path = os.path.join(_folder(work), name)
        try:
            with open(path, encoding="utf-8") as f:
                out.append((path, json.load(f)))
        except (OSError, ValueError):
            continue
    return out


def ours(entry: dict, seen: dict | None) -> tuple[bool, str]:
    """Is the running process `seen` the one this entry recorded?"""
    if seen is None:
        return False, "no such process is running"
    if entry["image"].lower() not in seen["name"].lower():
        return False, f"process {entry['pid']} is now '{seen['name']}', not ours"
    if entry.get("process_started") is not None:
        if abs(seen["started"] - entry["process_started"]) > START_TOLERANCE:
            return False, f"process {entry['pid']} started at another time: the number was reused"
    elif seen["started"] > entry["recorded"] + START_TOLERANCE:
        return False, f"process {entry['pid']} started after the entry was recorded: the number was reused"
    return True, "still running"


def cleanup(work: str, stop, say=print, table=windows_process, now: float | None = None, dry_run: bool = False
            ) -> dict:
    """Stop every registered process that is still running, and only those. `stop(entry)` ends one process.

    Returns counts: stopped, gone, not_ours, pruned."""
    now = time.time() if now is None else now
    counts = {"stopped": 0, "gone": 0, "not_ours": 0, "pruned": 0}
    for path, entry in entries(work):
        if entry.get("ended"):
            if now - entry["ended"] > PRUNE_AFTER:
                counts["pruned"] += 1
                if not dry_run:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
            continue
        if entry.get("host") != socket.gethostname():
            say(f"  left alone: {entry.get('label', '?')} (pid {entry['pid']}) was started on host "
                f"{entry.get('host')}, not this one")
            continue
        seen = table(entry["pid"])
        is_ours, why = ours(entry, seen)
        what = f"{entry.get('label', '?')} (pid {entry['pid']}, run '{entry.get('run', '')}', started " \
               f"{entry.get('recorded_at', '?')} by {entry.get('owner') or 'an unnamed agent'})"
        if is_ours:
            say(f"  {'would stop' if dry_run else 'stopping'}: {what}")
            counts["stopped"] += 1
            if not dry_run:
                stop(entry)
                finish(path, "stopped by cleanup", now)
        else:
            key = "gone" if seen is None else "not_ours"
            counts[key] += 1
            say(f"  already gone: {what}" if seen is None else f"  not touched: {what}: {why}")
            if not dry_run:
                finish(path, "found gone" if seen is None else "process ID reused", now)
    return counts
