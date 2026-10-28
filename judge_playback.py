"""The judge of a playback (gate-judge.py playback, playbacks): a recording played back against its own checksums.
A playback with no summary line did not finish, which is never a pass."""
import collections
import os
import re

import judge_base as base
import logs
from judge_base import load, text_of
from judge_game import NO_IDLES, crash_lines, frozen, probe_fields, screen_copies, spin

SUMMARY = re.compile(r"playback: (\d+) of (\d+) steps compared with the recording, (\d+) differed; "
                     r"rollbacks (\d+) \((\d+) forced\), deepest (\d+)")
RESULTS = re.compile(r"fzgx: playback: results (DIFFER from the recording's|other, not judged|not reached|not in the recording|the recording's)")
RESULT = re.compile(r"^(\S+): (.*): (PASS|FAIL|DID NOT FINISH)$", re.M)
# the runner's line when it starts no game from its launch file (port/core/src/files_launch.cpp ReadLaunchFile, said
# as "fzgx: ..." by the runner's start): the file refused, unreadable or too long
REFUSED = re.compile(r"(the launch file (?:is refused|cannot be read|is longer than 1 MiB)[^\r\n]*)")


def playback(text, steps, limit, fields=()):
    """(PASS | FAIL | DID NOT FINISH, what to say) for one playback's log. A launch file the runner refused is a FAIL
    with the runner's line: no game ran, and a run again would be refused again (it is no busy PC's "did not
    finish")."""
    refused = REFUSED.search(text)
    if refused:
        return "FAIL", f"refused: the runner started no game: {refused.group(1)[:300]}"
    crashed = crash_lines(text)
    if crashed:
        return "FAIL", f"crashed: {len(crashed)} line(s) like '{crashed[0][:90]}'"
    stuck = frozen(list(fields))
    if stuck:
        return "FAIL", stuck
    m = None
    for m in SUMMARY.finditer(text):
        pass
    first = re.search(r"differs from the recording first at step (\d+)", text)
    # the race's results against the recording's, where the recording took them (the runner's playback.cpp
    # CheckResults): a difference fails like a step that differs; a recording without results, or a playback cut
    # before its race's end, compares none
    results = RESULTS.search(text)
    if m:
        differ = bool(results) and results.group(1).startswith("DIFFER")
        ok = m.group(1) != "0" and m.group(3) == "0" and not differ
        return ("PASS" if ok else "FAIL",
                f"{m.group(1)} of {m.group(2)} steps compared, {m.group(3)} differed"
                f"{'; results DIFFER from the recording' if differ else ''}"
                f"{f' (first at step {first.group(1)})' if first else ''}; rollbacks {m.group(4)} ({m.group(5)} forced), "
                f"deepest {m.group(6)}")
    reached = [int(x) for x in re.findall(r"fzgx: step (\d+)", text)]
    if steps is None:   # the file is not at hand: the playback's own count of the recording's steps
        steps = max((int(x) for x in re.findall(r"fzgx: step \d+, official (\d+)", text)), default=None)
    slow = [l for l in text.splitlines() if l.startswith("[slow]")]
    busy = sum(1 for l in slow for b in [re.search(r"PC (\d+)% busy", l)] if b and int(b.group(1)) >= 95)
    said = f"did not finish: {max(reached, default=0)} of {steps if steps is not None else '?'} steps (no summary line"
    said += f" within the limit of {limit} s" if limit else ""
    said += f"; the PC was 95% busy or more in {busy} of its {len(slow)} slow seconds" if busy else ""
    said += f"; before the cut: differs from the recording first at step {first.group(1)}" if first else ""
    return "DID NOT FINISH", said + ")"


def playbacks(text, v, expect, control=False, who="playbacks", again=None):
    """A row's playback lines (replay-check.sh prints one for each file). again(run): that playback's log read
    anew, for a line written before "did not finish" was a result of its own (it read "...: FAIL")."""
    lines = [(m.group(1), m.group(2), m.group(3)) for m in RESULT.finditer(text.replace("\r", ""))]
    for k, (name, said, result) in enumerate(lines):
        if "the playback did not finish" in said:
            lines[k] = (name, said.split(": ")[0] + ": " + again(name) if again else said, "DID NOT FINISH")
    count = collections.Counter(r for _, _, r in lines)
    for name, said, result in lines:
        if result == "DID NOT FINISH":
            v.unfinished(name, said)
        elif control:
            differed = re.search(r", (\d+) differed", said)
            if result == "PASS" or not differed or int(differed.group(1)) <= 1:
                v.fail(name, f"the control must FAIL with more than 1 step differing, and read: {said}: {result}")
        elif result == "FAIL":
            v.fail(name, said)
    if len(lines) != expect:
        v.fail(who, f"{len(lines)} of {expect} playbacks have a result line")
    v.note(f"{who}: {count['PASS']} PASS, {count['FAIL']} FAIL, {count['DID NOT FINISH']} did not finish, of {expect}"
           + ("; " + "; ".join(f"{t.split(';')[0]}" for _, t, _ in lines) if len(lines) <= 2 else ""))


def judge_playback(a, v):
    folder = f"{base.W}/port/runs/{a.run}"
    drive = re.match(r"^([A-Za-z]):[\\/](.*)$", a.file)   # a Windows path, on any drive: as WSL sees it
    path = f"/mnt/{drive.group(1).lower()}/" + drive.group(2).replace("\\", "/") if drive else a.file
    steps = len(load("replay-compare").read(path)["steps"]) if os.path.isfile(path) else None
    result, said = playback(text_of(f"{folder}/stderr.txt"), steps, a.limit, probe_fields(f"{folder}/probe.csv"))
    pace = text_of(f"{folder}/pace.csv").splitlines()   # only a playback given FZGX_PACE_LOG has one
    waited, idles = spin(pace)
    drawn = [problem for problem in (screen_copies(pace) + [waited]) if problem]
    if drawn and result == "PASS":
        result, said = "FAIL", f"{said}; {drawn[0]}"
    elif pace and not idles:
        said += f"; {NO_IDLES}"
    print(f"{a.run}: {os.path.basename(path)}: {said}: {result}")
    return {"PASS": 0, "FAIL": 1}.get(result, 4)


def reread(run):
    folder = f"{base.W}/port/runs/{run}"
    return playback(text_of(f"{folder}/stderr.txt"), None, 0, probe_fields(f"{folder}/probe.csv"))[1]


UNDO_CHECK = re.compile(r"undo log check: (\d+) steps compared with every page: (.*)")


def undo_check(text):
    """None when a playback's log says the undo log's guard went on and its log was the same as every page compared
    gives at every step it checked (debug.undoLog "both"), else what is wrong."""
    if "undo log: guard on" not in text:
        no = re.search(r"undo log: (no guard|the guard cannot be had|the system refused)[^\n]*", text)
        return f"the guard never went on ({no.group(0)[:120]})" if no else "the guard never went on"
    m = None
    for m in UNDO_CHECK.finditer(text):
        pass
    if not m:
        return "no line of the undo log's check (debug.undoLog \"both\"?)"
    if int(m.group(1)) == 0 or m.group(2) != "the log the same at every step":
        return f"undo log check: {m.group(1)} steps compared: {m.group(2)}"
    return None


def judge_playbacks(a, v):
    playbacks(text_of(a.log), v, a.expect, a.control, again=reread)
    for run in a.undo_check:
        said = undo_check(text_of(*(f"{base.W}/port/runs/{run}/{name}" for name in base.LOGS)))
        if said:
            v.fail(run, said)
        else:
            v.note(f"{run}: the undo log's guard checked at every step against every page compared: the same")
    for run in a.copies:
        pace = text_of(f"{base.W}/port/runs/{run}/pace.csv").splitlines()
        copies = sum(1 for p in logs.records(pace) if p[0] == "E")
        if not copies:
            v.fail(run, "no pacing log with a screen copy (pace.csv): the copies' sizes were not checked")
        waited, idles = spin(pace)
        for problem in screen_copies(pace) + [waited]:
            if problem:
                v.fail(run, problem)
        if copies and not idles:
            v.fail(run, f"{NO_IDLES.split(':')[0]} (pace.csv): whether the game spun was not checked")
        if copies:
            v.note(f"{run}: {copies} screen copies read, " + ("one size for each destination" if not v.bad else "see above"))
