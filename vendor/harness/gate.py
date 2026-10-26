"""The exactness gates, applied to two runs' logs and memory dumps as the manifest defines them.

Lifted from the first project's cmp.py (hashes per field), cmprf.py (hashes per step, for configurations where
display timing is free), ramdiff.py and dcnoise.py (words of whole-memory dumps, less the noise regions) and
ramregions.py (clusters, for naming noise). The compared ranges, noise and thresholds come from the manifest.

Nothing here runs the game: these functions read files.
"""
from __future__ import annotations

import os
import re
import struct

import deadstack
import probelog

MEM1 = 0x80000000
CHUNK = 0x10000


# ---- hashes ----------------------------------------------------------------------------------------------------------

def hash_by_field(a: list[dict], b: list[dict], column: str, step: str | None = None, from_step: int | None = None
                  ) -> dict:
    """Rows matched by field index (cmp.py). With `from_step`, fields before it in either run are counted apart."""
    a = [r for r in a if r.get(column)]
    b = [r for r in b if r.get(column)]
    n = min(len(a), len(b))
    idx = list(range(n))
    before = 0
    if from_step is not None and step:
        early = [i for i in idx if int(a[i][step]) < from_step or int(b[i][step]) < from_step]
        before = sum(1 for i in early if a[i][column] != b[i][column])
        idx = [i for i in idx if i not in set(early)]
    bad = [i for i in idx if a[i][column] != b[i][column]]
    out = {"column": column, "by": "field", "compared": len(idx), "differing": len(bad),
           "first": bad[0] if bad else None, "before": before}
    if not idx:
        out["text"] = f"{column}: NO FIELDS IN COMMON"
        out["differing"] = max(1, len(bad))
    elif not bad:
        out["text"] = f"{column}: identical over {len(idx)} fields"
    else:
        where = f" (step {a[bad[0]][step]}/{b[bad[0]][step]})" if step else ""
        out["text"] = (f"{column}: first differs at field {bad[0]}{where}; equal in {len(idx) - len(bad)}/{len(idx)}")
    if before:
        out["text"] += f"; before step {from_step}, {before} field(s) differ (not gated)"
    return out


def hash_by_step(a: list[dict], b: list[dict], column: str, step: str, from_step: int = 1) -> dict:
    """Rows matched by step counter: the first field that shows each step (cmprf.py). A shifted start is
    reported, not failed; fields before `from_step` are compared per field and only counted."""
    a = [r for r in a if r.get(column)]
    b = [r for r in b if r.get(column)]

    def start(rows):
        return next((i for i, r in enumerate(rows) if int(r[step]) >= from_step), None)

    def by_step(rows):
        d: dict[int, str] = {}
        for r in rows:
            if int(r[step]) >= from_step:
                d.setdefault(int(r[step]), r[column])
        return d

    sa, sb, fa, fb = start(a), start(b), by_step(a), by_step(b)
    common = sorted(set(fa) & set(fb))
    bad = [k for k in common if fa[k] != fb[k]]
    n = min(sa if sa is not None else len(a), sb if sb is not None else len(b), len(a), len(b))
    before = sum(1 for i in range(n) if a[i][column] != b[i][column])
    shift = None if sa is None or sb is None or sa == sb else sb - sa
    if not common:
        verdict, differing = "NO STEPS IN COMMON", 1
    elif bad:
        verdict, differing = f"STEPS DIFFER from step {bad[0]} ({len(bad)} of {len(common)})", len(bad)
    else:
        verdict, differing = "steps equal", 0
    text = f"{column} by step: {verdict} ({len(common) - len(bad)} of {len(common)})"
    if shift:
        text += f"; start shifted by {shift:+d} field(s)"
    text += f"; before the start {before} of {n} fields differ (not gated)"
    return {"column": column, "by": "step", "compared": len(common), "differing": differing,
            "first": bad[0] if bad else None, "before": before, "shift": shift, "text": text}


# ---- memory ----------------------------------------------------------------------------------------------------------

def diff_words(path_a: str, path_b: str) -> tuple[list[int], dict[int, tuple[int, int]]]:
    """Guest addresses of the 32-bit words that differ between two memory dumps, and their two values."""
    out: list[int] = []
    values: dict[int, tuple[int, int]] = {}
    with open(path_a, "rb") as fa, open(path_b, "rb") as fb:
        base = 0
        while True:
            ca, cb = fa.read(CHUNK), fb.read(CHUNK)
            n = min(len(ca), len(cb)) & ~3
            if n == 0:
                break
            if ca[:n] != cb[:n]:
                for o in range(0, n, 4):
                    if ca[o:o + 4] != cb[o:o + 4]:
                        address = MEM1 + base + o
                        out.append(address)
                        values[address] = (struct.unpack_from(">I", ca, o)[0], struct.unpack_from(">I", cb, o)[0])
            base += n
            if len(ca) < CHUNK or len(cb) < CHUNK:
                break
    return out, values


def outside(addresses: list[int], within: list[tuple[int, int]] | None, words: set[int],
            ranges: list[tuple[int, int]]) -> list[int]:
    """The differing words a memory gate counts: inside `within` (when given), not noise."""
    out = []
    for a in addresses:
        if within is not None and not any(s <= a < e for s, e in within):
            continue
        if a in words or any(s <= a < e for s, e in ranges):
            continue
        out.append(a)
    return out


def clusters(addresses: list[int], gap: int = 0x100) -> list[tuple[int, int, int]]:
    """(first, last, words) for runs of differing words closer than `gap` (ramregions.py)."""
    out: list[list[int]] = []
    for a in sorted(addresses):
        if out and a - out[-1][1] < gap:
            out[-1][1] = a
            out[-1][2] += 1
        else:
            out.append([a, a, 1])
    return [tuple(c) for c in out]


def by_region(manifest, addresses: list[int]) -> dict[str, int]:
    """How many of the words lie in each labelled part of memory (ramdiff.py's summary)."""
    counts: dict[str, int] = {}
    for a in addresses:
        label = manifest.label(a)
        key = label.split("+")[0] if label else "unlabelled"
        counts[key] = counts.get(key, 0) + 1
    return counts


def dump_path(manifest, run_dir: str, step: int) -> str:
    suffix = manifest.table("probe").get("dump_suffix", ".step{step}.ram")
    return os.path.join(run_dir, probelog.LOG_NAME + suffix.format(step=step))


# ---- applying the manifest's gates -----------------------------------------------------------------------------------

def apply(manifest, run_a: str, run_b: str, against: str, configuration: str, scene_name: str,
          show: int = 6) -> tuple[bool, list[str]]:
    """Every gate the manifest defines for this configuration, scene and kind of comparison.

    `run_a` is the run compared with (the reference's, the first of two, or the build before); `run_b` the run
    under test. Returns (passed, report lines)."""
    scene = manifest.scene(scene_name)
    gates = manifest.gates(configuration, scene=scene_name, against=against)
    lines = [f"== {os.path.basename(run_b.rstrip('/'))} against {os.path.basename(run_a.rstrip('/'))} "
             f"({against}; {configuration}; scene {scene_name})"]
    if not gates:
        lines.append("  NO GATE is defined for this comparison: nothing is proven")
        return False, lines
    passed = True
    cols = probelog.Columns(manifest)
    rows_a = rows_b = None
    diffs: dict[int, tuple[list[int], dict]] = {}
    for g in gates:
        limit = g["max_differing"]
        if g["kind"] == "hash":
            if rows_a is None:
                rows_a = probelog.read(os.path.join(run_a, probelog.LOG_NAME))
                rows_b = probelog.read(os.path.join(run_b, probelog.LOG_NAME))
            step = cols.step()
            from_step = scene.get("compare_from_step")
            for column in g["hashes"]:
                if g["by"] == "step":
                    r = hash_by_step(rows_a, rows_b, column, step, from_step if from_step is not None else 1)
                else:
                    r = hash_by_field(rows_a, rows_b, column, step, from_step)
                ok = r["differing"] <= limit
                passed &= ok
                lines.append(f"  {'PASS' if ok else 'FAIL'}  {g['name']}: {r['text']}")
        else:
            steps = scene.get("dump_steps", [])
            if not steps:
                lines.append(f"  SKIP  {g['name']}: scene '{scene_name}' has no dump_steps")
                continue
            within = [manifest.region(x) for x in g["within"]] if g.get("within") else None
            words, ranges = manifest.noise(g.get("ignore", []), configuration, scene_name)
            named = manifest.named_noise(g.get("pass_named", []), configuration, scene_name)
            for s in steps:
                pa, pb = dump_path(manifest, run_a, s), dump_path(manifest, run_b, s)
                if not (os.path.exists(pa) and os.path.exists(pb)):
                    passed = False
                    lines.append(f"  FAIL  {g['name']} at step {s}: a dump is missing "
                                 f"({os.path.basename(pa if not os.path.exists(pa) else pb)})")
                    continue
                if s not in diffs:
                    diffs[s] = diff_words(pa, pb)
                all_diff, values = diffs[s]
                counted = outside(all_diff, within, words, ranges)
                dead = []
                if g.get("dead_stacks") and counted:
                    with open(pa, "rb") as fa, open(pb, "rb") as fb:
                        dead, counted = deadstack.dead_in_both(counted, fa.read(), fb.read())
                # Noise that passes by name: said in the line, never silently. A word in none of the sets fails.
                by_name = []
                for name, n_words, n_ranges in named:
                    rest = outside(counted, None, n_words, n_ranges)
                    if len(rest) < len(counted):
                        by_name.append(f"{name} ({len(counted) - len(rest)} words)")
                    counted = rest
                ok = len(counted) <= limit
                passed &= ok
                scope = "+".join(g["within"]) if g.get("within") else "whole memory"
                lines.append(f"  {'PASS' if ok else 'FAIL'}  {g['name']} at step {s}: {len(all_diff)} differing "
                             f"words in all; {len(counted)} in {scope} outside the noise (limit {limit})" +
                             (f"; {len(dead)} below a thread's stack pointer (dead stack)" if dead else "") +
                             (f"; {'pass, ' if ok else ''}noise: {', '.join(by_name)}" if by_name else ""))
                for a in counted[:show]:
                    va, vb = values[a]
                    label = manifest.label(a)
                    lines.append(f"          0x{a:08X}{' ' + label if label else ''}: {va:08x} vs {vb:08x}")
                if len(counted) > show:
                    lines.append(f"          ... and {len(counted) - show} more")
    lines.append(f"  {'EXACT' if passed else 'NOT EXACT'} by {len(gates)} gate(s)")
    return passed, lines


_PAIR = re.compile(r"^== (\S+) against (\S+) ")
_NAMED = re.compile(r"noise: (.+)$")


def named_noise_tally(lines: list[str]) -> list[str]:
    """How often each noise set that passes by name occurred, from the report lines of several pairs (`apply`):
    in how many of the pairs, and with how many words. One line per set; none when no set occurred."""
    pairs = 0
    seen: dict[str, dict[str, list[int]]] = {}       # set -> pair -> word counts
    pair = ""
    for line in lines:
        head = _PAIR.match(line)
        if head:
            pairs += 1
            pair = f"{head.group(1)} against {head.group(2)}"
            continue
        found = _NAMED.search(line) if " at step " in line else None
        for part in (found.group(1).split(", ") if found else []):
            m = re.fullmatch(r"(\S+) \((\d+) words\)", part)
            if m:
                seen.setdefault(m.group(1), {}).setdefault(pair, []).append(int(m.group(2)))
    out = []
    for name in sorted(seen):
        counts = [n for per_pair in seen[name].values() for n in per_pair]
        span = f"{min(counts)}" if min(counts) == max(counts) else f"{min(counts)} to {max(counts)}"
        out.append(f"named noise '{name}': in {len(seen[name])} of {pairs} pair(s), {span} words: " +
                   ", ".join(p.split(" against ")[0] for p in seen[name]))
    return out


def noise_report(manifest, pairs: list[tuple[str, str]], configuration: str, scene_name: str,
                 known: list[str] | None = None) -> list[str]:
    """Clusters of words that differ between runs that should be equal, less the noise already declared.

    For establishing the noise floor: run the reference against itself, and give the pairs here. What is printed
    is what a noise entry must cover, or what must be explained."""
    scene = manifest.scene(scene_name)
    names = known if known is not None else [n["name"] for n in manifest.entries("exactness.noise")]
    words, ranges = manifest.noise(names, configuration, scene_name)
    seen: dict[int, int] = {}
    total = 0
    for run_a, run_b in pairs:
        for s in scene.get("dump_steps", []):
            pa, pb = dump_path(manifest, run_a, s), dump_path(manifest, run_b, s)
            if not (os.path.exists(pa) and os.path.exists(pb)):
                continue
            total += 1
            for a in diff_words(pa, pb)[0]:
                seen[a] = seen.get(a, 0) + 1
    new = outside(sorted(seen), None, words, ranges)
    lines = [f"{len(seen)} distinct differing words over {total} dump pair(s) ({configuration}; scene {scene_name}); "
             f"{len(seen) - len(new)} inside declared noise, {len(new)} outside"]
    if total == 0:
        lines.append("no dump pairs found: nothing was compared")
    for first, last, n in clusters(new):
        label = manifest.label(first) or "unlabelled"
        lines.append(f"  0x{first:08X}-0x{last + 3:08X} {n:6d} words  {label}")
    if new:
        lines.append("as manifest ranges (name what each is before adding it):")
        lines.append("  ranges = [" + ", ".join(f"{{ start = 0x{f:08X}, end = 0x{l + 4:08X} }}"
                                                 for f, l, _ in clusters(new)) + "]")
    return lines
