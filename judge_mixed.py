"""The judge of a race whose games ran different builds (gate-judge.py mixed; runs/mixed-run.sh): which game ran
which build, by the run's record and by each recording's own header; every step both games recorded, inputs and
checksum; and whether the race held what a difference would show under (each game's lag, its forced rollbacks at
every depth asked, the start, a seat on the wall, a seat across the line). A difference names its first step and
both games' builds; conditions that were not met fail the run too, so that a pass is never a quiet race's."""
import collections
import csv
import json
import os
import struct
import sys

import judge_base as base
import logs
from judge_base import LOGS, load, text_of
from judge_game import WRITTEN, game
from judge_race import RELAY_DIFFERS, recordings

sys.path.insert(0, os.path.join(base.HERE, "..", "facts", "generated"))   # the game's sizes and the checksum's masks
import facts   # noqa: E402

# The game's dump of the machines' state (its "debug.traceStates"; port/core/src/instruments.cpp): records of a mark,
# the step, how it ran and a size, then for each of the 30 racers its block and its progress record. A step that ran
# again after a rollback is written again: the last record of a step is the one that stood.
STATE, RACER, PROGRESS = 0x465A5354, facts.MACHINE_SIZE, facts.PROGRESS_SIZE
WALL_HITS = 0x213   # a racer's block: its count of wall hits, one byte (the re-machines-physics notes)
Played = collections.namedtuple("Played", "n launcher build lag drive alter rollbacks states name rec left text")


def games_of(run):
    """The run's record (mixed-run.sh's games.tsv): a row for each game, as text."""
    rows = []
    for line in text_of(f"{base.W}/port/scratch/mixed/{run}.games.tsv").splitlines():
        cells = line.split("\t")
        if len(cells) >= 8:
            rows.append(cells[:8])
    return rows


def states(path):
    """{step: the machines' state as the game last wrote it for that step}."""
    out, at, data = {}, 0, b""
    if os.path.isfile(path):
        with open(path, "rb") as f:
            data = f.read()
    while at + 16 <= len(data):
        mark, step, _, size = struct.unpack_from(">IIII", data, at)
        if mark != STATE or at + 16 + size > len(data):
            break
        out[step] = data[at + 16:at + 16 + size]
        at += 16 + size
    return out


def wall_hits(state, seat):
    at = seat * (RACER + PROGRESS) + WALL_HITS
    return state[at] if at < len(state) else 0


def differing(a, b):
    """Where two games' states of one step differ, by word the checksum covers: [(racer, "block" or "progress",
    offset, a's, b's)]. The words it leaves out (pointers, which differ with a game's memory, and what only the
    drawing reads: facts.BLOCK_SKIP, PROGRESS_SKIP) differ between two games that are equal, and are not counted."""
    out, size = [], RACER + PROGRESS
    for at in range(0, min(len(a), len(b)), 4):
        if a[at:at + 4] != b[at:at + 4]:
            racer, inside = divmod(at, size)
            part, offset, skip = ("block", inside, facts.BLOCK_SKIP) if inside < RACER else ("progress", inside - RACER, facts.PROGRESS_SKIP)
            if not skip[offset // 128] >> (31 - offset // 4 % 32) & 1:
                out.append((racer, part, offset, a[at:at + 4].hex(), b[at:at + 4].hex()))
    return out


def who(g):
    return f"game {g.n} ({g.launcher}: {'/'.join(part[:8] for part in g.build.split('/'))})"


def builds(played, want, v):
    """Each game ran the build its launcher folder held when the run began: its recording's header says the image
    and the module the game itself loaded. And the race mixed builds: `want` different ones at least."""
    for g in played:
        image, module = (g.build.split("/") + ["", ""])[:2]
        header = g.rec["header"]
        for what, held, said in (("module", module, header.get("module_sha1")), ("image", image, header.get("mod_sha1"))):
            if said != held:
                v.fail(g.name, f"its recording says {what} {str(said)[:8]}, and {g.launcher} held {held[:8]} when the "
                               "run began: which build this game ran is not known")
    different = len({g.build for g in played})
    if different < want:
        v.fail("the builds", f"{different} build(s) in {len(played)} games, {want} are wanted: "
                             f"{', '.join(who(g) for g in played)}")


def state_difference(a, b, first):
    """What differs between two games' dumped states, for the failure's line: the first dumped step that differs."""
    sa, sb = states(f"{base.W}/port/runs/{a.name}/trace.csv.states"), states(f"{base.W}/port/runs/{b.name}/trace.csv.states")
    for step in sorted(set(sa) & set(sb)):
        words = differing(sa[step], sb[step])
        if words:
            racer, part, offset, was, now = words[0]
            return (f"the machines' state at step {step}: {len(words)} word(s) the checksum covers differ, the first "
                    f"in racer {racer}, {part} +0x{offset:X} ({was} in game {a.n}, {now} in game {b.n})")
    return (f"no state both games wrote differs (steps {a.states.replace(',', ' to ')}, the last not written): for the "
            f"state itself run again with STATES={first},{first + 2}")


def steps(played, v):
    """Every pair of games over the steps both recorded: the first step whose inputs or checksum differ, with both
    games' builds. Returns whether all were equal."""
    equal = True
    for i, a in enumerate(played):
        for b in played[i + 1:]:
            if a.rec["seats"] != b.rec["seats"] or a.rec["lineup"] != b.rec["lineup"]:
                v.fail("the race", f"{who(a)} and {who(b)} are not one race (other seats or another lineup)")
                equal = False
                continue
            n = min(len(a.rec["steps"]), len(b.rec["steps"]))
            rows = [t for t in range(n) if a.rec["steps"][t][0] != b.rec["steps"][t][0]]
            sums = [t for t in range(n) if a.rec["steps"][t][1] != b.rec["steps"][t][1]]
            if not rows and not sums:
                continue
            equal = False
            first = min(rows[:1] + sums[:1])
            what = "; ".join(said for said in (
                f"checksums differ at {len(sums)} of the {n} steps both recorded, first at {sums[0]}" if sums else "checksums equal",
                f"inputs differ at {len(rows)}, first at {rows[0]}" if rows else "inputs equal"))
            v.fail("the builds differ", f"{who(a)} and {who(b)} differ first at step {first}: {what}; "
                                        f"{state_difference(a, b, first)}")
    return equal


def forced(path, depths):
    """{depth: rollbacks forced that deep} of a game's rollback log, for the depths asked."""
    count = collections.Counter()
    for row in logs.rollback_log(path):
        if (row.get("forced") or "0") != "0" and (row.get("depth") or "").isdigit():
            count[int(row["depth"])] += 1
    return {d: count[d] for d in depths}


def conditions(played, v):
    """What a difference would show under was there, in every game: its lag, the start, its forced rollbacks at each
    depth asked; and in the race: the wall for the seat driven into it, the line for a seat the AI drove. Returns
    the figures."""
    said = []
    for g in played:
        mine = [f"lag {g.lag} ms"]
        if g.lag != "0" and f"test lag {g.lag} ms" not in g.text:
            v.fail(g.name, f"its log does not say 'test lag {g.lag} ms': the lag was not on")
        if "fzgx: go (" not in g.text:
            v.fail(g.name, "its log has no 'go' line: the race did not start from the grid in this game")
        try:
            depths = [int(d) for d in json.loads(g.rollbacks).get("depths", [])]
        except (ValueError, AttributeError):
            depths = []
        done = forced(f"{base.W}/port/runs/{g.name}/rb.csv", depths)
        for depth, count in done.items():
            if count == 0:
                v.fail(g.name, f"no forced rollback {depth} steps deep in its rollback log (rb.csv)")
        mine.append("forced rollbacks " + ", ".join(f"{c} of depth {d}" for d, c in done.items()) if done else "no forced rollbacks asked")
        row = next((r for r in (g.rec["results"] or {}).get("results", []) if r.get("seat") == g.rec["seat"]), None)
        if g.drive == "wall":
            dump = states(f"{base.W}/port/runs/{g.name}/trace.csv.states")
            hits = max((wall_hits(state, g.rec["seat"]) for state in dump.values()), default=None)
            if not hits:
                v.fail(g.name, f"its seat {g.rec['seat']} was to be driven into the wall, and its state dump "
                               + ("holds no state" if hits is None else f"counts 0 wall hits (steps {', '.join(map(str, sorted(dump)))})"))
            mine.append(f"its seat {g.rec['seat']} on the wall: {hits or 0} hits by step {max(dump, default='-')}")
        else:
            if not row or row.get("finished") is not True:
                v.fail(g.name, f"its seat {g.rec['seat']}, which the game's AI drove, has no finish in its results")
            mine.append(f"its seat {g.rec['seat']} across the line")
        said.append(f"{who(g)}: " + ", ".join(mine))
    return said


def mixed(run, log, want, v):
    compare, played = load("replay-compare"), []
    rows = games_of(run)
    if len(rows) < 2:
        v.fail(run, f"no record of its games (port/scratch/mixed/{run}.games.tsv, which mixed-run.sh writes)")
        return
    for cells in rows:
        name = f"{run}-{cells[0]}"
        folder = f"{base.W}/port/runs/{name}"
        left = game(folder, name, v, "results", log + text_of(f"{base.W}/port/scratch/mixed/{name}.run.log"), must=WRITTEN).left
        if os.path.isfile(f"{folder}/race.fzrp"):
            played.append(Played(*cells, name, compare.read(f"{folder}/race.fzrp"), left,
                                 text_of(*(os.path.join(folder, n) for n in LOGS))))
        else:
            v.fail(name, "no recording (race.fzrp)")
    if len(played) < len(rows):
        return
    builds(played, want, v)
    if steps(played, v):   # (a difference is said once, with the builds; the recordings' own rules when there is none)
        recordings([(g.name, g.rec, g.left) for g in played], v, f"{run}: the recordings")
    found = [line.strip() for line in text_of(f"{base.W}/port/scratch/mixed/{run}.server.log").splitlines()
             if any(said in line for said in RELAY_DIFFERS)]
    if found:
        v.fail("the relay", f"{len(found)} line(s) of a difference in its log, the first: {found[0][:160]}")
    v.note(f"{run}: " + "; ".join(conditions(played, v)))


def judge_mixed(a, v):
    log = text_of(a.log) if a.log else ""
    for run in a.names:
        mixed(run, log, a.builds, v)
