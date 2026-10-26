#!/usr/bin/env python3
"""freeze-report.py RUN | LOG [SUMMARY-FILE]: what a game's log says of a freeze and of its stop (the freeze report:
port/moderngekko/src/freeze_watch.cpp, port/core/include/fzgx/freeze.h), for freeze-run.sh and for a player's log.

Prints each freeze (when it was reported, where the game was, whether it moved again), each wait for the relay,
the stop line and the summary's words. With --expect-test it judges the run of freeze-run.sh: a stand of 2.6 s in
the countdown that is not reported (the first report there waits 5 s), one of 2.6 s in the race that is reported
once and ends, a third that is reported at least twice, each report with all its lines, and is closed from outside
while it stands, and a summary line (in the log and as the last line of race-summary.txt) that says so. Its last line is then "freeze NAME: PASS" or
"freeze NAME: FAIL: why"; status 1 on a fail.

  --map PROGRAM=FILE   names the call stacks' places: FILE is the linker's map of PROGRAM (moderngekko-run.exe=
                       .../moderngekko-run.map, kept beside every runner that is built; the native module's the same
                       way). Each "PROGRAM+OFFSET" of the log's stacks is then printed with the function it is in.
"""

import bisect
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from map_lib import LinkMap  # noqa: E402  (the one reader of a link map)

STANDS = re.compile(r"fzgx: freeze: no game frame for ([0-9.]+) s \(report (\d+) of this freeze; game frame (\d+), race step (\d+); (.*)\)")
WAITS = re.compile(r"fzgx: wait: no game frame for ([0-9.]+) s: the core waits for the relay's inputs \(report (\d+) of this wait; game frame (\d+), race step (\d+)")
ENDS = re.compile(r"fzgx: (freeze|wait): (the game moves again; it|the race is over for this game .*; it had) (?:stood|waited) for ([0-9.]+) s")
STOP = re.compile(r"fzgx: stop: (.*)")
SUMMARY = re.compile(r"fzgx: race summary: (.*)")
# what a report holds beside its first line: a line each
PARTS = {
    "cpu": "fzgx: freeze: emulated CPU, ",
    "time": "fzgx: freeze: in those ",
    "game stack": "fzgx: freeze: the game's thread, call stack",
    "picture stack": "fzgx: freeze: the picture's thread",
    "command list": "fzgx: freeze: command list: ",
}


PLACE = re.compile(r"([A-Za-z0-9_.-]+)\+([0-9A-F]+)")


def read_map(text):
    """A linker's map (MSVC's /MAP, map_lib.LinkMap) as two lists in step: each function's or datum's offset from the
    program's first byte, ascending, and its name. The base is the map's "Preferred load address" (0x140000000 when
    it states none); what lies below it (the map's absolute symbols) is left out."""
    linked = LinkMap(text=text, default_base=0x140000000)
    found = [(at, name) for at, name in zip(linked.addresses, linked.names) if at >= 0]
    return [at for at, _ in found], [plain(name) for _, name in found]


def plain(name):
    """A decorated C++ name as Scope::Name where it is a plain one (?Name@Scope@@...); else as it is, cut."""
    if m := re.match(r"^\?([A-Za-z_]\w*(?:@[A-Za-z_]\w*)*)@@", name):
        return "::".join(reversed(m.group(1).split("@")))
    return name[:90]


def named(line, maps):
    """The line with every PROGRAM+OFFSET of a known program followed by its function and the offset inside it."""
    def name(m):
        offsets, names = maps.get(m.group(1).lower(), ([], []))
        i = bisect.bisect_right(offsets, int(m.group(2), 16)) - 1
        if i < 0:
            return m.group(0)
        return f"{m.group(0)} [{names[i]}+{int(m.group(2), 16) - offsets[i]:X}]"
    return PLACE.sub(name, line)


def read(text):
    """The log's freezes (a dict each: step, where, reports: a list of dicts of seconds and the parts seen, moved:
    seconds or None, left: the race ended under it), its waits for the relay (step, reports: seconds, ended), its
    first stop line and its summary line's words (key: value), or None for either. A report's lines are the ones
    from its first line to the next line that is no freeze line: the dump a slow shutdown gets, after the stop
    line, belongs to no report."""
    freezes, waits, stop, summary = [], [], None, None
    report = None   # the report whose lines are being read
    for line in text.splitlines():
        if m := STANDS.search(line):
            if m.group(2) == "1":
                freezes.append(dict(reports=[], moved=None, left=False, step=int(m.group(4)), where=m.group(5)))
            report = dict(seconds=float(m.group(1)), parts=set())
            if freezes:
                freezes[-1]["reports"].append(report)
            continue
        if "fzgx: freeze: " in line and not ENDS.search(line):
            part = next((name for name, mark in PARTS.items() if mark in line), None)
            if part and report is not None:
                report["parts"].add(part)
            continue
        report = None
        if m := WAITS.search(line):
            if m.group(2) == "1":
                waits.append(dict(reports=[], ended=None, step=int(m.group(4))))
            if waits:
                waits[-1]["reports"].append(float(m.group(1)))
        elif m := ENDS.search(line):
            which = freezes if m.group(1) == "freeze" else waits
            if which:
                which[-1]["moved" if m.group(1) == "freeze" else "ended"] = float(m.group(3))
                if m.group(1) == "freeze":
                    which[-1]["left"] = m.group(2).startswith("the race is over")
        elif (m := STOP.search(line)) and stop is None:
            stop = m.group(1).strip()
        elif m := SUMMARY.search(line):
            summary = words(m.group(1))
    return freezes, waits, stop, summary


def words(line):
    """The head of a summary line (protocol/formats.md, section 6) as key: value."""
    return dict(word.split("=", 1) for word in line.split(" | ")[0].split() if "=" in word)


def judge(text, summary_file):
    """Why the log of freeze-run.sh's game is not what it must be; None when it is."""
    freezes, waits, stop, summary = read(text)
    if any(f["step"] < 500 for f in freezes):
        return "the stand of 2.6 s in the countdown was reported: the first report there waits 5 s"
    if len(freezes) != 2:
        return f"{len(freezes)} freezes were reported, not the two the test makes in the race"
    first, second = freezes
    for n, freeze in enumerate(freezes, 1):
        for k, report in enumerate(freeze["reports"], 1):
            if missing := sorted(set(PARTS) - report["parts"]):
                return f"freeze {n}'s report {k} lacks: {', '.join(missing)}"
        if not 2.0 <= freeze["reports"][0]["seconds"] < 2.6:
            return f"freeze {n} was first reported after {freeze['reports'][0]['seconds']} s, not after 2"
        if "in the race" not in freeze["where"]:
            return f"freeze {n}'s first line does not say that it is in the race"
    if first["moved"] is None or len(first["reports"]) != 1:
        return "the first stand in the race (2.6 s) was not reported once and then said to move again"
    if second["moved"] is not None or len(second["reports"]) < 2:
        return "the second stand was not reported twice or more, standing to the stop"
    if waits:
        return "a wait for the relay was reported, and the test makes none"
    if stop is None or "the game's window was asked to close: a close message from outside" not in stop:
        return f"the stop line does not name the close from outside: {stop}"
    said = re.search(r"the game stood still when it was asked \(for ([0-9.]+) s by then\)", stop)
    if not said:
        return "the stop line does not say that the game stood still"
    if not second["reports"][-1]["seconds"] <= float(said.group(1)) < second["reports"][-1]["seconds"] + 4:
        return f"the stop line's {said.group(1)} s is not the length of the freeze it stopped in"
    if "fzgx: stop: the emulator has shut down" not in text:
        return "no line says that the emulator shut down"
    if summary is None:
        return "the log has no summary line"
    if (summary.get("freezes"), summary.get("stuck"), summary.get("end"), summary.get("waits")) != ("2", "yes", "closed", "0"):
        return (f"the summary line says freezes={summary.get('freezes')} stuck={summary.get('stuck')} "
                f"end={summary.get('end')} waits={summary.get('waits')}")
    if not float(summary.get("stood", "0").replace("-", "0")) >= second["reports"][-1]["seconds"]:
        return f"the summary line's stood={summary.get('stood')} is shorter than the last report"
    last = (summary_file.strip().splitlines() or [""])[-1]
    if words(last).get("stuck") != "yes" or words(last).get("freezes") != "2":
        return "the last line of race-summary.txt does not say the freeze"
    return None


def main(argv):
    expect = "--expect-test" in argv
    maps = {}
    while "--map" in argv:
        at = argv.index("--map")
        program, _, file = argv[at + 1].partition("=")
        maps[program.lower()] = read_map(open(file, encoding="utf-8", errors="replace").read())
        del argv[at:at + 2]
    names = [a for a in argv[1:] if not a.startswith("--")]
    if not names:
        sys.exit(__doc__)
    log = names[0]
    name = os.path.basename(log.rstrip("/"))
    if os.path.isdir(log):
        folder = log
        log = os.path.join(folder, "fzgx.log")
        names = names[:1] + [os.path.join(folder, "race-summary.txt")] + names[1:]
    text = open(log, encoding="utf-8", errors="replace").read()
    summary_file = open(names[1], encoding="utf-8", errors="replace").read() if len(names) > 1 and os.path.exists(names[1]) else ""
    freezes, waits, stop, summary = read(text)
    for n, freeze in enumerate(freezes, 1):
        how = "did not move again" if freeze["moved"] is None else (
            f"the race ended for this game after {freeze['moved']} s" if freeze["left"] else f"moved again after {freeze['moved']} s")
        whole = sum(1 for report in freeze["reports"] if report["parts"] == set(PARTS))
        print(f"freeze {n}: at race step {freeze['step']}, reported after "
              f"{', '.join(str(report['seconds']) for report in freeze['reports'])} s; {how}; {freeze['where']}; "
              f"{whole} of {len(freeze['reports'])} reports with all their lines")
    for n, wait in enumerate(waits, 1):
        how = "did not end in the log" if wait["ended"] is None else f"ended after {wait['ended']} s"
        print(f"wait {n} (for the relay's inputs; no freeze): at race step {wait['step']}, reported after "
              f"{', '.join(map(str, wait['reports']))} s; {how}")
    if maps:
        for line in text.splitlines():
            if "fzgx: freeze: " in line and ("call stack" in line or "host code" in line):
                print(named(line[line.index("fzgx: freeze: "):], maps).replace(" < ", "\n    < "))
    print(f"stop: {stop or 'no stop line'}")
    if summary:
        print(f"summary: end={summary.get('end')} freezes={summary.get('freezes')} stood={summary.get('stood')} "
              f"stuck={summary.get('stuck')} waits={summary.get('waits')}")
    if expect:
        why = judge(text, summary_file)
        print(f"freeze {name}: " + ("PASS" if why is None else f"FAIL: {why}"))
        return 0 if why is None else 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
