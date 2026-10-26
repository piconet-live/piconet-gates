"""What the tests of the gates' judges share: the judge itself, made-up logs, probes and recordings, and a made-up
work folder with the files a game, a launcher's visit and a row leave in it. No game data."""
import contextlib
import importlib.util
import io
import json
import os
import struct
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(HERE, "..", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gj, compare = load("gate-judge"), load("replay-compare")
# powershell.exe for a test: it answers what room-for-games.sh asks (Windows' free commit, in KB: what <folder>/free-kb
# holds when a test wrote one, else 32 GB, with Windows' line end), notes the question in <folder>/asked, and says
# nothing to any other question. No test asks Windows.
WINDOWS = ('#!/bin/bash\nhere=$(dirname "$0")\ncase "$*" in *FreeVirtualMemory*) echo asked >> "$here/../asked"\n'
           '  if [ -e "$here/../free-kb" ]; then cat "$here/../free-kb"; else printf \'33554432\\r\\n\'; fi;; esac\n')


def windows(folder):
    """The stand-in above as FOLDER/bin/powershell.exe; returns FOLDER/bin, to go first in PATH."""
    path = os.path.join(folder, "bin", "powershell.exe")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(WINDOWS)
    os.chmod(path, 0o755)
    return os.path.dirname(path)


def gb(amount):
    """GB as Windows states its free commit: in KB."""
    return str(int(amount * 1024 * 1024))
LEFT = "fzgx: the player left the results; stopping\n"
# a pacing log of one field (it idled 545 times: a native game's log counts idles) and one screen copy
PACE = "F,1,10,0,2,36,5," + ",".join(["0"] * 15) + ",545,0,,,\nE,1,5,1,0,0,0,128,128,5,01235fa0\n"
# the core's line when the race's end is settled, and a race's results with seat 1 short of the line
OVER = "fzgx: the race is over before step {}: every step before it ran with the official inputs\n"
SHORT = {"results": [{"seat": 0, "rank": 0, "finished": True, "out": False, "laps": 1, "timeMs": 45116, "bestLapMs": 45116},
                     {"seat": 1, "rank": 1, "finished": False, "out": False, "laps": 0, "timeMs": None, "bestLapMs": 0}]}
STOP = "fzgx: the race desynced at step 1559 and the relay disconnected this game; stopping\n"
CRASH = "[staticrecomp] unknown guest instruction pc=0x00000008 opcode=0x01000000 last_pc=0x8006dbe0\n"
SUMMARY = ("fzgx: playback: {} of {} steps compared with the recording, {} differed; rollbacks 3 (0 forced), "
           "deepest 2, 5 steps re-simulated\n")
PLAYED = "{}: {}: 60 of 60 steps compared, 0 differed; rollbacks 0 (0 forced), deepest 0: PASS\n"
# what a test server's relay logs when it found a difference and only observed (the server's default)
OBSERVED = ("19:05:18 race m32: desync, checksums differ at frame {}: seat 3 = 0000000A, seat 7 = 0000000B; "
            "no majority of the reporting seats: nobody is told or disconnected\n")


def probe(gaps_us, frames=None):
    """A probe log whose fields are these many microseconds apart."""
    lines, clock = ["field,ticks,module,mode,submode,race_frame,x,qpc_us"], 1000
    for i, gap in enumerate([0, *gaps_us]):
        clock += gap
        lines.append(f"{i},0,801ba660,2,36,{frames[i] if frames else i},0,{clock}")
    return "\n".join(lines) + "\n"


def recording(steps, results=True, sums=None, seats=2, seat=0, said=None):
    """A version 2 replay of made-up steps: inputs i, checksum i (or sums[i]), seen from `seat`. `results`: True
    for made-up ones, or the results themselves (a race's own: {"results": [{"seat", "finished", "out"}, ...]}).
    `said`: more members of its header (what the game says of itself: "module_sha1", "mod_sha1")."""
    header = json.dumps({"engine": "test", "match": {"setup": {"course": 1, "laps": 1}}, **(said or {})}).encode()
    data = b"FZRP" + struct.pack(">HI", 2, len(header)) + header + b"FZRF" + struct.pack(">II", (1 << seats) - 1, seat)
    for i in range(steps):
        data += bytes([i % 251]) * (seats * 6) + struct.pack(">I", sums[i] if sums else i)
    if results:
        tail = json.dumps({"first": 3} if results is True else results).encode()
        data += tail + struct.pack(">I", len(tail)) + b"FZRS"
    return data


def machine_states(step, hits=3, word=None):
    """A record of a game's dump of the machines' state (its "debug.traceStates"): 30 racers of a block and a
    progress record, seat 0 with `hits` wall hits; `word`: (byte, value) put in."""
    racers = bytearray(30 * (0x620 + 0x1FC))
    racers[0x213] = hits
    if word:
        racers[word[0]] = word[1]
    return struct.pack(">IIII", 0x465A5354, step, 0, len(racers)) + bytes(racers)


def verdict(run, *argv):
    """(exit status, everything printed) of gate-judge.py's command line."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        status = gj.main([str(a) for a in (run, *argv)])
    return status, out.getvalue()


class Work:
    """A made-up work folder, and the files a game, a launcher's visit and a row leave in it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(setattr, gj.base, "W", gj.base.W)
        gj.base.W = self.tmp.name

    def write(self, path, content):
        path = os.path.join(self.tmp.name, path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(content, bytes) else "w") as f:
            f.write(content)
        return path

    def game_files(self, run, log=LEFT, gaps=None, pace=PACE):
        self.write(f"port/runs/{run}/fzgx.log", "fzgx: go\n" + log)
        self.write(f"port/runs/{run}/probe.csv", probe(gaps or [16_683] * 300))
        self.write(f"port/runs/{run}/pace.csv", pace)

    def launcher(self, run, i, closed=True, steps=60, standings=("1:finished:100",)):
        door = [{"event": "match", "values": {"match": "m32"}}, {"event": "game", "values": {"state": "running", "match": "m32"}}]
        folder = f"port/runs/{run}-{i}"
        if closed:
            door.append({"event": "game", "values": {"state": "closed", "match": "m32", "standings": list(standings)}})
            self.write(f"{folder}/race1/runner.log", "fzgx: go\n" + LEFT)
            self.write(f"{folder}/race1/probe.csv", probe([16_683] * 300))
            self.write(f"{folder}/race1/pace.csv", PACE)
        else:
            door.append({"event": "failed", "values": {"text": "the visit's time limit is over"}})
            self.write(f"{folder}/runner.log", "fzgx: go\n" + CRASH)
            self.write(f"{folder}/probe.csv", probe([16_683] * 300 + [1_700_000] * 40))
        self.write(f"{folder}/door.jsonl", "".join(json.dumps(e) + "\n" for e in door))
        self.write(f"{folder}/replays/20261006-191326-m32.fzrp", recording(steps, results=closed))

    # a race of two builds (mixed-run.sh): the images and runners the same, the modules OLD and NEW
    IMAGE, RUNNER, OLD, NEW = "1" * 40, "2" * 40, "a" * 40, "b" * 40
    FINISH = {"results": [{"seat": 0, "rank": 1, "finished": False, "out": False}, {"seat": 1, "rank": 0, "finished": True, "out": False}]}
    FORCED = "at_us,step,depth,forced\n1,10,6,1\n2,17,12,1\n3,20,3,0\n"

    def mixed_race(self, run="m", modules=None, sums2=None, said2=None, rollbacks=FORCED, states=None, results=None,
                   log="", relay=""):
        """Run `run` of mixed-run.sh: game 1 on the first module with a lag of 30 ms and its seat on the wall, game
        2 on the second with 90 ms, its seat the AI's; rollbacks asked 6 and 12 deep, the state of step 40 written."""
        record, states = "", states or (machine_states(40), machine_states(40))
        for i, module in enumerate(modules or (self.OLD, self.NEW), 1):
            lag = (30, 90)[i - 1]
            record += (f"{i}\tlauncher-{'old' if module == self.OLD else 'new'}\t{self.IMAGE}/{module}/{self.RUNNER}\t{lag}\t"
                       f"{'wall' if i == 1 else 'ai'}\t-\t" + '{"every":7,"depths":[6,12]}\t40,41\n')
            self.game_files(f"{run}-{i}", log=log or f"fzgx: network session with relay 1.2.3.4:5, input delay 2, test lag {lag} ms\n"
                            "fzgx: go (this game's system time at boot: 0)\n" + LEFT)
            said = said2 if i == 2 and said2 else {"module_sha1": module, "mod_sha1": self.IMAGE}
            self.write(f"port/runs/{run}-{i}/race.fzrp", recording(60, results or self.FINISH, sums2 if i == 2 else None, seat=i - 1, said=said))
            self.write(f"port/runs/{run}-{i}/rb.csv", rollbacks)
            self.write(f"port/runs/{run}-{i}/trace.csv.states", states[i - 1])
        self.write(f"port/scratch/mixed/{run}.games.tsv", record)
        self.write(f"port/scratch/mixed/{run}.server.log", "19:05:17 race m32: go (30 player seats)\n" + relay)

