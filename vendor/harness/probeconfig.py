"""The probe's configuration file, written from the manifest for each run (docs/probe.md).

The probe takes this file in place of addresses compiled into the runtime. Addresses are resolved here, so the
probe knows nothing of modules or sections; a range that follows a guest pointer stays a pointer, for the probe
to follow at each field.
"""
from __future__ import annotations

CONFIG_VERSION = 1


def _hex(n: int) -> str:
    return f"0x{n:08X}"


def _range(manifest, r: dict) -> dict:
    if "pointer" in r:
        return {"pointer": _hex(manifest.resolve(r["pointer"])), "offset": r.get("offset", 0), "size": r["size"]}
    start, end = manifest.resolve_range(r)
    return {"start": _hex(start), "size": end - start}


def probe_config(manifest, scene: str | None = None, hashes: bool = True) -> dict:
    m = manifest
    probe = m.table("probe")
    exact = m.table("exactness")
    out: dict = {"version": CONFIG_VERSION, "game": m.game_id}
    if exact.get("step_counter") is not None:
        out["step_counter"] = {"address": _hex(m.resolve(exact["step_counter"])), "width": 4}
    out["modules"] = [{"name": x["name"], "base_pointer": _hex(x["base_pointer"]), "expect_base": _hex(x["load_address"])}
                      for x in m.entries("module") if x.get("base_pointer") and x.get("load_address")]
    out["values"] = [{"name": v["name"], "address": _hex(m.resolve(v["at"])), "width": v["width"]}
                     for v in m.entries("probe.value")]
    out["hashes"] = []
    if hashes:
        for h in m.entries("probe.hash"):
            words, ranges = m.noise(h.get("zero", []), scene=scene)
            zero = [{"start": _hex(w), "size": 4} for w in sorted(words)]
            zero += [{"start": _hex(s), "size": e - s} for s, e in ranges]
            out["hashes"].append({"name": h["name"], "ranges": [_range(m, r) for r in h["ranges"]], "zero": zero})
    if m.entries("probe.timer"):
        timers: dict = {"call": _hex(m.resolve(probe["timer_call"])), "return": _hex(m.resolve(probe["timer_return"])),
                        "functions": [{"name": t["name"], "entry": _hex(m.resolve(t["entry"]))}
                                      for t in m.entries("probe.timer")]}
        for key in ("timer_call_word", "timer_return_word"):
            if key in probe:
                timers[key[6:]] = _hex(probe[key])
        out["timers"] = timers
    if probe.get("trace_calls"):
        out["trace"] = {"calls": probe["trace_calls"], "frame_end": probe.get("trace_frame_end", "")}
    if probe.get("select_value"):
        out["select"] = {"value": probe["select_value"], "equals": probe["select_equals"]}
    sc = m.scene(scene) if scene else {}
    out["dumps"] = {"at": probe.get("dump_at", "first-timer-call-of-step"),
                    "steps": sc.get("dump_steps", []) if hashes else [],
                    "suffix": probe.get("dump_suffix", ".step{step}.ram"),
                    "memory": {"start": _hex(0x80000000), "size": m.mem1_size}}
    if sc.get("input"):
        out["input"] = sc["input"]
    return out
