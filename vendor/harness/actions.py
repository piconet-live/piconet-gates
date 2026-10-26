"""What each harness command does, as a plan of steps.

A command builds its plan from the manifest (the game's facts) and the machine file (this PC's paths), then the
plan is printed (`--dry-run`) or carried out. Each step is lifted from one of the first project's scripts, named
in the step's docstring, and produces the same command lines for the same game.

The runner's own conventions (ModernGekko's command line, how its reference core is asked for) are in RUNNER,
in one place. Nothing here names a game.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable

import gate as gate_mod
import locks
import probelog
import registry
import timing
from probeconfig import probe_config

HERE = os.path.dirname(os.path.abspath(__file__))

# ModernGekko's runner, as the first project drove it.
RUNNER = {
    "fixed_args": ["--mute"],                                  # every test run is muted (working rule 19)
    "reference_env": [("MODERNGEKKO_STATICRECOMP", "0")],      # the runner's own JIT, no native module
    "reference_args": ["--allow-interpreter"],
    "stop_command": "command=stop",
    "screenshot_command": "command=screenshot",
}
KIT_WIN = "kit-win"   # where the kit's Windows scripts are copied to, under the work folder
# launch.ps1's own time limit for a run is its --max-seconds and this much more: the stop command, its 30 s and the
# kill by ID come after the harness's deadline, and the watchdog only ends what this loop could not.
LIMIT_MARGIN = 60
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")


class HarnessError(Exception):
    """A command cannot be carried out as asked."""


@dataclass
class Step:
    what: str                               # one line: what the step does
    detail: list[str] = field(default_factory=list)   # the exact commands or files, for --dry-run
    action: Callable[[], object] | None = None


@dataclass
class Context:
    manifest: object
    machine: object
    dry_run: bool = False
    say: Callable[[str], None] = print
    lock: object = None          # the lock this command holds (locks.Held), so long steps can extend it

    def check_name(self, name: str, what: str = "name") -> str:
        if not NAME.match(name):
            raise HarnessError(f"'{name}' is not a usable {what}: letters, digits, '.', '_' and '-' only")
        return name


def carry_out(ctx: Context, steps: list[Step]) -> None:
    for n, step in enumerate(steps, 1):
        if ctx.dry_run:
            ctx.say(f"{n}. {step.what}")
            for d in step.detail:
                ctx.say(f"     {d}")
        else:
            ctx.say(f"[{time.strftime('%H:%M:%S')}] {step.what}")
            if step.action:
                step.action()


def _under(machine, rel: str) -> str:
    """A folder under the work folder that the harness may delete and recreate."""
    path = os.path.normpath(machine.p(rel))
    root = os.path.normpath(machine["work"])
    if not path.startswith(root + os.sep) or path == root:
        raise HarnessError(f"refusing to touch {path}: it is not inside the work folder {root}")
    return path


def install_win(ctx: Context) -> Step:
    """Windows programs cannot run scripts from this shell's file system: copy the kit's to the work folder, with
    this machine's settings beside them (machine.bat), so no quoted path has to pass through cmd.exe."""
    mc = ctx.machine
    src, dst = os.path.join(HERE, "win"), mc.p(KIT_WIN)
    settings = [("RECOMP_JOBS", str(mc["jobs"])), ("RECOMP_VCVARS", mc["vcvars"]),
                ("RECOMP_CLANG", mc["llvm_bin_win"].rstrip("/\\") + "/clang.exe"),
                ("RECOMP_PATH", ";".join(mc["path_win"]))]

    def act():
        os.makedirs(dst, exist_ok=True)
        for name in sorted(os.listdir(src)):
            shutil.copyfile(os.path.join(src, name), os.path.join(dst, name))
        with open(os.path.join(dst, "machine.bat"), "w", newline="\r\n") as f:
            f.write("@echo off\nrem written by the harness from the machine file\n")
            f.write("".join(f"set {k}={v}\n" for k, v in settings))
    return Step(f"copy the kit's Windows scripts to {dst}",
                [f"cp {src}/* {dst}/", f"write {dst}/machine.bat ({', '.join(k for k, _ in settings)})"], act)


# ---- build -----------------------------------------------------------------------------------------------------------

def manifest_hash(manifest) -> str:
    try:
        with open(manifest.path, "rb") as f:
            return hashlib.sha1(f.read()).hexdigest()
    except OSError:
        return ""


# ---- run -------------------------------------------------------------------------------------------------------------

@dataclass
class RunSpec:
    run: str                      # the run's name (its folder)
    scene: str
    build: str | None             # a build's name, or None for the reference
    configuration: str
    fields: int | None = None
    label: str | None = None
    hashes: bool = True           # False: no hashing and no dumps (a pure timing or long run)
    headless: bool = False
    env: list[tuple[str, str]] = field(default_factory=list)   # extra environment (profile, census, trace)
    module_path: str | None = None    # a module file under the work folder, instead of a build's
    screenshot: bool = True
    max_seconds: int = 900            # the run is stopped after this long, whatever its log says
    args: list[str] = field(default_factory=list)   # further arguments for the runner, after the scene's own


def run_env(ctx: Context, spec: RunSpec) -> list[tuple[str, str]]:
    """The runner's environment for one run, in the order the first project's cg-run.sh gave it."""
    m = ctx.manifest
    scene, config = m.scene(spec.scene), m.configuration(spec.configuration)
    kind = "native" if (spec.build or spec.module_path) else "reference"
    pe = m.probe_env
    env: list[tuple[str, str]] = [(pe("RECOMP_PROBE"), "{run}\\" + probelog.LOG_NAME)]
    if pe("RECOMP_PROBE_CONFIG"):
        env.append((pe("RECOMP_PROBE_CONFIG"), "{run}\\probe.json"))
    if scene.get("input") and pe("RECOMP_PROBE_INPUT"):
        env.append((pe("RECOMP_PROBE_INPUT"), scene["input"]))
    if m.entries("probe.timer") and pe("RECOMP_PROBE_TIMERS"):
        env.append((pe("RECOMP_PROBE_TIMERS"), "1"))
    if not spec.hashes:
        env.append((pe("RECOMP_PROBE_HASH"), "0"))
    elif scene.get("dump_steps"):
        env.append((pe("RECOMP_PROBE_DUMP_STEPS"), ",".join(str(s) for s in scene["dump_steps"])))
    env += sorted((config.get("env") or {}).items())
    env += spec.env
    if kind == "reference":
        env += RUNNER["reference_env"]
    env += [(s["key"], str(s["value"])) for s in m.settings("runner-env", kind)]
    return env


def run_args(ctx: Context, spec: RunSpec) -> list[str]:
    """The runner's command line (launch.ps1's, in its order)."""
    m, mc = ctx.manifest, ctx.machine
    scene = m.scene(spec.scene)
    kind = "native" if (spec.build or spec.module_path) else "reference"
    args = ["--game", mc.w(mc["game"]), "--user-dir", mc.w(mc["user"]), *RUNNER["fixed_args"]]
    for s in m.settings("runner-arg", kind):
        args += [s["key"]] if s["value"] is True else [] if s["value"] is False else [s["key"], str(s["value"])]
    args += ["--automation-dir", mc.w(mc.run(spec.run), "auto")]
    if kind == "native":
        args += ["--module", mc.w(spec.module_path or mc.module_file(spec.build, m.game_id))]
    if spec.headless:
        args.append("--headless")
    if kind == "reference":
        args += RUNNER["reference_args"]
    if scene["reach"] == "savestate":
        args += ["--load-state", mc.w(mc["derived"], scene["state"])]
    elif scene["reach"] == "input-recording":
        raise HarnessError(f"scene '{spec.scene}': reaching a scene by an input recording is not written")
    return args + extra_args(ctx, spec)


def extra_args(ctx: Context, spec: RunSpec) -> list[str]:
    """What a scene or one run adds to the runner's command line (a game's own arguments: the file a race is booted
    from, a switch of its port): the scene's `runner_args`, then the run's `--arg`s. "{work}" and "{run}" stand for
    the work folder and the run's folder as Windows sees them."""
    mc = ctx.machine
    out = []
    for a in list(ctx.manifest.scene(spec.scene).get("runner_args", [])) + list(spec.args):
        a = a.replace("{work}", mc.w()).replace("{run}", mc.w(mc.run(spec.run)))
        if not a or any(c in a for c in '| "'):
            raise HarnessError(f"argument '{a}' cannot be handed to the runner: it is empty, or holds a space, a "
                               "quote or '|' (the launch script splits its list at '|' and does not quote)")
        out.append(a)
    return out


def run_label(ctx: Context, spec: RunSpec) -> str:
    """The window title's prefix: every visible run says what it is (working rule 19)."""
    if spec.label:
        return spec.label
    what = f"NATIVE {spec.build or 'module'}" if (spec.build or spec.module_path) else "REFERENCE"
    return f"[{what}, {spec.configuration}, {spec.scene}]"


def run(ctx: Context, spec: RunSpec) -> list[Step]:
    """One muted, labelled, bounded run with the probe (cg-run.sh, run.sh, launch.sh, launch.ps1, cmd.sh)."""
    m, mc = ctx.manifest, ctx.machine
    m.require("run")
    ctx.check_name(spec.run, "run name")
    scene = m.scene(spec.scene)
    fields = spec.fields or scene.get("fields")
    if not fields:
        raise HarnessError(f"scene '{spec.scene}' gives no length: pass --fields")
    R, RW = mc.p(mc.run(spec.run)), mc.w(mc.run(spec.run))
    env, args = run_env(ctx, spec), run_args(ctx, spec)
    env_text = ";".join(f"{k}={v}" for k, v in env)
    label = f"{run_label(ctx, spec)} {spec.run}"
    launch = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", mc.w(KIT_WIN, "launch.ps1"),
              "-Runner", mc.w(mc["runner"]), "-RunDir", RW, "-Env", env_text, "-ArgList", "|".join(args),
              "-MaxSeconds", str(spec.max_seconds + LIMIT_MARGIN)]
    # One screenshot at the scene's field, to the run's screenshot file; further ones, each to <file>-f<field>.
    shot = mc.w(mc.shot(spec.run))
    shots: list[tuple[int, str]] = []
    if spec.screenshot:
        if scene.get("screenshot_field"):
            shots.append((scene["screenshot_field"], shot))
        stem, dot, ext = shot.rpartition(".")
        shots += [(f, f"{stem}-f{f}{dot}{ext}") for f in scene.get("screenshot_fields", [])]
        shots.sort()
    steps = [install_win(ctx)]

    def prepare():
        shutil.rmtree(_under(mc, mc.run(spec.run)), ignore_errors=True)
        os.makedirs(R)
        if mc["user_pristine"]:
            shutil.copytree(mc.p(mc["user_pristine"]), mc.p(mc["user"]), dirs_exist_ok=True)
        if (spec.build or spec.module_path) and not os.path.exists(
                mc.p(spec.module_path or mc.module_file(spec.build, m.game_id))):
            raise HarnessError(f"no module for build '{spec.build}': build it first")
        if scene["reach"] == "savestate" and not os.path.exists(mc.p(mc["derived"], scene["state"])):
            raise HarnessError(f"scene '{spec.scene}': {mc.p(mc['derived'], scene['state'])} is missing")
        with open(os.path.join(R, "run.json"), "w", encoding="utf-8") as f:
            json.dump({"run": spec.run, "scene": spec.scene, "configuration": spec.configuration,
                       "kind": "native" if (spec.build or spec.module_path) else "reference", "build": spec.build,
                       "fields": fields, "label": label, "game": m.game_id, "manifest": manifest_hash(m),
                       "args": extra_args(ctx, spec),
                       "started": time.strftime("%Y-%m-%d %H:%M:%S")}, f, indent=1)
        if m.probe_env("RECOMP_PROBE_CONFIG"):
            with open(os.path.join(R, "probe.json"), "w", encoding="utf-8") as f:
                json.dump(probe_config(m, scene=spec.scene, hashes=spec.hashes), f, indent=1)
    detail = [f"rm -rf {R}; mkdir -p {R}", f"write {R}/run.json"]
    if mc["user_pristine"]:
        detail.append(f"cp -r {mc.p(mc['user_pristine'])}/* {mc.p(mc['user'])}/")
    if m.probe_env("RECOMP_PROBE_CONFIG"):
        detail.append(f"write {R}/probe.json (the probe's configuration, from the manifest)")
    steps.append(Step(f"prepare run '{spec.run}'", detail, prepare))

    detail = [shlex.join(launch), f"environment: {env_text}", f"label the window: {label}" if not spec.headless
              else "headless: no window",
              f"wait until {R}/{probelog.LOG_NAME} has {fields} lines, or the runner exits (at most {spec.max_seconds} s)",
              f"launch.ps1's watchdog ends the runner {spec.max_seconds + LIMIT_MARGIN} s after its start whatever this "
              f"process does (writing {R}/limit.txt)"]
    for shot_field, shot_path in shots:
        detail.append(f"at field {shot_field}: screenshot to {shot_path}")
    detail += [f"stop: automation command '{RUNNER['stop_command']}', wait up to 30 s, then end the process by its ID",
               f"about {fields * mc['run_seconds_per_field'] / 60 + 0.3:.1f} minutes"]
    steps.append(Step(f"run {fields} fields of scene '{spec.scene}' ({spec.configuration}): {run_label(ctx, spec)}",
                      detail, lambda: _do_run(ctx, spec, launch, label, fields, shots)))
    return steps


def automation(run_dir: str, name: str, lines: list[str], wait: float = 60) -> None:
    """Hand one automation command to a running game atomically (cmd.sh): write elsewhere, then rename. The
    runtime polls the commands folder and rejects a command it reads half-written."""
    commands, staging = os.path.join(run_dir, "auto", "commands"), os.path.join(run_dir, "auto", "staging")
    deadline = time.time() + wait
    while not os.path.isdir(commands):
        if time.time() > deadline:
            raise HarnessError(f"{commands} did not appear: the runner is not polling for commands")
        time.sleep(0.2)
    os.makedirs(staging, exist_ok=True)
    with open(os.path.join(staging, name + ".txt"), "w", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    os.replace(os.path.join(staging, name + ".txt"), os.path.join(commands, name + ".txt"))


def _alive(pid: str, process: str) -> bool:
    out = subprocess.run(["tasklist.exe", "/FI", f"PID eq {pid}"], capture_output=True, text=True).stdout
    return process in out


def _lines(path: str) -> int:
    try:
        with open(path, "rb") as f:
            return f.read().count(b"\n")
    except OSError:
        return 0


def _do_run(ctx: Context, spec: RunSpec, launch: list[str], label: str, fields: int,
            shots: list[tuple[int, str]]) -> None:
    mc = ctx.machine
    R = mc.p(mc.run(spec.run))
    log = os.path.join(R, probelog.LOG_NAME)
    with open(R + ".launch.log", "w") as out:
        subprocess.Popen(launch, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    pid_file = os.path.join(R, "pid.txt")
    for _ in range(60):
        if os.path.exists(pid_file) and os.path.getsize(pid_file):
            break
        time.sleep(0.5)
    else:
        raise HarnessError(f"the runner did not start (see {R}.launch.log)")
    with open(pid_file) as f:
        pid = f.read().strip()
    ctx.say(f"{spec.run} pid={pid} start={time.strftime('%H:%M:%S')}")
    # Registered at once: if this agent vanishes now, `cleanup` can find the process and stop it.
    entry = registry.record(mc["work"], int(pid), mc["runner_process"], label, spec.run, R, locks.owner())
    if ctx.lock is not None:
        ctx.lock.extend(fields * mc["run_seconds_per_field"] + 300)
    if not spec.headless:
        with open(R + ".show.log", "w") as out:
            subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                              mc.w(KIT_WIN, "show.ps1"), "-Id", pid, "-Label", label, "-Title", mc["window_title"]],
                             stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
    deadline, last_alive_check, pending = time.time() + spec.max_seconds, 0.0, list(shots)
    try:
        while time.time() < deadline:
            n = _lines(log)
            while pending and n >= pending[0][0]:
                shot_field, shot_path = pending.pop(0)
                automation(R, f"shot{shot_field}", [RUNNER["screenshot_command"], f"path={shot_path}"])
            if n >= fields:
                break
            if time.time() - last_alive_check > 1:
                last_alive_check = time.time()
                if not _alive(pid, mc["runner_process"]):
                    ctx.say("exited early")
                    break
            time.sleep(0.05 if pending else 0.5)
        else:
            ctx.say(f"stopped after {spec.max_seconds} s with {_lines(log)} of {fields} lines")
    finally:
        # Always stop what was started, and only that: by its own process ID (working rule 18).
        try:
            automation(R, "zz-stop", [RUNNER["stop_command"]], wait=5)
        except HarnessError:
            pass
        for _ in range(30):
            if not _alive(pid, mc["runner_process"]):
                break
            time.sleep(1)
        else:
            ctx.say("force kill")
            subprocess.run(["taskkill.exe", "/PID", pid, "/F"], capture_output=True)
        registry.finish(entry)
    ctx.say(f"{spec.run} end={time.strftime('%H:%M:%S')} lines={_lines(log)}")


# ---- reading runs ----------------------------------------------------------------------------------------------------

def run_info(ctx: Context, run: str) -> dict:
    """What `run` recorded about a run, or {} for a run made by older scripts."""
    try:
        with open(os.path.join(ctx.machine.p(ctx.machine.run(run)), "run.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def gate(ctx: Context, run: str, other: str, against: str, configuration: str | None, scene: str | None
         ) -> tuple[bool, list[str]]:
    """Apply the manifest's gates to two finished runs (cg-gate.sh, cg-dcgate.sh). Reads files only."""
    ctx.manifest.require("gate")
    info = run_info(ctx, run)
    configuration = configuration or info.get("configuration")
    scene = scene or info.get("scene")
    if not configuration or not scene:
        raise HarnessError(f"run '{run}' has no run.json: give --config and --scene")
    mc = ctx.machine
    return gate_mod.apply(ctx.manifest, mc.p(mc.run(other)), mc.p(mc.run(run)), against, configuration, scene)


def times(ctx: Context, runs: list[str]) -> list[str]:
    """The result table for finished runs (tasks.py, itrow.py)."""
    ctx.manifest.require("time")
    mc = ctx.machine
    lines = [timing.header(ctx.manifest)]
    for r in runs:
        rows = probelog.read(os.path.join(mc.p(mc.run(r)), probelog.LOG_NAME))
        lines.append(timing.line(ctx.manifest, r, timing.measure(ctx.manifest, rows, mc["tsc_hz"])))
    lines.append(timing.LEGEND)
    return lines


# ---- batches ---------------------------------------------------------------------------------------------------------

# ---- profile, census, trace ------------------------------------------------------------------------------------------

# ---- train and optimise ----------------------------------------------------------------------------------------------

# ---- bisect ----------------------------------------------------------------------------------------------------------

# ---- closed roots ----------------------------------------------------------------------------------------------------

# ---- doctor ----------------------------------------------------------------------------------------------------------
