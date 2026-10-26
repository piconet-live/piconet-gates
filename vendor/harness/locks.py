"""TIMING.lock and BUILD.wanted: how agents share one machine (rules/machine-sharing.md), and how a lock left
behind by an agent that vanished is recognised (rules/interruptions.md).

Two kinds of work:

  quiet()  a timing or gate batch, which needs the machine to itself. It waits while any request file or another
           TIMING.lock exists, then holds TIMING.lock until the batch ends, however it ends.
  heavy()  CPU-heavy work that needs no quiet (a build, a training run). It raises its own request file,
           BUILD.wanted.<agent>, waits until TIMING.lock is gone, works, and takes its request down.

A request file is per agent, so that one agent finishing does not withdraw another's request. Any file whose name
begins with BUILD.wanted counts as a request, the bare BUILD.wanted of the older scripts included.

A lock file's existence is the signal. Its content says who holds it, since when, and until when at the latest:

    owner=<agent>  pid=<n>  host=<name>  what=<command>
    started=<ISO time>  started_epoch=<seconds>
    expected_end=<ISO time>  expected_end_epoch=<seconds>

The request file's lines are the same. A lock is stale when its owner's process is gone (same host), or when it is past its expected end plus a grace
period. Whoever finds a stale lock may remove it, and tells the orchestrator. A lock that is not stale is never
removed by anyone but its owner.

Lifted from the first project's timing-lock.sh, whose locks were empty files: those are given a default life from
their modification time.
"""
from __future__ import annotations

import atexit
import contextlib
import os
import socket
import time

TIMING = "TIMING.lock"
BUILD = "BUILD.wanted"

# Seconds. quiet(): poll BUILD.wanted every 10 s, start anyway after 15 minutes.
#          heavy(): poll TIMING.lock every 20 s, tell the orchestrator after 40 minutes (and keep waiting).
QUIET_POLL, QUIET_GIVE_UP = 10, 900
HEAVY_POLL, HEAVY_WARN = 20, 2400
GRACE = 600                                   # a lock is stale this long after its expected end
DEFAULT_LIFE = {TIMING: 2700, BUILD: 1200}    # for a lock that says nothing: from its modification time


def owner() -> str:
    return os.environ.get("RECOMP_AGENT") or os.environ.get("USER") or "unknown"


def is_timing_agent() -> bool:
    """The project's one timing agent says so in its shell (RECOMP_TIMING_AGENT=1). Only it starts a batch over a
    request that has waited too long; any other agent's timing runs wait for as long as a request stands."""
    return os.environ.get("RECOMP_TIMING_AGENT") == "1"


def request_name(agent: str | None = None) -> str:
    """This agent's request file: BUILD.wanted.<agent>."""
    agent = agent or owner()
    return BUILD + "." + "".join(c if c.isalnum() or c in "_-." else "-" for c in agent)


def requests(folder: str) -> list[str]:
    """Every request file present: BUILD.wanted and BUILD.wanted.<agent>."""
    try:
        return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                      if n.startswith(BUILD) and not n.endswith(".tmp"))
    except OSError:
        return []


def _life(path: str) -> int:
    name = os.path.basename(path)
    return DEFAULT_LIFE[BUILD if name.startswith(BUILD) else TIMING] if (name.startswith(BUILD) or name == TIMING) else 2700


def _stamp(t: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(t))


def write(path: str, what: str, expected_seconds: float, now: float | None = None) -> None:
    now = time.time() if now is None else now
    end = now + expected_seconds
    text = (f"owner={owner()}\npid={os.getpid()}\nhost={socket.gethostname()}\nwhat={what}\n"
            f"started={_stamp(now)}\nstarted_epoch={int(now)}\n"
            f"expected_end={_stamp(end)}\nexpected_end_epoch={int(end)}\n")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def read(path: str) -> dict | None:
    """What a lock file says, or None when it is absent. An empty file gives {} (a lock of the older scripts)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return None
    info: dict = {}
    for line in text.splitlines():          # one key=value per line; the value is the rest of the line
        if "=" in line:
            k, v = line.split("=", 1)
            info[k.strip()] = v.strip()
    return info


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def mine(path: str) -> bool:
    info = read(path)
    return bool(info) and info.get("pid") == str(os.getpid()) and info.get("host") == socket.gethostname()


def stale(path: str, now: float | None = None, grace: float = GRACE, alive=_pid_alive) -> tuple[bool, str]:
    """(is it stale, why). An absent lock is not stale."""
    info = read(path)
    if info is None:
        return False, "absent"
    now = time.time() if now is None else now
    if info.get("host") == socket.gethostname() and info.get("pid", "").isdigit() and not alive(int(info["pid"])):
        return True, f"its owner's process ({info['pid']}) is gone"
    if info.get("expected_end_epoch", "").isdigit():
        end = int(info["expected_end_epoch"])
        source = f"its expected end {info.get('expected_end', '')}"
    else:
        try:
            end = os.path.getmtime(path) + _life(path)
        except OSError:
            return False, "absent"
        source = f"the default life of a lock that names no end ({_life(path) // 60} min)"
    if now > end + grace:
        return True, f"it is {int((now - end) // 60)} minutes past {source}, and the grace is {int(grace // 60)}"
    return False, f"held by {info.get('owner', 'an unnamed owner')} until {info.get('expected_end', 'an unstated time')}"


def describe(path: str) -> str:
    info = read(path)
    if info is None:
        return "absent"
    if not info:
        return "present, names no owner (written by an older script)"
    return (f"owner={info.get('owner', '?')} what={info.get('what', '?')} started={info.get('started', '?')} "
            f"expected_end={info.get('expected_end', '?')} pid={info.get('pid', '?')} host={info.get('host', '?')}")


def remove_stale(folder: str, say=print, now: float | None = None, grace: float = GRACE, alive=_pid_alive,
                 dry_run: bool = False) -> list[str]:
    """Remove TIMING.lock and every request file where stale. Returns the names removed."""
    removed = []
    for path in [os.path.join(folder, TIMING)] + requests(folder):
        name = os.path.basename(path)
        is_stale, why = stale(path, now, grace, alive)
        if not is_stale:
            continue
        say(f"NOTE: {'would remove' if dry_run else 'removed'} stale {name} ({describe(path)}): {why}. "
            "Tell the orchestrator.")
        if not dry_run:
            with contextlib.suppress(OSError):
                os.remove(path)
        removed.append(name)
    return removed


def _take(path: str, what: str, expected_seconds: float) -> bool:
    """Create a lock only if it does not exist (two agents may try at the same moment). True when it is ours."""
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    except FileExistsError:
        return False
    write(path, what, expected_seconds)
    return True


def _remove_if_mine(path: str) -> None:
    if mine(path):
        with contextlib.suppress(OSError):
            os.remove(path)


class Held:
    """A lock this process holds. `extend` moves its expected end later, never earlier."""

    def __init__(self, path: str | None, what: str):
        self.path, self.what = path, what

    def extend(self, seconds_from_now: float) -> None:
        if not self.path or not mine(self.path):
            return
        info = read(self.path) or {}
        want = time.time() + seconds_from_now
        if info.get("expected_end_epoch", "0").isdigit() and want <= int(info["expected_end_epoch"]):
            return
        started = int(info["started_epoch"]) if info.get("started_epoch", "").isdigit() else time.time()
        write(self.path, self.what, want - started, now=started)


@contextlib.contextmanager
def quiet(folder: str, what: str, expected_seconds: float = 1800, say=print, sleep=time.sleep,
          poll: float = QUIET_POLL, give_up: float | None = QUIET_GIVE_UP, warn_after: float = HEAVY_WARN,
          dry_run: bool = False):
    """Hold TIMING.lock for a timing or gate batch.

    It is taken only when no other TIMING.lock and no request file exists. `give_up` is how long the project's
    timing agent waits for requests before it starts anyway and says so; None (any other agent) waits for as long
    as a request stands. Another agent's TIMING.lock is always waited for."""
    timing = os.path.join(folder, TIMING)
    if dry_run:
        say(f"# would remove {timing} or a request file if stale; wait while another {TIMING} or any {BUILD}* exists "
            f"(poll {poll:g} s" + (f", start over a request after {give_up:g} s)" if give_up is not None
                                   else "; never start over a request)"))
        say(f"# would create {timing} (expected to last {expected_seconds / 60:.0f} minutes), and remove it when the "
            "batch ends")
        yield Held(None, what)
        return
    waited = waited_requests = 0.0
    told_lock = told_request = warned = False
    while True:
        remove_stale(folder, say)
        if os.path.exists(timing) and not mine(timing):
            if not told_lock:
                say(f"waiting for {TIMING} to go ({time.strftime('%H:%M:%S')}; {describe(timing)})")
                told_lock = True
        else:
            pending = requests(folder)
            if pending and give_up is not None and waited_requests >= give_up:
                say(f"NOTE: {', '.join(os.path.basename(x) for x in pending)} still present after {give_up / 60:g} "
                    f"minutes; starting the batch anyway ({time.strftime('%H:%M:%S')}). Tell the orchestrator.")
                pending = []
            if not pending:
                if mine(timing) or _take(timing, what, expected_seconds):
                    break
                continue                      # another agent took it this instant: wait for it
            if not told_request:
                say(f"waiting for {', '.join(os.path.basename(x) for x in pending)} to go "
                    f"({time.strftime('%H:%M:%S')}; {describe(pending[0])})")
                told_request = True
            waited_requests += poll
        if waited >= warn_after and not warned:
            say(f"NOTE: still waiting to take {TIMING} after {warn_after / 60:g} minutes. Tell the orchestrator.")
            warned = True
        sleep(poll)
        waited += poll
    atexit.register(_remove_if_mine, timing)
    try:
        yield Held(timing, what)
    finally:
        _remove_if_mine(timing)


@contextlib.contextmanager
def heavy(folder: str, what: str, expected_seconds: float = 600, say=print, sleep=time.sleep,
          poll: float = HEAVY_POLL, warn_after: float = HEAVY_WARN, dry_run: bool = False):
    """Raise this agent's request file for CPU-heavy work, and wait until no timing batch is running."""
    timing, build = os.path.join(folder, TIMING), os.path.join(folder, request_name())
    if dry_run:
        say(f"# would create {build} (expected to last {expected_seconds / 60:.0f} minutes), wait until {timing} is "
            f"absent or stale (poll {poll:g} s), work, then remove {build}")
        yield Held(None, what)
        return
    remove_stale(folder, say)
    if os.path.exists(build) and not mine(build):
        raise RuntimeError(f"{build} exists ({describe(build)}): another process is working under this agent's name. "
                           "Give each agent its own RECOMP_AGENT.")
    write(build, what, expected_seconds)
    atexit.register(_remove_if_mine, build)
    try:
        waited, warned = 0.0, False
        while os.path.exists(timing):
            if waited == 0:
                say(f"waiting for {TIMING} to go ({time.strftime('%H:%M:%S')}; {describe(timing)})")
            if waited >= warn_after and not warned:
                say(f"NOTE: {TIMING} still present after {warn_after / 60:g} minutes. Tell the orchestrator.")
                warned = True
            sleep(poll)
            waited += poll
            if stale(timing)[0]:
                remove_stale(folder, say)
        if waited:                        # the wait used up the time first stated
            write(build, what, expected_seconds)
        yield Held(build, what)
    finally:
        _remove_if_mine(build)


def state(folder: str) -> dict[str, str]:
    """What TIMING.lock and every request file say now, and whether each is stale, for `doctor` and `cleanup`."""
    out = {}
    for path in [os.path.join(folder, TIMING)] + requests(folder):
        if os.path.exists(path):
            is_stale, why = stale(path)
            out[os.path.basename(path)] = f"{describe(path)}; {'STALE: ' + why if is_stale else why}"
    return out
