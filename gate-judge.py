#!/usr/bin/env python3
#!/usr/bin/env python3
"""gate-judge.py KIND ...: the judges of the port's gates (the port handbook, "What must hold"): what a run must have
left behind to count as a game that ran and ended as it should. Reads files only, so every judge can be run again
on the folders of an earlier run (gates.sh --judge-only), and on made-up logs (port/gates/tests).

  game RUN [--end results|desync|stop|any] [--log FILE] [--must probe pace]   one game's folder <work>/port/runs/RUN
  runs NAME...          every folder <work>/port/runs/NAME (shell patterns): no crash line, not frozen. A JIT
                        reference run (the harness's run.json says so) may have an empty log, and is counted
  pair RUN [--log FILE --playbacks K --short N]           RUN-1 and RUN-2: each game, and their recordings as one race.
                        --short N: the host's rule ended the race with game N's own seat still racing: every game's
                        log names one step the race was over before, the same one, and that seat has no finish and
                        is not out in every recording
  desync RUN [--altered STEP --log FILE]                  a difference made on purpose in game 2 before STEP: the
                        relay, which only observes, found it within 60 steps; nobody was disconnected, nothing was
                        repaired; both games raced on to their own finish; the recordings differ from STEP on
  quickplay RUN --launchers N --races K [--log FILE]      every launcher of every race (quickplay-run.sh)
  mixed RUN... [--log FILE --builds N]                    games of different builds in one race (runs/mixed-run.sh),
                        every run named: each game ran the build its launcher folder held (its recording's header
                        says the module and the image), N builds at least (2); inputs and checksums equal at every
                        step, or the first step that differs with both games' builds; and each game's lag, forced
                        rollbacks at every depth asked, the start, a seat on the wall and a seat across the line
  playback RUN FILE [--limit S]                           one playback of replay-check.sh: its result line; with a
                        pacing log in its folder (RUN_ENV), a destination of screen copies that got two sizes, or
                        a game that spun without idling, is a FAIL
  playbacks --log FILE --expect N [--control] [--copies RUN...]   the result lines of a row's playbacks; --copies:
                        each of these playbacks must have left a pacing log with screen copies, one size a destination;
                        --undo-check: each of these played with debug.undoLog "both", and its log says the guard went
                        on and the undo log was the same as every page compared at every step it checked
  pieces RUN...         the pieces of code that failed their check

A game passes when (0) it booted once (a second boot is a game that reset itself: RESET, with the field and the race
frame), (1) no log of it holds a crash line ("[staticrecomp] unknown guest instruction", "[zero-access]"),
(2) its probe does not end frozen: fields more than 0.25 s apart for its last 15 s or more, which is a process that
lives and no longer plays, (3) it ended as asked: --end results, the core's "the player left the results; stopping";
desync, "the relay disconnected this game; stopping"; stop, launcher-run.sh's "exited ... after the stop command"
(in --log or the folder's end.txt), and (4) in its pacing log every destination of a copy out of the frame buffer
got one size only (the crash of 2026-10-06 began with full-screen copies into the six 128x128 portraits), and (5) its
pacing log has no row of 10 or more race fields in which the CPU thread did not idle (a game waiting on the graphics
side: the reset of 2026-10-06 and every crashed or frozen game of that day have one).
A check whose file is not there was not made, and the judge says so: "no probe: freeze not checked", "no pacing
log: copies not checked" (or one that holds no copy), "its pacing log counts no idles: spin not checked". Where
the run's script always writes the file (--must; the
games of pair, desync and quickplay) its absence is a failure.
The recordings of one race pass when every file holds steps, ends on a whole step and holds the same results, and
inputs and checksums are equal over the steps all hold. Lengths may differ (each game records until its own player
leaves the results), only when every game logged that its player left: each game by 372 steps at most after the step
its log says its results could first be left from (two presses of the pad script: the first does not always leave; when that is depends on the
racer's standing), or, for a build that does not log that step, by 360 steps at most across the games. A recording
cut short has no results, or is too short, or ends inside a step.
A playback with no summary line is "did not finish: N of M steps" (N: the last step its log reports), never a pass
and never a count of differing steps.

--log FILE: the output of the scripts that made the run (a row's log of gates.sh). Prints a line for each finding
and last "verdict: pass|FAIL|did not finish | figures". Exit status 0, 1, 4 in that order.
  PORT_WORK   the work folder (default: port/setup/work-folder.env's)"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # the judges' modules stand beside this file
# Every name of the judges is reachable here, as it was while they were one file; a test sets base.W, the work
# folder every module reads.
import judge_base as base   # noqa: E402,F401
from judge_base import *   # noqa: E402,F401,F403
from judge_game import *   # noqa: E402,F401,F403
from judge_playback import *   # noqa: E402,F401,F403
from judge_race import *   # noqa: E402,F401,F403
from judge_mixed import *   # noqa: E402,F401,F403

base.W = os.environ.get("PORT_WORK", base.W)   # read here, the program, and nowhere in the judges' modules


def main(argv):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="kind", required=True)

    def kind(name, *arguments):
        s = sub.add_parser(name)
        for flags, options in arguments:
            s.add_argument(*flags.split(), **options)

    run, log, names = ("run", {}), ("--log", {}), ("names", dict(nargs="+"))
    count = lambda flag, default: (flag, dict(type=int, default=default))
    kind("game", run, ("--end", dict(default="any", choices=[*ENDS, "stop", "any"])), log,
         ("--must", dict(nargs="*", default=[], choices=WRITTEN)))
    kind("runs", names)
    kind("pair", run, log, count("--playbacks", 0), count("--short", 0))
    kind("desync", run, count("--altered", 1500), log)
    kind("quickplay", run, count("--launchers", 2), count("--races", 2), log)
    kind("mixed", names, log, count("--builds", 2))
    kind("playback", run, ("file", {}), count("--limit", 0))
    kind("playbacks", ("--log", dict(required=True)), ("--expect", dict(type=int, required=True)),
         ("--control", dict(action="store_true")), ("--copies", dict(nargs="*", default=[])),
         ("--undo-check", dict(nargs="*", default=[])))
    kind("pieces", names)
    a = p.parse_args(argv)
    v = Verdict()
    status = globals()["judge_" + a.kind](a, v)
    return status if a.kind == "playback" else v.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
