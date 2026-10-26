#!/usr/bin/env python3
"""stat-pack-report.py RUN [MACHINE] [--only PART]: what the parts of stat-pack-run.sh RUN show
(handbook/stat-packs.md). --only: that part alone is judged (stat-pack-run.sh ONLY=PART), with the import.

  RUN-plain   no pack: the same race as the JIT reference's kept run (run-summary.py), a version 2 recording, no
              word of a stat pack in the game's log
  RUN-plain2  no pack, two games and rollbacks, computer racers: version 2 recordings, no word of a stat pack,
              rollbacks in both, the two recordings one race, and both played back on the build from before stat
              packs with 0 steps differing
  pbo-RUN     two recordings of the build from before stat packs, played back on this one with rollbacks forced:
              0 steps differing
  RUN-pack    two games on pack A among computer racers: laid in both and held at the go, the two recordings one
              race over every step both hold (replay-compare.py), rollbacks in both, version 3 recordings (7 since 0.4.0) with the
              pack in their header, both playbacks 0 steps differing, and the changed weight in the racers' blocks
              (stat-pack.py weights)
  RUN-two     game 1 on pack A, game 2 on pack B: each laid its own, the recordings' checksums differ within the
              first 60 steps, and the test server's relay said desync
  RUN-srv     the whole-file pack W from a server started with --stat-pack, through two launchers' Quick Play: the
              server named it, both games laid every value, and the rest as RUN-pack, with computer racers at CPU
              level 1
  RUN-real    two games on a pack of the repository (GX Unleashed), read from its file a third way: as RUN-pack
  RUN-no-*, RUN-game-*   packs with a machine's denormal, a machine's grip below its floor and a part's value past its
              size: the launcher refused the match start and started no game; the game, handed the pack itself,
              said that it refuses it
And the launcher's import of pack A: the fingerprint stat-pack.py worked out by itself.

A line for each thing looked at, "ok" or "FAIL" first; a part there is no run of is "not run", which is no pass.
The last line: "stat packs RUN: PASS" or "FAIL (N of M)". Exit status 0 only for PASS. Reads files only."""
import csv
import glob
import json
import os
import re
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "..", "setup"))   # work_folder.py: the one place that names the work folder
import work_folder   # noqa: E402
sys.path.insert(0, os.path.join(here, ".."))
import logs  # noqa: E402  (the one reader of the rollback log)
import parts  # noqa: E402
sys.path.insert(0, parts.path_in("REPO_PROTOCOL", "protocol/generated"))   # the replay file's reader (protocol/replay.toml)
import replay_file  # noqa: E402


def text(path):
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def game_log(folder):
    """The core's own lines of a game's run: its log file, and what it wrote to the runner's output."""
    return text(f"{folder}/fzgx.log") + text(f"{folder}/stderr.txt")


def laid(log, pack):
    """Whether a game's log says it laid this pack and held it at the go; and what it says."""
    mark = f"stat pack {pack['name']} ({pack['fingerprint'][:8]})"
    written = re.search(re.escape(mark) + r": (\d+) of its (\d+) values written over the game's car data", log)
    held = re.search(re.escape(mark) + r": its (\d+) values are in the game's car data; of (\d+) racers (\d+) hold "
                     r"their machines' weights from it and (\d+) another.*", log)
    refused = re.search(r"stat pack.*(?:refused|are not in the game's car data).*", log)
    said = "; ".join(m.group(0)[:150] for m in (written, held, refused) if m) or "no line of a stat pack"
    # laid and let go on the pack. What the racers held at the go is the game's own line and is read for what it
    # says (a racer that holds another weight is not a fault of the pack: the game may alter it), never judged.
    return bool(written and held and not refused), said


def replay_header(path):
    """(the replay's version, its header); (0, {}) when the file is no replay."""
    if not os.path.exists(path):
        return 0, {}
    r = replay_file.read(path)
    if not r.marked:
        return 0, {}
    try:
        header = json.loads(r.header) if r.header is not None else {}
    except ValueError:
        return r.version, {}
    return r.version, header if isinstance(header, dict) else {}


def replay_pack(path):
    """(the replay's version, its header's stat pack or None); (0, None) when the file is no replay."""
    version, header = replay_header(path)
    return version, header.get("match", {}).get("setup", {}).get("stats")


def computer_racers(path):
    """(how many of a replay's seats the game's own drivers hold, the race's CPU level or None)."""
    setup = replay_header(path)[1].get("match", {}).get("setup", {})
    return sum(1 for seat in setup.get("seats", []) if not seat.get("playerId")), (setup.get("rules") or {}).get("cpuLevel")


def played(log):
    """Whether a playback's log says every step was compared and none differed; and what it says."""
    done = re.search(r"playback: (\d+) of (\d+) steps compared with the recording, (\d+) differed", log)
    return bool(done) and done[1] == done[2] and done[3] == "0", done[0] if done else "no summary line (not run, or did not finish)"


def one_race(compare):
    """Whether replay-compare.py found two recordings to be one race; and its line."""
    line = next((l for l in compare.stdout.splitlines() if "steps in both" in l), compare.stdout.strip()[:200] or compare.stderr.strip()[:200])
    return compare.returncode == 0 and "checksums equal at every step" in line, line.strip()[:200]


def rollbacks(folder):
    """Displayed frames with a rollback in a game's rollback log; -1: no log."""
    if not os.path.exists(f"{folder}/rb.csv"):
        return -1
    return sum(1 for row in logs.rollback_log(f"{folder}/rb.csv") if int(row["depth"] or 0) > 0)


class Report:
    def __init__(self):
        self.lines, self.failed, self.checks = [], 0, 0

    def say(self, ok, what):
        self.checks += 1
        self.failed += not ok
        self.lines.append(("ok   " if ok else "FAIL ") + what)

    def not_run(self, what):
        self.checks += 1
        self.failed += 1
        self.lines.append("FAIL not run: " + what)


REFUSED = ("denormal", "negative", "part")   # stat-pack.py bad: the kinds of pack nobody may take


def plain(report, runs, reference, summary):
    folder = f"{runs}-plain"
    if not os.path.isdir(folder):
        return report.not_run("RUN-plain (the race without a pack)")
    report.say(summary.returncode == 0, f"plain: against {reference}: " + (summary.stdout.strip().splitlines() or ["no comparison"])[-1].strip()[:160])
    version, pack = replay_pack(f"{folder}/race.fzrp")
    report.say(version == 2 and pack is None, f"plain: the recording is version {version} and holds {'a' if pack else 'no'} stat pack")
    report.say("stat pack" not in game_log(folder), "plain: the game's log has no line of a stat pack")


def plain_pair(report, runs, compare, playbacks):
    if not os.path.isdir(f"{runs}-plain2-1"):
        return report.not_run("RUN-plain2 (two games without a pack, with rollbacks)")
    for i in (1, 2):
        folder = f"{runs}-plain2-{i}"
        version, pack = replay_pack(f"{folder}/race.fzrp")
        report.say(version == 2 and pack is None, f"plain2: game {i}: the recording is version {version} and holds {'a' if pack else 'no'} stat pack")
        report.say("stat pack" not in game_log(folder), f"plain2: game {i}: the game's log has no line of a stat pack")
        count = rollbacks(folder)
        report.say(count > 0, f"plain2: game {i}: {count} displayed frames with a rollback" if count >= 0 else f"plain2: game {i}: no rollback log")
        ok, said = played(playbacks[i - 1])
        report.say(ok, f"plain2: game {i}'s recording played back on the build from before stat packs: {said}")
    ok, line = one_race(compare)
    report.say(ok, "plain2: the two recordings: " + line)
    cpu, level = computer_racers(f"{runs}-plain2-1/race.fzrp")
    report.say(cpu > 0, f"plain2: {cpu} computer racers at CPU level {level}")


def old(report, names, playbacks):
    if not names:
        return report.not_run("pbo-RUN (recordings of the build from before stat packs, played back on this one)")
    for i, name in enumerate(names[:2]):
        ok, said = played(playbacks[i])
        cpu, level = computer_racers(name)
        report.say(ok, f"old: {'/'.join(name.split('/')[-3:])} ({cpu} computer racers, level {level}), rollbacks forced: {said}")


def same(report, runs, pack, compare, weights, playbacks, race="pack"):
    """A race of two games on one pack: RUN-pack (pair-run.sh), or RUN-srv (quickplay-run.sh: each game's files are
    in its launcher's folder, the first race's in race1, the replay in replays)."""
    quick = race == "srv"
    if not os.path.isdir(f"{runs}-{race}-1"):
        return report.not_run({"srv": "RUN-srv (the pack from a server, through Quick Play)",
                               "real": "RUN-real (two games on a pack of the repository)"}.get(race, "RUN-pack (two games on one pack)"))
    replays = []
    for i in (1, 2):
        folder = f"{runs}-{race}-{i}"
        kept = f"{folder}/race1" if quick else folder
        replays.append(next(iter(sorted(glob.glob(f"{folder}/replays/*.fzrp"))), "") if quick else f"{folder}/race.fzrp")
        ok, said = laid(text(f"{kept}/runner.log") if quick else game_log(folder), pack)
        report.say(ok, f"{race}: game {i}: {said}")
        version, held = replay_pack(replays[-1])
        report.say(version in (3, 7) and (held or {}).get("fingerprint") == pack["fingerprint"],
                   f"{race}: game {i}: the recording is version {version} with {'the pack' if held else 'no pack'} in its header")
        count = rollbacks(kept)
        report.say(count > 0, f"{race}: game {i}: {count} displayed frames with a rollback" if count >= 0 else f"{race}: game {i}: no rollback log")
        report.say(weights[i - 1].returncode == 0, f"{race}: game {i}: " + (weights[i - 1].stdout.strip().splitlines() or ["no state dump"])[-1][:260])
        ok, said = played(playbacks[i - 1])
        report.say(ok, f"{race}: game {i}'s recording played back: {said}")
    ok, line = one_race(compare(replays))
    report.say(ok, f"{race}: the two recordings: " + line)
    cpu, level = computer_racers(replays[0])
    report.say(cpu > 0, f"{race}: {cpu} computer racers at CPU level {level}")
    return level


def served(report, runs, pack, server):
    """What only the race from a server shows: the server named the pack, and the games hold every value of it."""
    if not os.path.isdir(f"{runs}-srv-1"):
        return
    count = len(pack["values"]) * 3 // 4 // 6
    line = next((l for l in server.splitlines() if "stat pack" in l), "no line of a stat pack")
    report.say(pack["fingerprint"] in line and f"({count} values" in line, "srv: the test server: " + line.strip()[:200])
    # (a game writes only the words that differ from the disc's, and at the go reads every value of the pack back)
    logs = [text(f"{runs}-srv-{i}/race1/runner.log") for i in (1, 2)]
    whole = all(f"its {count} values are in the game's car data" in log for log in logs)
    written = sorted({m[1] for log in logs for m in re.finditer(rf"(\d+) of its {count} values written", log)})
    report.say(whole and len(written) == 1, (f"srv: both games hold all {count} values at the go" if whole else f"srv: not every game held all {count} values at the go")
               + f" (written over the disc's: {', '.join(written) or 'none'})")


def refused(report, runs):
    if not any(os.path.isdir(f"{runs}-{who}-{kind}") for who in ("no", "game") for kind in REFUSED):
        return report.not_run("RUN-no-*, RUN-game-* (packs the launcher and the game must refuse)")
    for kind in REFUSED:
        said = re.search(r"The match's stat pack is not one this launcher takes: .*", text(f"{runs}-no-{kind}/stderr.txt"))
        fields = text(f"{runs}-no-{kind}/probe.csv").count("\n")
        report.say(bool(said) and fields < 2, f"refused: {kind}: the launcher: " + (said[0].strip()[:200] if said else "no sentence of a stat pack")
                   + ("" if fields < 2 else f"; and a game ran ({fields} fields)"))
        said = re.search(r"the race's stat pack is refused: .*", game_log(f"{runs}-game-{kind}"))
        report.say(bool(said), f"refused: {kind}: the game: " + (said[0].strip()[:200] if said else "no line that it refuses the pack"))


def differ(report, runs, packs, compare, server):
    if not os.path.isdir(f"{runs}-two-1"):
        return report.not_run("RUN-two (two games handed different packs)")
    for i in (1, 2):
        ok, said = laid(game_log(f"{runs}-two-{i}"), packs[i - 1])
        report.say(ok, f"two: game {i}: {said}")
    first = re.search(r"checksums differ first at step (\d+)", compare.stdout)
    report.say(bool(first) and int(first[1]) <= 60,
               "two: the recordings' " + (first[0] if first else "checksums do not differ: " + compare.stdout.strip()[-160:]))
    desyncs = [l for l in server.splitlines() if "desync" in l]
    report.say(bool(desyncs), "two: the test server's relay: " + (desyncs[0].strip()[:170] if desyncs else "no desync line"))


def main(run, machine, only=None):
    work = os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT)
    runs, scratch = f"{work}/port/runs/{run}", f"{work}/port/scratch/stat-pack/{run}"
    car = f"{work}/extracted/GFZE01/files/game/cardata.lz"

    def tool(*command):
        return subprocess.run([sys.executable, *command], capture_output=True, text=True)

    def compare(replays):
        return tool(f"{here}/../replay-compare.py", *replays)

    def weights(race, pack, of):
        return [tool(f"{here}/../runs/stat-pack.py", "weights", f"{runs}-{race}-{i}/trace.csv.states", f"{scratch}-{pack}.json", car, str(of)) for i in (1, 2)]

    def playbacks(name):
        return [game_log(f"{work}/port/runs/{name.format(i=i)}") for i in (1, 2)]
    report = Report()
    packs = {}
    for name in ("a", "b", "w", "real"):
        if not os.path.exists(f"{scratch}-{name}.json"):
            print(f"stat packs {run}: FAIL (no pack {scratch}-{name}.json: stat-pack-run.sh makes them)")
            return 1
        with open(f"{scratch}-{name}.json", encoding="utf-8") as f:
            packs[name] = json.load(f)
    imported = re.search(r"fingerprint: ([0-9a-f]{40})", text(f"{scratch}.import.log"))
    report.say(bool(imported) and imported[1] == packs["a"]["fingerprint"],
               "the launcher's import of pack A: " + (f"fingerprint {imported[1][:8]}, stat-pack.py's {packs['a']['fingerprint'][:8]}"
                                                     if imported else "no fingerprint line in the import's log"))
    # (two recordings are compared over the steps both hold: each game stops when its own player leaves the results;
    # 6: the machine of Quick Play's second launcher, whose weight stat-pack-run.sh has the whole pack change)
    parts = {
        "plain": lambda: plain(report, runs, "nmj", tool(f"{here}/run-summary.py", "nmj", f"{run}-plain")),
        "plain2": lambda: plain_pair(report, runs, compare([f"{runs}-plain2-{i}/race.fzrp" for i in (1, 2)]), playbacks(f"pbs-{run}-plain2-{{i}}")),
        "old": lambda: old(report, text(f"{scratch}.old.txt").split(), playbacks(f"pbo-{run}-{{i}}")),
        "pack": lambda: same(report, runs, packs["a"], compare, weights("pack", "a", machine), playbacks(f"pb-{run}-pack-{{i}}")),
        "two": lambda: differ(report, runs, [packs["a"], packs["b"]], compare([f"{runs}-two-{i}/race.fzrp" for i in (1, 2)]),
                              text(f"{work}/port/scratch/pair/{run}-two.server.log")),
        "server": lambda: (served(report, runs, packs["w"], text(f"{work}/port/scratch/qp/{run}-srv.server.log")),
                           same(report, runs, packs["w"], compare, weights("srv", "w", 6), playbacks(f"pb-{run}-srv-{{i}}-1"), race="srv")),
        "real": lambda: same(report, runs, packs["real"], compare, weights("real", "real", machine), playbacks(f"pb-{run}-real-{{i}}"), race="real"),
        "refused": lambda: refused(report, runs),
    }
    if only is not None and only not in parts:
        print(f"stat packs {run}: FAIL (no part {only}: the parts are {', '.join(parts)})")
        return 1
    for name, judge in parts.items():
        if only in (None, name):
            judge()
    print("\n".join(report.lines))
    print(f"stat packs {run}{f' ({only} only)' if only else ''}: " + ("PASS" if report.failed == 0 else f"FAIL ({report.failed} of {report.checks})"))
    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    words = sys.argv[1:]
    part = None
    if "--only" in words[:-1]:
        at = words.index("--only")
        part, words = words[at + 1], words[:at] + words[at + 2:]
    if len(words) not in (1, 2):
        sys.exit(__doc__)
    sys.exit(main(words[0], int(words[1]) if len(words) == 2 else 6, part))
