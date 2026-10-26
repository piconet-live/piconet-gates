"""The judges of a race several games ran (gate-judge.py pair, desync, quickplay): each game, their recordings as
one race, what the relay and the launchers' doors said, and the playbacks at the run's end."""
import collections
import glob
import json
import os
import re

import judge_base as base
from judge_base import ENDS, LOGS, load, text_of
from judge_game import WRITTEN, game
from judge_playback import playbacks, reread

# What a test server's relay logs when a checksum vote found a difference: the first when it disconnected the seat
# (--on-desync disconnect), the second when it only observed (the server's default) or the vote had no majority.
RELAY_DIFFERS = ("desynced at frame", "checksums differ at frame")
# How much shorter than the longest a recording of the same race may be. Each game records until its own player leaves
# the results, which the gates' pad scripts do at their next press of A: every 120 fields in row pair, every 180 in
# Quick Play, and the games' field counts are not aligned. So one period at most, 180 steps; twice that is allowed for
# a results page that takes the press one period later. In the 47 kept races of 6 October whose files hold the same
# results the largest difference is 139 steps (run qp2; rows pair: 106, 103).
MAX_SHORTER = 360
# A game of a build that logs it ("the results can be left from step N", port/core session.cpp) is timed from there
# instead: the press after the results' every-racer page opens leaves them. When that page opens is the game's own
# matter, by the local racer's standing (rows open from the last place up: run gv030-024218-q30, 26th, 11th and 6th
# left 150, 331 and 514 steps after the race's end, one press period apart each; gv022-214152 the same), so one
# race's recordings may differ by several press periods, and no bound across games fits. From its own moment a game
# leaves at the pad script's next press: one period (180 in Quick Play, 120 in row pair), and the few steps a game
# watching behind live runs late (1 to 9 measured in those two runs). The first press after the moment does not always
# leave, the next does: row pair's games left 241 and 244 steps after it in grid-p1, 244 and 123 in h5pair, 247 in
# sflk2-1 on image a8a50bc6 (0.3.0's simulation with the countdown fix: the game's own results flow, as before 0.4.0's
# changes), and Quick Play's grid-qp 365, two of its 180 periods. Why the first press is not taken is not found. So
# two periods and the steps late (2026-10-23, review 040); a lost press beyond that, or a hung page, still fails.
LEAVE_WITHIN = 2 * 180 + 12
# The games report a checksum of the race state every 60th frame, and the relay compares what they report.
CHECKSUM_INTERVAL = 60


def recordings(games, v, who="the recordings"):
    """games: [(name, recording as replay-compare.py reads it, the game logged that its player left the results[,
    the step its log says the results could first be left from, or None])]. One race, whatever the lengths: every
    file holds steps, ends on a whole step and holds the same results, and all are equal over the steps all hold.
    Each game records until its own player leaves the results, so lengths may differ, only when every game logged
    that it left: when every game logged when its results could be left, each by LEAVE_WITHIN steps from there at
    most; else (a build before that line) by MAX_SHORTER steps at most across the games."""
    games = [tuple(g) + (None,) * (4 - len(g)) for g in games]
    if len(games) < 2:
        return
    lengths = [len(g[1]["steps"]) for g in games]
    timed = all(g[3] is not None for g in games)
    for (name, rec, _, _), n in zip(games, lengths):
        if not rec["whole"]:
            v.fail(who, f"{name}'s recording is cut inside a step (after {n} whole steps): a file the game closed ends "
                        "on a whole step")
        if n == 0:
            v.fail(who, f"{name}'s recording holds no step")
    first = games[0]
    for name, rec, _, _ in games[1:]:
        if rec["seats"] != first[1]["seats"] or rec["lineup"] != first[1]["lineup"]:
            v.fail(who, f"{name} and {first[0]} are not one race (other seats or another lineup)")
            return
        n = min(len(rec["steps"]), lengths[0])
        differ = next((t for t in range(n) if rec["steps"][t] != first[1]["steps"][t]), None)
        if differ is not None:
            v.fail(who, f"{name} and {first[0]} differ first at step {differ} (inputs or checksum)")
    said, longest, equal = ", ".join(str(n) for n in lengths), max(lengths), len(set(lengths)) == 1
    results = [g[1]["results"] for g in games]
    for (name, rec, left, leavable), n in zip(games, lengths):
        why = [] if rec["results"] else ["its recording holds no results"]
        why += [] if left or equal else ["its game never logged 'the player left the results; stopping'"]
        if why:
            short = "cut short, " if n < longest else ""
            v.fail(who, f"{name} recorded {n} steps of {longest}: {short}{' and '.join(why)}")
        elif timed and not leavable <= n <= leavable + LEAVE_WITHIN:
            v.fail(who, f"{name} recorded {n} steps: it left its results {n - leavable} steps after they could "
                        f"first be left (step {leavable}), and a game leaves them within {LEAVE_WITHIN} (two presses)")
        elif not timed and longest - n > MAX_SHORTER:
            v.fail(who, f"{name} recorded {n} steps of {longest}: {longest - n} short, and a game leaves its results "
                        f"within {MAX_SHORTER} steps of the others (results in the file or not, it is cut short)")
    if all(results) and not all(r == results[0] for r in results):
        v.fail(who, f"the recordings ({said} steps) hold OTHER results")
    if equal:
        v.note(f"{who}: {lengths[0]} steps in each of {len(games)}, equal at every step, the same results")
    else:
        waits = ", ".join(str(n - g[3]) for g, n in zip(games, lengths)) if timed else ""
        v.note(f"{who}: {said} steps, equal over the {min(lengths)} all hold (each game records until its own "
               f"player leaves the results: every game logged that, every recording holds the same results"
               + (f"; each left {waits} steps after its results could be left" if timed else "") + ")")


# The core's line when its race-over test's "over" is settled: the step the race ended for every game before.
OVER = re.compile(r"the race is over before step (\d+)")


def ended_by_the_rule(games, short, v):
    """games: [(name, recording, every log of the game as one text)]; `short`: the game (1, 2, ...) whose own seat was
    still racing when the host's rule ended the race for everyone (the server's --finish-limit-seconds: so long after
    the first finish). The games agree on the step the race ended before, each saying it once; and in every game's
    recording that seat has no finish and is not out: it is the racer the results list calls DISQUALIFIED. A race
    that ended because its last machine finished or went out has no such racer, and fails here."""
    who = "the race's end"
    steps = set()
    for name, _, text in games:
        said = sorted(set(OVER.findall(text)), key=int)
        steps.update(said)
        if len(said) != 1:
            v.fail(name, f"its log says 'the race is over before step N' for {len(said)} steps "
                         f"({', '.join(said) or 'none'}): one is expected")
    if len(steps) > 1:
        v.fail(who, f"the games ended the race before different steps ({', '.join(sorted(steps, key=int))}): "
                    "every game ends it before the same step")
    if not 1 <= short <= len(games):
        v.fail(who, f"no game {short} among the {len(games)} with a recording")
        return
    seat, held = games[short - 1][1]["seat"], 0
    for name, rec, _ in games:
        rows = [r for r in (rec["results"] or {}).get("results", []) if r.get("seat") == seat]
        if len(rows) != 1:
            v.fail(name, f"its recording's results hold {len(rows)} entries for seat {seat} (game {short}'s own)")
        elif rows[0].get("finished") is not False or rows[0].get("out") is not False:
            state = "finished" if rows[0].get("finished") else "out" if rows[0].get("out") else "neither said"
            v.fail(name, f"its recording has seat {seat} (game {short}'s own) {state}: the host's rule was to end the "
                         "race with that seat still racing (finished false, out false)")
        else:
            held += 1
    if len(steps) == 1 and held == len(games):
        v.note(f"{who}: before step {min(steps)} in every game, by the host's rule; seat {seat} (game {short}'s own) "
               f"short of the line in all {len(games)} recordings (not finished, not out)")


def door(path):
    """A launcher's door lines: its races [{match, end, standings}], and what failed."""
    races, wrong = [], []
    for line in text_of(path).splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        name, values = e.get("event"), e.get("values") or {}
        if name == "match":
            races.append(dict(match=values.get("match"), end=None, standings=None))
        elif name == "game" and values.get("state") in ("closed", "never ran") and races:
            races[-1].update(end=values["state"], standings=values.get("standings"))
        elif name in ("failed", "problem") and values.get("text"):
            wrong.append(f"{name}: {values['text']}")
    return races, wrong


def judge_pair(a, v):
    compare, games, texts = load("replay-compare"), [], []
    log = text_of(a.log) if a.log else ""
    for i in (1, 2):
        name, folder = f"{a.run}-{i}", f"{base.W}/port/runs/{a.run}-{i}"
        seen = game(folder, name, v, "results", log + text_of(f"{base.W}/port/scratch/pair/{name}.run.log"), must=WRITTEN)
        if os.path.isfile(f"{folder}/race.fzrp"):
            games.append((name, compare.read(f"{folder}/race.fzrp"), seen.left, seen.leavable))
            texts.append(text_of(*(os.path.join(folder, n) for n in LOGS)))
        else:
            v.fail(name, "no recording (race.fzrp)")
    recordings(games, v)
    if a.short:
        ended_by_the_rule([(g[0], g[1], text) for g, text in zip(games, texts)], a.short, v)
    for line in text_of(f"{base.W}/port/scratch/pair/{a.run}.server.log").splitlines():
        if any(said in line for said in RELAY_DIFFERS):
            v.fail("the relay", line.strip()[:160])
    if a.log and a.playbacks:
        playbacks(log, v, a.playbacks, again=reread)


def judge_desync(a, v):
    """A difference made on purpose in game 2 (pair-run.sh ALTER2) against a relay that observes, the server's default:
    it is found, nobody is disconnected, nothing is repaired, and both games race on to their own finish."""
    compare, recs = load("replay-compare"), []
    log = text_of(a.log) if a.log else ""
    for i in (1, 2):
        name, folder = f"{a.run}-{i}", f"{base.W}/port/runs/{a.run}-{i}"
        game(folder, name, v, "results", log + text_of(f"{base.W}/port/scratch/pair/{name}.run.log"), must=WRITTEN)
        if ENDS["desync"] in text_of(*(os.path.join(folder, n) for n in LOGS)):
            v.fail(name, f"its log holds '{ENDS['desync']}': the relay was to observe only")
        if os.path.isfile(f"{folder}/race.fzrp"):
            recs.append(compare.read(f"{folder}/race.fzrp"))
        else:
            v.fail(name, "no recording (race.fzrp)")
    server = text_of(f"{base.W}/port/scratch/pair/{a.run}.server.log").splitlines()
    found = [l.strip() for l in server if RELAY_DIFFERS[1] in l]
    frame = int(re.search(r"checksums differ at frame (\d+)", found[0]).group(1)) if found else None
    last = a.altered + CHECKSUM_INTERVAL - 1
    if not found:
        v.fail("the relay", f"its log has no '{RELAY_DIFFERS[1]}' line: the difference was NOT found")
    elif not a.altered <= frame <= last:
        v.fail("the relay", f"it first found a difference at frame {frame}, not within its comparison interval of the "
                            f"altered step ({a.altered} to {last})")
    for line in server:
        if RELAY_DIFFERS[0] in line or (RELAY_DIFFERS[1] in line and "nobody is told or disconnected" not in line):
            v.fail("the relay", f"it was to tell and disconnect nobody: {line.strip()[:160]}")
    differ = same_after = None
    if len(recs) == 2:
        a_steps, b_steps = recs[0]["steps"], recs[1]["steps"]
        n = min(len(a_steps), len(b_steps))
        before = next((t for t in range(min(n, a.altered)) if a_steps[t] != b_steps[t]), None)
        differ = next((t for t in range(n) if a_steps[t][1] != b_steps[t][1]), None)
        if before is not None:
            v.fail("the recordings", f"they differ at step {before} (inputs or checksum), before the altered step {a.altered}")
        elif differ is None:
            v.fail("the recordings", f"their checksums do NOT differ over {n} steps: nothing was altered")
        else:
            if differ > (frame if frame is not None else last):
                v.fail("the recordings", f"their checksums differ first at step {differ}, after the frame the relay named")
            same_after = sum(a_steps[t][1] == b_steps[t][1] for t in range(differ, n))
            if same_after:
                v.fail("the recordings", f"{same_after} of the {n - differ} steps from step {differ} on have equal "
                                         "checksums again: a game that differed must stay different (nothing is repaired)")
        steps = f"equal over steps 0 to {a.altered - 1}, checksums differ at every step from {differ} to {n - 1}"
    else:
        steps = f"{len(recs)} of 2 recordings"
    v.note(f"the relay: {found[0][9:150] if found else '-'}; {len(found)} such line(s), nobody disconnected; both games "
           f"raced on to their own results; the recordings: {steps}")


def judge_quickplay(a, v):
    compare, by_match, replays = load("replay-compare"), collections.defaultdict(list), 0
    for i in range(1, a.launchers + 1):
        who, folder = f"launcher {i}", f"{base.W}/port/runs/{a.run}-{i}"
        races, wrong = door(f"{folder}/door.jsonl")
        for text in wrong:
            v.fail(who, text)
        if len(races) != a.races:
            v.fail(who, f"{len(races)} of {a.races} races in its door's lines ({a.run}-{i}/door.jsonl)")
        for k, race in enumerate(races, 1):
            name = f"{who} ({a.run}-{i}), race {k} ({race['match']})"
            closed = race["end"] == "closed"
            if not closed:
                v.fail(name, f"the game {race['end'] or 'did not close'}: it never ended its race")
            # a closed game's files are in raceK; one that never closed left them where it wrote them
            seen = game(f"{folder}/race{k}" if closed else folder, name, v, "results", must=WRITTEN)
            if not race["standings"]:
                v.fail(name, "no final standings from its game")
            found = sorted(glob.glob(f"{folder}/replays/*-{race['match']}.fzrp"))
            if len(found) != 1:
                v.fail(name, f"{len(found)} recordings of the match in its replay folder (1 expected)")
            for path in found[:1]:
                replays += 1
                by_match[race["match"]].append((f"launcher {i}", compare.read(path), seen.left, seen.leavable, race["standings"]))
    for match, games in by_match.items():
        if len(games) != a.launchers:
            v.fail(f"match {match}", f"{len(games)} of {a.launchers} launchers recorded it")
        recordings([g[:4] for g in games], v, f"match {match}")
        if len({json.dumps(g[4]) for g in games}) != 1:
            v.fail(f"match {match}", "the final standings from the launchers' own games are DIFFERENT or missing")
    if len(by_match) != a.races:
        v.fail(a.run, f"{len(by_match)} of {a.races} races were recorded")
    for line in text_of(f"{base.W}/port/scratch/qp/{a.run}.server.log").splitlines():
        if any(said in line for said in RELAY_DIFFERS):
            v.fail("the relay", line.strip()[:160])
    v.note(f"{replays} recordings of {a.launchers * a.races}" + ("" if v.bad else ", every game ended its race"))
    if a.log:
        playbacks(text_of(a.log), v, a.launchers * a.races, again=reread)
