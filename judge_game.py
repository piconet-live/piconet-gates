"""The judge of one game (gate-judge.py game, runs, pieces): what its folder must hold to count as a game that ran
and ended as it should. The parts read text or rows; game() reads a folder and fills a Verdict."""
import collections
import glob
import json
import os
import re

import judge_base as base
import logs
from judge_base import ENDS, LOGS, text_of

CRASH = re.compile(r"\[staticrecomp\] unknown guest instruction|\[zero-access\]")
WRITTEN = ("probe", "pace")   # what pair-run.sh, quickplay-run.sh and match-run.sh make every game write
STOPPED = re.compile(r"game and launcher exited [0-9.]+s after the stop command")
FROZEN_GAP_US, FROZEN_SECONDS = 250_000, 15
PIECES_FROM, PIECES_TO = 0x80596000, 0x81800000   # on-demand modules load here: none of the game's own code


def crash_lines(text):
    return [l.strip() for l in text.splitlines() if CRASH.search(l)]


def probe_fields(path):
    """[(clock in us, race frame)] of a probe log, in order."""
    out = []
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8", errors="replace") as f:
        head = f.readline().rstrip().split(",")
        if "qpc_us" not in head or "race_frame" not in head:
            return out
        q, r = head.index("qpc_us"), head.index("race_frame")
        for line in f:
            c = line.rstrip("\n").split(",")
            if len(c) > max(q, r) and c[q].isdigit() and c[r].isdigit():
                out.append((int(c[q]), int(c[r])))
    return out


BOOTED = "fzgx: the game's code:"   # the core writes it once a boot, when it has patched the game
RACE_UNDER_WAY = 60                 # race frames: an ordinary rollback steps the frame back by its depth, never to 0


def booted_again(folder, one_race):
    """None, or how the folder shows a game that booted a second time (it reset itself: the game's own reset
    routine, 5.19). Two signs: a log with more than one line of the core's boot, and, in the probe, the race frame
    back at 0 after the race was under way (fields in the race mode, 2; a boot's first fields hold a stray number).
    The second only for a game started for one race (one_race): offline play goes from race to race."""
    boots = max((text_of(os.path.join(folder, n)).count(BOOTED) for n in LOGS), default=0)
    back, top = None, 0
    path = os.path.join(folder, "probe.csv")
    if (one_race or boots > 1) and os.path.isfile(path):   # (with two boots in a log the probe only says where)
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.readline().rstrip().split(",")
            if all(name in head for name in ("field", "mode", "race_frame")):
                at, m, r = head.index("field"), head.index("mode"), head.index("race_frame")
                for line in f:
                    c = line.rstrip("\n").split(",")
                    if len(c) <= max(at, m, r) or not c[r].isdigit():
                        continue
                    if c[m] == "2" and int(c[r]) > top:
                        top = int(c[r])
                    elif int(c[r]) == 0 and top > RACE_UNDER_WAY:
                        back = c[at]
                        break
    if back is not None:
        return (f"RESET: the game booted again at field {back} after race frame {top}"
                + (f" ({boots} boots in its log)" if boots > 1 else " (its race frame is back at 0)"))
    if boots > 1:
        return f"RESET: the game booted again ({boots} lines '{BOOTED}' in one log; the probe does not show where)"
    return None


def frozen(fields):
    """None, or how the probe's end shows a game that lives and no longer plays."""
    k = len(fields) - 1
    while k > 0 and fields[k][0] - fields[k - 1][0] > FROZEN_GAP_US:
        k -= 1
    seconds = (fields[-1][0] - fields[k][0]) / 1e6 if fields else 0
    if seconds < FROZEN_SECONDS:
        return None
    still = "stood still" if fields[k][1] == fields[-1][1] else f"went on from {fields[k][1]}"
    return (f"frozen: its last {len(fields) - 1 - k} fields took {seconds:.0f} s (the game's pace is 60 a second) and "
            f"race frame {fields[-1][1]} {still}, while the process lived")


SPUN_IDLES, SPUN_FIELDS = 5, 10
NO_IDLES = "its pacing log counts no idles: spin not checked"


def spun(lines):
    """spin()'s finding alone: None, or the row of fields in which the game spun."""
    return spin(lines)[0]


def spin(lines):
    """(None or the finding, whether the log counts idles at all). The finding: the longest row of consecutive race fields of a pacing log in which the CPU thread idled SPUN_IDLES
    times or fewer, when it is SPUN_FIELDS long or longer: the game's wait for the graphics processor's "draw done"
    spins without idling (a healthy field idles some 550 times; a frame that overruns its field gives a row of 1 or
    2). Over the 104 kept runs of 6 October: 0 to 2 in the 93 healthy ones, 60 in the game that reset itself, 23 to
    204 in the ten that crashed or froze. F records: field at 2, mode at 4, race frame at 6, idles at 22. A log in
    which no field idled more than that counts no idles (a JIT run's: the reference nmj; an older log's short
    records): nothing can be read from it, and the caller must say so (NO_IDLES), never pass it as checked."""
    longest, start, run, first, counted = 0, None, 0, None, False
    for p in logs.records(lines):
        if p[0] != "F" or len(p) < 23 or not (p[2].isdigit() and p[6].isdigit() and p[22].isdigit()):
            continue
        counted = counted or int(p[22]) > SPUN_IDLES
        if p[4] == "2" and int(p[6]) > RACE_UNDER_WAY and int(p[22]) <= SPUN_IDLES:
            first = p[2] if run == 0 else first
            run += 1
            if run > longest:
                longest, start = run, first
        else:
            run = 0
    if longest < SPUN_FIELDS or not counted:
        return None, counted
    return (f"the game spun without idling for {longest} fields from field {start}: it was waiting on the graphics "
            f"side (the CPU thread idled {SPUN_IDLES} times or fewer in each)"), counted


def screen_copies(lines):
    """Problems of a pacing log's E records (a copy out of the frame buffer): a destination that got two sizes."""
    frame, sizes = 0, collections.defaultdict(dict)
    for p in logs.records(lines):
        if p[0] == "F" and len(p) > 6 and p[6].isdigit():
            frame = int(p[6])
        elif p[0] == "E" and len(p) > 10:
            sizes[p[10]].setdefault(f"{p[7]}x{p[8]}", []).append(frame)
    odd = []   # (race frame logged before the copy, address, its size, the address's usual size)
    for address, by_size in sorted(sizes.items()):
        if len(by_size) > 1:
            usual = max(by_size, key=lambda s: len(by_size[s]))
            odd += [(f, address, size, usual) for size, frames in by_size.items() if size != usual for f in frames]
    if not odd:
        return []
    first, address, size, usual = min(odd)
    places, frames = sorted({o[1] for o in odd}), sorted({o[0] for o in odd})
    return [f"screen copies of two sizes to one destination: {address} (usually {usual}) got {size} after race frame "
            f"{first}; {len(odd)} such copies to {len(places)} destination(s) ({' '.join(places[:6])}) after race "
            f"frame(s) {' '.join(str(f) for f in frames[:4])}{' ...' if len(frames) > 4 else ''}"]


def pieces(text):
    """(the runner's own count at shutdown, lines, chunks named, of them outside the on-demand modules' range)."""
    chunks = re.findall(r"chunk \[0x([0-9A-Fa-f]+),0x[0-9A-Fa-f]+\) hash mismatch", text)
    own = {c for c in chunks if not PIECES_FROM <= int(c, 16) < PIECES_TO}
    failed = re.findall(r"shutdown:.*\bsmc_failed=(\d+)", text)
    return (int(failed[-1]) if failed else None), len(chunks), len(set(chunks)), len(own)


class Game:
    """What game() found of one game: left (its log holds the line of a race left after its results), and the
    checks it could not make because their file is not there (unchecked: "no probe: freeze not checked")."""

    def __init__(self, left, probe, copies, unchecked, silent=False, leavable=None):
        self.left, self.probe, self.copies, self.unchecked = left, probe, copies, unchecked
        self.silent = silent   # a JIT reference run whose log is there and empty
        self.leavable = leavable   # the step its log says the results could first be left from (None: no such line)

    def checked(self, end):
        """The words for a game that passed: only what was checked."""
        return ", ".join(["no crash line"] + ["not frozen"] * self.probe + [f"ended as asked ({end})"] +
                         ["one size for each screen-copy destination"] * self.copies + self.unchecked)


def reference_run(folder):
    """The harness's own word for the run (run.json): the JIT reference, which prints no line of its own. Only a
    second that ran slow leaves it a line, so on a quiet PC its log is there and empty."""
    try:
        with open(os.path.join(folder, "run.json"), encoding="utf-8") as f:
            return json.load(f).get("kind") == "reference"
    except (OSError, ValueError, AttributeError):
        return False


def game(folder, who, v, end="any", log="", copies=True, must=()):
    """One game's folder. must: of "probe" and "pace", the files the run's script always writes: one that is not
    there, or holds nothing to check, fails the game; otherwise its check is named as not made. Returns a Game."""
    text = text_of(*(os.path.join(folder, n) for n in LOGS))
    fields = probe_fields(os.path.join(folder, "probe.csv"))
    at = f"its last field is {len(fields)}, race frame {fields[-1][1]}" if fields else "no probe"
    unchecked = []
    if not fields:
        unchecked.append("no probe: freeze not checked")
        if "probe" in must:
            v.fail(who, "no probe (probe.csv is missing or holds no field): whether the game froze was not checked")
    silent = False
    if not text.strip():
        # a log that is there and empty is a JIT reference run's on a quiet PC; of any other game, or with no log
        # file at all, nothing was kept
        silent = any(os.path.isfile(os.path.join(folder, n)) for n in LOGS) and reference_run(folder) and end == "any"
        if not silent:
            v.fail(who, f"no log of the game was kept ({', '.join(LOGS)}): nothing shows how it ended ({at})")
    crashed = crash_lines(text)
    if crashed:
        v.fail(who, f"crashed: {len(crashed)} line(s) like '{crashed[0][:110]}' ({at})")
    stuck = frozen(fields)
    if stuck:
        v.fail(who, stuck)
    again = booted_again(folder, end in ENDS)
    if again:
        v.fail(who, again)
    said = text_of(os.path.join(folder, "end.txt")) + log
    words = []   # launcher-run.sh's own words for a game it had to end or lost: once each (end.txt and the run's log)
    for line in said.splitlines():
        if re.search(r": (FROZEN|GONE|NOT ENDED|NOT STARTED|RESET)\b", line) and os.path.basename(folder) in line:
            words += [line.split(": ", 1)[1][:200]] if line.split(": ", 1)[1][:200] not in words else []
    for line in words:
        v.fail(who, line)
    if end in ENDS and ENDS[end] not in text:
        v.fail(who, f"no end line '{ENDS[end]}' in its log ({at})")
    if end == "stop" and not STOPPED.search(said):
        v.fail(who, f"no line 'game and launcher exited ... after the stop command' ({at})")
    read = False   # the screen copies' sizes
    pace = text_of(os.path.join(folder, "pace.csv")).splitlines()
    waited, idles = spin(pace)
    if waited:
        v.fail(who, waited)
    elif pace and not idles:   # the measure cannot switch itself off unsaid
        unchecked.append(NO_IDLES)
        if "pace" in must:
            v.fail(who, f"{NO_IDLES.split(':')[0]} (pace.csv): whether the game spun was not checked")
    if copies:
        read = any(p[0] == "E" for p in logs.records(pace))
        if read:
            for problem in screen_copies(pace):
                v.fail(who, problem)
        else:
            unchecked.append("no pacing log: copies not checked" if not pace else
                             "its pacing log holds no screen copy: copies not checked")
            if "pace" in must:
                v.fail(who, f"{unchecked[-1].split(':')[0]} (pace.csv): the screen copies' sizes were not checked")
    said_leavable = re.findall(r"fzgx: the results can be left from step (\d+)", text)
    return Game(ENDS["results"] in text, bool(fields), read, unchecked, silent, int(said_leavable[-1]) if said_leavable else None)


def judge_game(a, v):
    seen = game(f"{base.W}/port/runs/{a.run}", a.run, v, a.end, text_of(a.log) if a.log else "", must=a.must)
    if not v.bad:
        v.note(f"{a.run}: {seen.checked(a.end)}")


def judge_runs(a, v):
    folders = sorted(f for n in a.names for f in glob.glob(f"{base.W}/port/runs/{n}") if os.path.isdir(f))
    seen = [game(folder, os.path.basename(folder), v, "any") for folder in folders]
    if not folders:
        v.fail("runs", f"no run folder matches {' '.join(a.names)}")
    if not v.bad:
        blind, silent = sum(1 for g in seen if not g.probe), sum(1 for g in seen if g.silent)
        v.note(f"{len(folders)} runs: no crash line, " + ("none frozen" if not blind else
               f"{len(folders) - blind} not frozen, {blind} with no probe: freeze not checked")
               + (f"; {silent} of them JIT reference runs whose log is empty (the JIT prints no line of its own)" if silent else ""))


def judge_pieces(a, v):
    for run in a.names:
        text = text_of(f"{base.W}/port/runs/{run}/stderr.txt") or text_of(f"{base.W}/port/runs/{run}/runner.log")
        if not text:
            v.fail(run, "no log")
            continue
        failed, lines, chunks, own = pieces(text)
        if own:
            v.fail(run, f"{own} of the {chunks} chunks that failed their check are the game's own code")
        v.note(f"{run}: {failed if failed is not None else 'no count of'} pieces failing at shutdown (the runner's "
               f"smc_failed), {lines} 'hash mismatch' lines naming {chunks} chunks, {own} of the game's own")
