#!/usr/bin/env python3
"""recomp.py: the kit's harness. Every command reads the game's manifest and this PC's machine file.

  recomp.py [--manifest FILE] [--machine FILE] [--dry-run] COMMAND ...

  run RUN --scene S (--build B | --reference) [--config C] [--fields N] [--arg=ARG]...
                                           one muted, labelled, bounded run with the probe
  time RUN...                              the result table for finished runs
  gate RUN --against RUN2 [--kind reference|self|previous]
                                           the manifest's gates on two finished runs

(The gates' copy carries these three commands alone: recomp-kit's others, doctor, cleanup, build, emit, pgo, batch,
long, noise, profile, census, trace, bisect and roots, were taken out; vendor/harness/README.md.)

--dry-run prints every step and command a command would carry out, and touches nothing.
The manifest and machine file also come from RECOMP_MANIFEST and RECOMP_MACHINE. See docs/harness.md.
"""
from __future__ import annotations

import argparse
import contextlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "manifest"))

import actions  # noqa: E402
import locks  # noqa: E402
from actions import Context, HarnessError, RunSpec  # noqa: E402
from machine import Machine, MachineError  # noqa: E402
from manifest import Manifest, ManifestError  # noqa: E402


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="recomp.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=os.environ.get("RECOMP_MANIFEST"))
    ap.add_argument("--machine", default=os.environ.get("RECOMP_MACHINE"))
    ap.add_argument("--dry-run", action="store_true")
    sub = ap.add_subparsers(dest="command", required=True)

    def scene_config(p, scene_required=False):
        p.add_argument("--scene", required=scene_required)
        p.add_argument("--config")

    p = sub.add_parser("run")
    p.add_argument("run")
    scene_config(p, scene_required=True)
    who = p.add_mutually_exclusive_group(required=True)
    who.add_argument("--build")
    who.add_argument("--reference", action="store_true")
    p.add_argument("--fields", type=int)
    p.add_argument("--label")
    p.add_argument("--no-hash", action="store_true", help="no hashes and no dumps")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--env", action="append", default=[], metavar="K=V")
    p.add_argument("--arg", action="append", default=[], metavar="ARG",
                   help="one more argument for the runner, after the scene's own; repeat it, and write --arg=--name "
                        "for one that begins with a dash. {work} and {run} stand for the work and run folders")
    p.add_argument("--max-seconds", type=int, default=900,
                   help="stop the run after this long even if its log is short (a boot that may hang)")
    p.add_argument("--not-timing", action="store_true",
                   help="the run is not a measurement: ask for CPU with BUILD.wanted instead of taking TIMING.lock")

    p = sub.add_parser("time")
    p.add_argument("runs", nargs="+")

    p = sub.add_parser("gate")
    p.add_argument("run")
    p.add_argument("--against", required=True, metavar="RUN2")
    p.add_argument("--kind", choices=["reference", "self", "previous"], default="reference")
    scene_config(p)

    return ap


def pairs(items: list[str]) -> dict[str, str]:
    out = {}
    for item in items:
        if "=" not in item:
            raise HarnessError(f"'{item}' is not K=V")
        k, v = item.split("=", 1)
        out[k] = v
    return out


def main(argv: list[str], say=print) -> int:
    extra: list[str] = []
    if "--" in argv:                      # (only recomp-kit's build and emit took arguments after --)
        cut = argv.index("--")
        argv, extra = argv[:cut], argv[cut + 1:]
    args = parser().parse_args(argv)
    try:
        if extra:
            raise HarnessError(f"'{args.command}' takes no arguments after --")
        if not args.manifest:
            raise HarnessError("no manifest: give --manifest or set RECOMP_MANIFEST")
        if not args.machine:
            raise HarnessError("no machine file: give --machine or set RECOMP_MACHINE")
        manifest = Manifest.load(args.manifest)
        errors, _ = manifest.validate()
        if errors:
            raise HarnessError(f"{args.manifest} is not valid ({len(errors)} error(s)); run tools/manifest/validate.py")
        ctx = Context(manifest, Machine.load(args.machine), args.dry_run, say)
        return dispatch(ctx, args)
    except (HarnessError, ManifestError, MachineError, RuntimeError) as e:
        say(f"recomp.py: {e}")
        return 1


def dispatch(ctx: Context, a) -> int:
    work = ctx.machine["work"]
    dry = ctx.dry_run
    mc = ctx.machine

    @contextlib.contextmanager
    def quiet(what, seconds):
        give_up = locks.QUIET_GIVE_UP if locks.is_timing_agent() else None
        with locks.quiet(work, what, seconds, say=ctx.say, give_up=give_up, dry_run=dry) as held:
            ctx.lock = held
            try:
                yield held
            finally:
                ctx.lock = None

    @contextlib.contextmanager
    def heavy(what, seconds):
        with locks.heavy(work, what, seconds, say=ctx.say, dry_run=dry) as held:
            ctx.lock = held
            try:
                yield held
            finally:
                ctx.lock = None

    def run_seconds(fields) -> float:
        return (fields or 2000) * mc["run_seconds_per_field"] + 120
    cmd = a.command

    if cmd == "run":
        config = a.config or ctx.manifest.primary_configuration()["name"]
        spec = RunSpec(run=a.run, scene=a.scene, build=a.build, configuration=config, fields=a.fields, label=a.label,
                       hashes=not a.no_hash, headless=a.headless, env=sorted(pairs(a.env).items()),
                       max_seconds=a.max_seconds, args=a.arg)
        steps = actions.run(ctx, spec)
        with (heavy if a.not_timing else quiet)(f"run {a.run}", run_seconds(a.fields or ctx.manifest.scene(a.scene).get("fields"))):
            actions.carry_out(ctx, steps)
        return 0

    if cmd == "time":
        ctx.manifest.require("time")
        if dry:
            ctx.say("would read: " + ", ".join(f"{ctx.machine.p(ctx.machine.run(r))}/probe.csv" for r in a.runs))
            return 0
        for line in actions.times(ctx, a.runs):
            ctx.say(line)
        return 0

    if cmd == "gate":
        ctx.manifest.require("gate")
        if dry:
            info = actions.run_info(ctx, a.run)
            config, scene = a.config or info.get("configuration", "?"), a.scene or info.get("scene", "?")
            ctx.say(f"would compare {a.run} with {a.against} ({a.kind}; {config}; scene {scene}) by the gates: " +
                    (", ".join(g["name"] for g in ctx.manifest.gates(config, scene=scene, against=a.kind)) or "none"))
            return 0
        ok, lines = actions.gate(ctx, a.run, a.against, a.kind, a.config, a.scene)
        for line in lines:
            ctx.say(line)
        return 0 if ok else 1

    raise HarnessError(f"unknown command {cmd}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
