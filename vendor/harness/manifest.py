"""The game manifest: schema, loader, address resolution and validation.

One file, `manifest.toml`, tells every kit tool about a game. This module is the single definition of that
format: `docs/manifest.md` carries the reference this module prints (`validate.py --reference`), and the
harness reads a manifest only through `Manifest`.

Standard library only (Python 3.11 or later, for `tomllib`).
"""
from __future__ import annotations

import re
import tomllib

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------------------------------------------
# Schema. Each table is a list of (field, type, required, description).
#
# Types:
#   str, int, bool, number          scalars
#   sha1                            40 hex digits
#   addr                            a guest address: an integer, or "<module>+0xOFF", or "<module>:<section>+0xOFF"
#   range                           {start = addr, size = int} | {start = addr, end = addr} (end exclusive)
#                                   | {pointer = addr, offset = int, size = int} (a guest pointer followed at run time)
#   enum(a|b|c)                     one of the listed strings
#   ref(kind)                       the name of an entry of that kind (module, pin, scene, ...)
#   list(T)                         an array of T
#   table(T)                        a table of string keys to T
#   scalar                          str, int, number or bool
# --------------------------------------------------------------------------------------------------------------

SOURCE = ("source", "str", False,
          "Where the entry's values come from: the note and its section, or the script. Required by `--strict`.")
NOTE = ("note", "str", False, "Anything a reader needs that the fields do not say.")

SCHEMA: dict[str, dict] = {
    "": {
        "doc": "Top level.",
        "fields": [
            ("schema", "int", True, f"Version of this format. This kit reads version {SCHEMA_VERSION}."),
        ],
    },
    "game": {
        "doc": "Identity. One table.",
        "fields": [
            ("id", "str", True, "The six-character game ID from the disc header."),
            ("title", "str", True, "The game's name, for reports."),
            ("region", "enum(NTSC-U|NTSC-J|NTSC-K|PAL)", True, "The disc's region."),
            ("platform", "enum(gamecube|wii)", True, "The console."),
            ("revision", "int", False, "The disc revision, when more than one exists."),
            ("mem1_size", "int", False, "Bytes of main memory. Default 0x1800000 (24 MiB)."),
            ("mem2_size", "int", False, "Bytes of the second memory (Wii). Default 0."),
            ("symbols", "str", False, "Where names for addresses come from (a decompilation and its commit)."),
            NOTE, SOURCE,
        ],
    },
    "reference": {
        "doc": "The reference every result is compared with. One table.",
        "fields": [
            ("emulator", "str", True, "The emulator build that is the reference, with its version."),
            ("core", "str", True, "The reference's CPU core (for example its JIT)."),
            NOTE, SOURCE,
        ],
    },
    "toolchain[]": {
        "doc": "The pinned tools: recompiler, runtime, compiler. One entry per component.",
        "fields": [
            ("name", "str", True, "The component."),
            ("commit", "str", False, "The pinned commit or version."),
            ("branch", "str", False, "The local work branch on top of the pin."),
            ("patches", "str", False, "Where the local changes are exported (a path in the game's repository)."),
            NOTE, SOURCE,
        ],
    },
    "module[]": {
        "doc": "A code module: the executable or a relocatable module. `obtain` says how its bytes are had, "
               "`load` where it runs.",
        "fields": [
            ("name", "str", True, "A short name, used in address expressions (`main.rel:bss+0x50A4`)."),
            ("kind", "enum(dol|rel)", True, "The file format."),
            ("obtain", "enum(executable|disc-file|unpack|memory-dump)", True,
             "`executable`: the boot executable itself. `disc-file`: a plain file on the disc. `unpack`: packed or "
             "encrypted on the disc and unpacked offline by a tool. `memory-dump`: dumped from the reference's "
             "memory after the game's own loader has unpacked and relocated it."),
            ("disc_path", "str", False, "The file in the extracted disc tree (`sys/...` or `files/...`). For a "
                                        "packed module, the packed file."),
            ("sha1", "sha1", False, "SHA-1 of the usable file: the disc file, or the unpacked file for `unpack` "
                                    "and `memory-dump`."),
            ("compile", "bool", True, "Whether the module is part of the native build."),
            ("load", "enum(fixed|runtime)", False,
             "`fixed`: at the addresses in its own header (a DOL). `runtime`: the game loads it at run time. "
             "Default `fixed` for a dol, `runtime` for a rel."),
            ("load_address", "int", False,
             "The address of the module's first byte once loaded. Required for a compiled `runtime` module, "
             "which therefore needs a pin."),
            ("base_pointer", "int", False, "A guest word that holds the module's base at run time; tools read "
                                           "it to check the pin held."),
            ("varies_with", "str", False, "What moves the module when it is not pinned."),
            ("pins", "list(ref(pin))", False, "The pins that must be applied for `load_address` to hold."),
            ("dump", "table(scalar)", False,
             "For `memory-dump`: `file` (name under the machine's derived folder), `covers` (section name), "
             "`when` (the moment of the dump)."),
            ("unpack", "table(scalar)", False, "For `unpack`: `tool` and what it does. Never the key or the data."),
            ("sections", "table(section)", False,
             "Named sections as `{offset, size}`, offsets from the module's first byte. Address expressions and "
             "gates use them."),
            NOTE, SOURCE,
        ],
    },
    "pin[]": {
        "doc": "A change that fixes something the game would otherwise vary, with the code hash it relies on.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("purpose", "str", True, "What it makes fixed."),
            ("module", "ref(module)", True, "The module whose code is changed."),
            ("relies_on_sha1", "sha1", False, "SHA-1 of that module's unchanged file. The pin is void on any "
                                              "other hash."),
            ("applied", "enum(extracted-copy|ram-at-boot|image)", True,
             "How it is applied today: to a local extracted copy, to memory at boot, or to the image the "
             "recompiler reads and to memory alike."),
            ("result", "str", True, "What holds once it is applied."),
            ("writes", "list(write)", True, "The changed words."),
            NOTE, SOURCE,
        ],
    },
    "configuration[]": {
        "doc": "A way of running that results are stated for (single core, dual core). Gates and noise are per "
               "configuration.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("what", "str", True, "What distinguishes it."),
            ("ships", "bool", False, "The configuration the product ships with. Measure there."),
            ("primary", "bool", False, "The configuration each step is judged in."),
            ("env", "table(str)", False, "Environment given to the runner for this configuration."),
            ("settings", "table(scalar)", False, "Emulator settings this configuration overrides."),
            NOTE, SOURCE,
        ],
    },
    "setting[]": {
        "doc": "An emulator or runner setting the game needs, with the reason.",
        "fields": [
            ("key", "str", True, "The setting's name where it is set."),
            ("value", "scalar", True, "Its value."),
            ("where", "enum(emulator-config|game-config|runner-arg|runner-env)", True,
             "Where it is set: the emulator's main configuration, its per-game configuration, the runner's "
             "command line, or the runner's environment."),
            ("applies", "enum(all|reference|native)", False, "Which runs take it. Default `all`."),
            ("reason", "str", True, "Why it is needed. A setting without a reason is removed."),
            NOTE, SOURCE,
        ],
    },
    "scene[]": {
        "doc": "A test scene and how to reach it.",
        "fields": [
            ("name", "str", True, "A short name, used in run names."),
            ("exercises", "str", True, "What the scene exercises, and what it does not."),
            ("reach", "enum(savestate|input-recording|boot-codes|boot)", True,
             "A saved state recorded under the reference, an input recording, boot codes, or `boot`: a plain "
             "start from the disc tree with nothing but the scene's scripted input."),
            ("state", "str", False, "For `savestate`: the file's name under the machine's derived folder. Never "
                                    "committed."),
            ("sha1", "sha1", False, "SHA-1 of the saved state or recording, so two machines know they hold the "
                                    "same one."),
            ("recorded_under", "str", False, "For `savestate`: which core recorded it and where in the game."),
            ("recording", "str", False, "For `input-recording`: the file's name under the derived folder."),
            ("codes", "list(str)", False, "For `boot-codes`: the generators or code files, in the game's "
                                          "repository."),
            ("input", "str", False, "The scripted input while the scene runs, in the probe's form "
                                    "`FIELD:BUTTONS_HEX[:STICK_X:STICK_Y[:CSTICK_X:CSTICK_Y]],...`."),
            ("fields", "int", False, "The usual length of a run, in display fields."),
            ("runner_args", "list(str)", False, "Further arguments for the runner in every run of this scene (a "
                                                "game's own: the file a race is booted from, a switch of its "
                                                "port). `{work}` and `{run}` stand for the work folder and the "
                                                "run's folder as Windows sees them. No spaces, quotes or `|`."),
            ("dump_steps", "list(int)", False, "Step-counter values at which whole memory is dumped."),
            ("compare_from_step", "int", False, "The first step at which the hashes are compared (before it "
                                                "the differences are counted, not failed)."),
            ("screenshot_field", "int", False, "The field at which the run's screenshot is taken."),
            ("screenshot_fields", "list(int)", False, "Further fields at which a screenshot is taken, each to "
                                                      "its own file (`<screenshot>-f<field>`): a scene that "
                                                      "passes through several screens."),
            ("uses", "list(enum(timing|gate|training|screenshot|long))", False, "What the scene is used for."),
            NOTE, SOURCE,
        ],
    },
    "difference[]": {
        "doc": "A source of difference between two runs, and how it is pinned.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("what", "str", True, "What differs and what it changes downstream."),
            ("pinned", "enum(setting|pin|scene|codes|harness|noise|by-step|ungated|open)", True,
             "How it is handled: by a setting, a pin, the scene (its saved state or scripted input), boot codes, "
             "the harness's run procedure, accepted as noise (a set under `exactness.noise`), by comparing per "
             "step where display timing is free, left outside every gated region (say in `note` why that is "
             "acceptable), or still open."),
            ("by", "str", False, "The setting key, pin name, scene name or noise name that handles it."),
            NOTE, SOURCE,
        ],
    },
    "memory": {
        "doc": "The memory map beyond the modules. Holds `region` entries only.",
        "fields": [],
    },
    "memory.region[]": {
        "doc": "A named part of guest memory, for labelling differences. Regions of modules need no entry: "
               "their sections are regions already.",
        "fields": [
            ("name", "str", True, "The label."),
            ("start", "addr", True, "First address."),
            ("end", "addr", True, "One past the last address."),
            NOTE, SOURCE,
        ],
    },
    "exactness": {
        "doc": "How exactness is proven. One table, with `gate` and `noise` entries.",
        "fields": [
            ("step_counter", "addr", True, "The guest word that counts simulation steps. Dumps and per-step "
                                           "comparisons are keyed by it."),
            ("statement", "str", False, "What the gates cover and what they do not, in a sentence or two."),
            NOTE, SOURCE,
        ],
    },
    "exactness.noise[]": {
        "doc": "Memory that differs between two runs that should be equal. A gate ignores exactly the sets it "
               "names.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("what", "str", True, "What the memory is, and whether that is proven or inferred."),
            ("configurations", "list(ref(configuration))", False, "Where it applies. Default: all."),
            ("scenes", "list(ref(scene))", False, "Where it applies. Default: all."),
            ("words", "list(addr)", False, "Single 32-bit words."),
            ("ranges", "list(range)", False, "Address ranges."),
            ("reference_pairs", "table(str)", False,
             "Scene name to the pair of reference runs (the reference against itself) in which the module's "
             "differing words lay in this set: which runs, when, how many words. A gate may pass this set by "
             "name (`pass_named`) only in a scene listed here: noise is what the reference shows against "
             "itself, never what a build shows against the reference."),
            NOTE, SOURCE,
        ],
    },
    "exactness.gate[]": {
        "doc": "One comparison a build must pass: what is compared, at which points, against what, with its "
               "threshold.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("kind", "enum(hash|memory)", True,
             "`hash`: a probe hash column compared row by row. `memory`: the 32-bit words of memory dumps."),
            ("hashes", "list(ref(hash))", False, "For `hash`: the probe hashes compared."),
            ("by", "enum(field|step)", False,
             "For `hash`: rows matched by display field, or by step counter (the first field that shows each "
             "step). Use `step` where display timing is free."),
            ("within", "list(str)", False,
             "For `memory`: limit the comparison to these regions (`<module>:<section>` or a memory region's "
             "name). Default: all dumped memory."),
            ("ignore", "list(ref(noise))", False, "The noise sets left out."),
            ("pass_named", "list(ref(noise))", False,
             "For `memory`: noise sets that pass by name instead of silently. Differing words that lie in one "
             "of them do not fail the gate, and the line says so: `pass, noise: <set> (<n> words)`; a batch "
             "ends with how often each set occurred. A set counts only in a scene for which it records a "
             "`reference_pairs` entry. For noise that occurs in some runs and not in others (a start that "
             "slipped a field), so that a reader sees how often."),
            ("dead_stacks", "bool", False,
             "For `memory`: leave out the words below each guest thread's saved stack pointer in both dumps, "
             "found from the OS's thread records (GameCube/Wii OSThread; tools/harness/deadstack.py): memory the "
             "program does not read before writing it again. Never the running thread's stack."),
            ("against", "enum(reference|self|previous)", True,
             "Compared with the reference's run, with a second run of the same build, or with the build "
             "before."),
            ("configurations", "list(ref(configuration))", True, "Where the gate applies."),
            ("scenes", "list(ref(scene))", False, "Where the gate applies. Default: every scene used for gates."),
            ("max_differing", "int", True, "The threshold: how many rows or words may differ. Normally 0."),
            NOTE, SOURCE,
        ],
    },
    "probe": {
        "doc": "What the runtime's probe logs, times, hashes and dumps. One table, with `value`, `hash` and "
               "`timer` entries. See `docs/probe.md`.",
        "fields": [
            ("select_value", "ref(value)", False, "A logged value that marks the rows worth measuring."),
            ("select_equals", "int", False, "Rows count when `select_value` equals this."),
            ("skip_fields", "int", False, "Selected rows skipped at the start of a run before timing."),
            ("timer_call", "addr", False, "The call instruction through which every timed function is called."),
            ("timer_return", "addr", False, "The instruction that call returns to."),
            ("timer_call_word", "int", False, "The instruction word expected at `timer_call` (checked before "
                                              "hooking)."),
            ("timer_return_word", "int", False, "The instruction word expected at `timer_return`."),
            ("dump_at", "enum(first-timer-call-of-step|field)", False,
             "The guest point of a memory dump. A fixed guest point is comparable; a display field catches "
             "threads at different places."),
            ("trace_calls", "ref(timer)", False, "The timer whose calls the access trace tells apart (the function "
                                                 "called once per actor)."),
            ("trace_frame_end", "ref(timer)", False, "The timer whose first call ends a traced frame."),
            ("dump_suffix", "str", False,
             "What a dump's file name adds to the log's, with `{step}` for the step. Default `.step{step}.ram`."),
            ("legacy_total_column", "str", False, "The column suffix of the all-timers total of a probe that "
                                                  "predates the contract."),
            ("env", "table(str)", False,
             "Names of the environment variables of the probe in use, where they differ from the contract's "
             "(`docs/probe.md`). Keys are the contract's names; an empty name means the probe has no such "
             "variable."),
            NOTE, SOURCE,
        ],
    },
    "probe.value[]": {
        "doc": "A guest value logged every field.",
        "fields": [
            ("name", "str", True, "The log column."),
            ("at", "addr", True, "Where it is."),
            ("width", "int", True, "Bytes: 1, 2 or 4."),
            NOTE, SOURCE,
        ],
    },
    "probe.hash[]": {
        "doc": "A hash of guest memory logged every field.",
        "fields": [
            ("name", "str", True, "The log column."),
            ("ranges", "list(range)", True, "What is hashed, in order."),
            ("zero", "list(ref(noise))", False, "Noise sets zeroed in the copy before hashing."),
            NOTE, SOURCE,
        ],
    },
    "probe.timer[]": {
        "doc": "A guest function timed per call.",
        "fields": [
            ("name", "str", True, "A short name; the log columns are `t_`, `n_`, `c_` and `e_` plus this name."),
            ("entry", "addr", True, "The function's first instruction."),
            ("per_step", "number", False, "Calls per simulation step, as observed."),
            ("legacy_column", "str", False, "The column suffix of a probe that predates the contract."),
            NOTE, SOURCE,
        ],
    },
    "fact": {
        "doc": "Discovered facts about the game's code. Holds the entries below only.",
        "fields": [],
    },
    "fact.hot_root[]": {
        "doc": "A function at the root of hot code: a candidate for timing, profiling and closed compilation.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("entry", "addr", True, "Its first instruction."),
            ("what", "str", True, "What it does and how hot it is."),
            NOTE, SOURCE,
        ],
    },
    "fact.wait_loop[]": {
        "doc": "A loop in which the game waits: native code spins there unless the runtime is told.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("kind", "enum(os-idle|busy-wait)", True, "The OS idle loop, or a loop polling for an event."),
            ("idle_pc", "addr", True, "The address given to the runtime as an idle point."),
            ("what", "str", True, "What it waits for, and what skipping it changes."),
            NOTE, SOURCE,
        ],
    },
    "fact.closed_unit[]": {
        "doc": "A set of functions compiled as one closed unit.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("roots", "list(addr)", True, "Addresses of the unit's roots."),
            ("functions", "int", False, "How many functions the unit holds."),
            ("deferral", "bool", False, "Whether slice ends and interrupts are deferred to the unit's end."),
            ("why_safe", "str", True, "Why closing (and deferring) cannot change the game's state."),
            ("found_by", "str", False, "How the roots were found."),
            NOTE, SOURCE,
        ],
    },
    "fact.packed_load[]": {
        "doc": "A quantisation register setting the game's paired loads and stores use.",
        "fields": [
            ("gqr", "int", True, "The register's number."),
            ("value", "int", True, "The value it holds."),
            ("share", "str", True, "How much of the game's paired accesses use it."),
            NOTE, SOURCE,
        ],
    },
    "fact.memory_window[]": {
        "doc": "Guest memory outside main memory that hot code accesses directly.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("guest_base", "int", True, "Its guest address."),
            ("what", "str", True, "What it is and how often it is accessed."),
            NOTE, SOURCE,
        ],
    },
    "fact.fallback[]": {
        "doc": "Code that stays on the fallback core, and why.",
        "fields": [
            ("name", "str", True, "A short name."),
            ("at", "addr", True, "Where."),
            ("why", "str", True, "Why it is not native, and whether it is hot."),
            NOTE, SOURCE,
        ],
    },
    "build": {
        "doc": "The current best build: its recompiler arguments and switches. One table, with `switches` and "
               "`training` entries.",
        "fields": [
            ("name", "str", True, "The build's name in the findings' table."),
            ("backend", "str", True, "The recompiler backend."),
            ("args", "list(str)", True, "Recompiler arguments of this build, in order, beyond backend, jobs, "
                                        "input and output."),
            ("platform_args", "list(str)", False, "Recompiler arguments that name the console's CPU and "
                                                  "platform. They follow `args` and any per-run extras."),
            ("target", "str", False, "The host target and what it must have (for example a hardware FMA)."),
            ("never", "list(str)", False, "Arguments and targets that must never be used, each with why."),
            ("switches", "table(str)", True, "Environment switches of the recompiler, name to value. Each is "
                                             "part of the object cache's key."),
            ("pgo", "bool", False, "Whether the build is profile-guided."),
            NOTE, SOURCE,
        ],
    },
    "build.training[]": {
        "doc": "A training run for profile-guided optimisation.",
        "fields": [
            ("scene", "ref(scene)", True, "The scene trained on."),
            ("fields", "int", True, "Its length in fields."),
            ("configuration", "ref(configuration)", True, "The configuration it runs in."),
            NOTE, SOURCE,
        ],
    },
    "question[]": {
        "doc": "A value the notes do not settle. It is left out of the manifest and listed here.",
        "fields": [
            ("about", "str", True, "The field or entry it concerns."),
            ("text", "str", True, "The question."),
            ("blocks", "list(str)", False, "Harness commands that cannot run until it is answered."),
            ("who", "enum(owner|agent)", False, "Who can answer: the owner, or an agent with a run."),
        ],
    },
}

# Inline-table types used inside the tables above.
INLINE: dict[str, list[tuple]] = {
    "section": [
        ("offset", "int", True, "Offset from the module's first byte."),
        ("size", "int", True, "Bytes."),
    ],
    "write": [
        ("address", "addr", False, "The guest address of the word. One of `address` and `file_offset` is "
                                   "required; a module with no fixed address has only the second."),
        ("file_offset", "int", False, "Its offset in the module's file."),
        ("was", "str", True, "The original instruction, as a mnemonic."),
        ("becomes", "str", True, "The new instruction, as a mnemonic."),
        ("original", "int", False, "The original word. Tools check it before writing."),
        ("patched", "int", False, "The new word."),
    ],
}

# What each harness command needs from the manifest: (dotted path, why).
READINESS: dict[str, list[tuple[str, str]]] = {
    "build": [("build", "the recompiler arguments and switches"),
              ("module", "the code modules")],
    "run": [("scene", "a scene to run"),
            ("configuration", "the configurations"),
            ("probe", "what the probe logs")],
    "time": [("probe.timer", "the timed functions")],
    "gate": [("exactness", "the step counter"),
             ("exactness.gate", "the gates"),
             ("probe.hash", "the hashed ranges")],
    "noise": [("exactness", "the step counter"), ("scene", "a scene")],
    "profile": [("probe.timer", "the timed functions"), ("scene", "a scene")],
    "census": [("probe.timer", "the timed functions")],
    "trace": [("fact.hot_root", "the function whose calls are traced")],
    "bisect": [("exactness.gate", "a hash gate to bisect on")],
    "pgo": [("build", "the build"), ("build.training", "the training scenes")],
}

REF_KINDS = {
    "module": "module", "pin": "pin", "scene": "scene", "configuration": "configuration",
    "noise": "exactness.noise", "hash": "probe.hash", "value": "probe.value", "timer": "probe.timer",
}

_ADDR = re.compile(r"^([A-Za-z0-9_.\-]+?)(?::([A-Za-z0-9_.]+))?(?:\+(0x[0-9A-Fa-f]+|\d+))?$")
_SHA1 = re.compile(r"^[0-9a-f]{40}$")
_GAME_ID = re.compile(r"^[A-Z0-9]{6}$")
# One step of a scene's input script: FIELD[:BUTTONS_HEX[:STICK_X:STICK_Y[:CSTICK_X:CSTICK_Y]]] (a lone STICK_X is
# read as the first project's scripts wrote it).
INPUT_STEP = r"\d+(:[0-9A-Fa-f]+(:\d+(:\d+(:\d+:\d+)?)?)?)?"


class ManifestError(Exception):
    """The manifest cannot be used as asked."""


def _get(doc: dict, path: str):
    """The table or array of tables at a dotted path ('exactness.gate'), or None."""
    node = doc
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _entries(doc: dict, key: str) -> list[tuple[str, dict]]:
    """(label, table) for a schema key: 'game' gives one, 'module[]' one per array entry."""
    if key == "":
        return [("(top level)", doc)]
    is_array = key.endswith("[]")
    node = _get(doc, key[:-2] if is_array else key)
    if node is None:
        return []
    if is_array:
        if not isinstance(node, list):
            return [(key[:-2], node)]
        return [(f"{key[:-2]}[{i}]" + (f" '{e.get('name')}'" if isinstance(e, dict) and e.get("name") else ""), e)
                for i, e in enumerate(node)]
    return [(key, node)]


def _child_tables(key: str) -> set[str]:
    """Names of sub-tables the schema defines directly under a table ('exactness' has 'noise' and 'gate')."""
    base = key[:-2] if key.endswith("[]") else key
    out = set()
    for other in SCHEMA:
        o = other[:-2] if other.endswith("[]") else other
        if not o or o == base:
            continue
        if base == "":
            out.add(o.split(".")[0])
        elif o.startswith(base + "."):
            out.add(o[len(base) + 1:].split(".")[0])
    return out


class Manifest:
    """A loaded manifest. Construct with `Manifest.load(path)`; nothing is checked until `validate()`."""

    def __init__(self, doc: dict, path: str = "<memory>"):
        self.doc = doc
        self.path = path

    @classmethod
    def load(cls, path: str) -> "Manifest":
        with open(path, "rb") as f:
            return cls(tomllib.load(f), path)

    # ---- lookups ---------------------------------------------------------------------------------------------

    def table(self, path: str) -> dict:
        node = _get(self.doc, path)
        return node if isinstance(node, dict) else {}

    def entries(self, path: str) -> list[dict]:
        node = _get(self.doc, path)
        return node if isinstance(node, list) else []

    def named(self, path: str, name: str) -> dict:
        for e in self.entries(path):
            if e.get("name") == name:
                return e
        known = ", ".join(e.get("name", "?") for e in self.entries(path)) or "none"
        raise ManifestError(f"{self.path}: no {path} named '{name}' (known: {known})")

    @property
    def game_id(self) -> str:
        return self.table("game").get("id", "")

    @property
    def mem1_size(self) -> int:
        return self.table("game").get("mem1_size", 0x1800000)

    def module(self, name: str) -> dict:
        return self.named("module", name)

    def scene(self, name: str) -> dict:
        return self.named("scene", name)

    def configuration(self, name: str) -> dict:
        return self.named("configuration", name)

    def primary_configuration(self) -> dict:
        for c in self.entries("configuration"):
            if c.get("primary"):
                return c
        configs = self.entries("configuration")
        if not configs:
            raise ManifestError(f"{self.path}: no configuration is defined")
        return configs[0]

    # ---- addresses -------------------------------------------------------------------------------------------

    def resolve(self, addr) -> int:
        """A guest address from an integer or a module-relative expression."""
        if isinstance(addr, bool):
            raise ManifestError(f"{self.path}: {addr!r} is not an address")
        if isinstance(addr, int):
            return addr
        if not isinstance(addr, str):
            raise ManifestError(f"{self.path}: {addr!r} is not an address")
        if re.fullmatch(r"0x[0-9A-Fa-f]+|\d+", addr):
            return int(addr, 0)
        m = _ADDR.match(addr)
        if not m:
            raise ManifestError(f"{self.path}: cannot read the address '{addr}'")
        name, section, off = m.group(1), m.group(2), int(m.group(3) or "0", 0)
        mod = self.module(name)
        base = mod.get("load_address")
        if base is None:
            raise ManifestError(f"{self.path}: '{addr}' needs module '{name}' to have a load_address")
        if section:
            sec = (mod.get("sections") or {}).get(section)
            if not isinstance(sec, dict) or "offset" not in sec:
                raise ManifestError(f"{self.path}: module '{name}' has no section '{section}' (in '{addr}')")
            base += sec["offset"]
        return base + off

    def resolve_range(self, r: dict) -> tuple[int, int] | None:
        """(start, end) of a fixed range, or None for a pointer range (known only at run time)."""
        if "pointer" in r:
            return None
        start = self.resolve(r["start"])
        end = self.resolve(r["end"]) if "end" in r else start + r["size"]
        return start, end

    def region(self, name: str) -> tuple[int, int]:
        """(start, end) of '<module>:<section>', '<module>' or a memory region's name."""
        for reg in self.entries("memory.region"):
            if reg.get("name") == name:
                return self.resolve(reg["start"]), self.resolve(reg["end"])
        mod_name, _, section = name.partition(":")
        mod = self.module(mod_name)
        base = mod.get("load_address")
        if base is None:
            raise ManifestError(f"{self.path}: region '{name}' needs module '{mod_name}' to have a load_address")
        sections = mod.get("sections") or {}
        if section:
            if section not in sections:
                raise ManifestError(f"{self.path}: module '{mod_name}' has no section '{section}'")
            s = sections[section]
            return base + s["offset"], base + s["offset"] + s["size"]
        if not sections:
            raise ManifestError(f"{self.path}: module '{mod_name}' has no sections to size it by")
        return base, max(base + s["offset"] + s["size"] for s in sections.values())

    def label(self, address: int) -> str:
        """A readable place for an address: '<module>:<section>+0xOFF', a memory region's name, or ''."""
        for mod in self.entries("module"):
            base = mod.get("load_address")
            if base is None:
                continue
            for sec_name, s in (mod.get("sections") or {}).items():
                if base + s["offset"] <= address < base + s["offset"] + s["size"]:
                    return f"{mod['name']}:{sec_name}+0x{address - base - s['offset']:X}"
        for reg in self.entries("memory.region"):
            if self.resolve(reg["start"]) <= address < self.resolve(reg["end"]):
                return reg["name"]
        return ""

    # ---- noise -----------------------------------------------------------------------------------------------

    def noise(self, names: list[str], configuration: str | None = None, scene: str | None = None
              ) -> tuple[set[int], list[tuple[int, int]]]:
        """The words and ranges of the named noise sets that apply to a configuration and scene."""
        words: set[int] = set()
        ranges: list[tuple[int, int]] = []
        for name in names:
            n = self.named("exactness.noise", name)
            if configuration and n.get("configurations") and configuration not in n["configurations"]:
                continue
            if scene and n.get("scenes") and scene not in n["scenes"]:
                continue
            words.update(self.resolve(w) for w in n.get("words", []))
            for r in n.get("ranges", []):
                fixed = self.resolve_range(r)
                if fixed:
                    ranges.append(fixed)
        return words, sorted(ranges)

    def named_noise(self, names: list[str], configuration: str, scene: str
                    ) -> list[tuple[str, set[int], list[tuple[int, int]]]]:
        """For a gate's `pass_named`: each set that applies to the configuration and scene and records a pair of
        reference runs for that scene, with its words and ranges."""
        out = []
        for name in names:
            if scene not in (self.named("exactness.noise", name).get("reference_pairs") or {}):
                continue
            words, ranges = self.noise([name], configuration, scene)
            if words or ranges:
                out.append((name, words, ranges))
        return out

    # ---- gates and settings ----------------------------------------------------------------------------------

    def gates(self, configuration: str, scene: str | None = None, against: str | None = None) -> list[dict]:
        out = []
        for g in self.entries("exactness.gate"):
            if configuration not in g.get("configurations", []):
                continue
            if scene and g.get("scenes") and scene not in g["scenes"]:
                continue
            if against and g.get("against") != against:
                continue
            out.append(g)
        return out

    def settings(self, where: str, run_kind: str) -> list[dict]:
        """Settings of one kind that apply to a 'reference' or 'native' run, in the manifest's order."""
        return [s for s in self.entries("setting")
                if s.get("where") == where and s.get("applies", "all") in ("all", run_kind)]

    def probe_env(self, contract_name: str) -> str:
        """The environment variable the probe in use reads for a contract variable."""
        return (self.table("probe").get("env") or {}).get(contract_name, contract_name)

    # ---- readiness -------------------------------------------------------------------------------------------

    def missing_for(self, command: str) -> list[str]:
        """What a harness command needs and the manifest lacks, with the open questions that block it."""
        out = []
        for path, why in READINESS.get(command, []):
            node = _get(self.doc, path)
            if not node:
                out.append(f"[{path}] is missing: {why}")
        for q in self.entries("question"):
            if command in q.get("blocks", []):
                out.append(f"open question on {q.get('about', '?')}: {q.get('text', '')}")
        return out

    def require(self, command: str) -> None:
        missing = self.missing_for(command)
        if missing:
            raise ManifestError(f"{self.path} is not ready for '{command}':\n  " + "\n  ".join(missing))

    # ---- validation ------------------------------------------------------------------------------------------

    def validate(self, strict: bool = False) -> tuple[list[str], list[str]]:
        """(errors, warnings). `strict` also requires a source on every entry."""
        return _Validator(self, strict).run()


class _Validator:
    def __init__(self, manifest: Manifest, strict: bool):
        self.m = manifest
        self.doc = manifest.doc
        self.strict = strict
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    def run(self) -> tuple[list[str], list[str]]:
        if not isinstance(self.doc, dict):
            return ["the manifest is not a table"], []
        if self.doc.get("schema") != SCHEMA_VERSION:
            self.err("schema", f"must be {SCHEMA_VERSION}, found {self.doc.get('schema')!r}")
        self.structure()
        if not self.errors:  # the cross-checks assume well-formed tables
            self.names_unique()
            self.references()
            self.semantics()
        return self.errors, self.warnings

    # ---- structure: required fields, types, unknown keys -----------------------------------------------------

    def structure(self) -> None:
        for required in ("game", "reference"):
            if required not in self.doc:
                self.err(required, "the table is required")
        for key, spec in SCHEMA.items():
            is_array = key.endswith("[]")
            node = _get(self.doc, key[:-2] if is_array else key) if key else self.doc
            if node is None:
                continue
            if is_array and not isinstance(node, list):
                self.err(key[:-2], "must be an array of tables ([[...]])")
                continue
            if not is_array and not isinstance(node, dict):
                self.err(key or "(top level)", "must be a table")
                continue
            fields = {f[0]: f for f in spec["fields"]}
            children = _child_tables(key)
            for label, entry in _entries(self.doc, key):
                if not isinstance(entry, dict):
                    self.err(label, "must be a table")
                    continue
                for name, _type, required, _doc in spec["fields"]:
                    if required and name not in entry:
                        self.err(label, f"'{name}' is required")
                for name, value in entry.items():
                    if name in children:
                        continue
                    if name not in fields:
                        self.err(label, f"unknown field '{name}'")
                        continue
                    self.check_type(f"{label}.{name}", value, fields[name][1])
                if self.strict and "source" in fields and "source" not in entry:
                    self.err(label, "has no 'source' (required by --strict)")

    def check_type(self, where: str, value, type_: str) -> None:
        if type_.startswith("list("):
            if not isinstance(value, list):
                return self.err(where, "must be an array")
            for i, v in enumerate(value):
                self.check_type(f"{where}[{i}]", v, type_[5:-1])
            return
        if type_.startswith("table("):
            if not isinstance(value, dict):
                return self.err(where, "must be a table")
            for k, v in value.items():
                self.check_type(f"{where}.{k}", v, type_[6:-1])
            return
        if type_.startswith("enum("):
            options = type_[5:-1].split("|")
            if value not in options:
                self.err(where, f"must be one of {', '.join(options)}; found {value!r}")
            return
        if type_.startswith("ref("):
            if not isinstance(value, str):
                self.err(where, "must be a name (a string)")
            return
        if type_ in INLINE:
            if not isinstance(value, dict):
                return self.err(where, "must be an inline table")
            fields = {f[0]: f for f in INLINE[type_]}
            for name, _t, required, _d in INLINE[type_]:
                if required and name not in value:
                    self.err(where, f"'{name}' is required")
            for k, v in value.items():
                if k not in fields:
                    self.err(where, f"unknown field '{k}'")
                else:
                    self.check_type(f"{where}.{k}", v, fields[k][1])
            return
        if type_ == "str":
            if not isinstance(value, str):
                self.err(where, "must be a string")
        elif type_ == "int":
            if not isinstance(value, int) or isinstance(value, bool):
                self.err(where, "must be an integer")
            elif value < 0:
                self.err(where, "must not be negative")
        elif type_ == "bool":
            if not isinstance(value, bool):
                self.err(where, "must be true or false")
        elif type_ == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                self.err(where, "must be a number")
        elif type_ == "scalar":
            if not isinstance(value, (str, int, float, bool)):
                self.err(where, "must be a string, number or boolean")
        elif type_ == "sha1":
            if not isinstance(value, str) or not _SHA1.match(value):
                self.err(where, "must be a full SHA-1: 40 lower-case hex digits")
        elif type_ == "addr":
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                self.err(where, "must be an address: an integer or '<module>[:<section>]+0xOFF'")
            elif isinstance(value, str) and not _ADDR.match(value):
                self.err(where, f"cannot read the address '{value}'")
        elif type_ == "range":
            if not isinstance(value, dict):
                return self.err(where, "must be an inline table")
            keys = set(value)
            if keys == {"start", "size"} or keys == {"start", "end"}:
                self.check_type(f"{where}.start", value["start"], "addr")
                self.check_type(f"{where}.{'size' if 'size' in value else 'end'}",
                                value.get("size", value.get("end")), "int" if "size" in value else "addr")
            elif keys == {"pointer", "offset", "size"} or keys == {"pointer", "size"}:
                self.check_type(f"{where}.pointer", value["pointer"], "addr")
                self.check_type(f"{where}.size", value["size"], "int")
                if "offset" in value:
                    self.check_type(f"{where}.offset", value["offset"], "int")
            else:
                self.err(where, "must be {start, size}, {start, end} or {pointer, [offset,] size}")
        else:  # pragma: no cover - a schema mistake
            raise AssertionError(f"unknown schema type {type_}")

    # ---- cross-checks ----------------------------------------------------------------------------------------

    def names_unique(self) -> None:
        for key in SCHEMA:
            if not key.endswith("[]"):
                continue
            seen: dict[str, str] = {}
            for label, entry in _entries(self.doc, key):
                name = entry.get("name")
                if name is None:
                    continue
                if name in seen:
                    self.err(label, f"the name '{name}' is already used by {seen[name]}")
                seen[name] = label

    def _names(self, kind: str) -> set[str]:
        return {e.get("name") for e in self.m.entries(REF_KINDS[kind])}

    def _check_refs(self, where: str, value, type_: str) -> None:
        if type_.startswith("list("):
            for i, v in enumerate(value):
                self._check_refs(f"{where}[{i}]", v, type_[5:-1])
        elif type_.startswith("ref("):
            kind = type_[4:-1]
            if value not in self._names(kind):
                known = ", ".join(sorted(n for n in self._names(kind) if n)) or "none"
                self.err(where, f"no {kind} is named '{value}' (known: {known})")
        elif type_ == "addr":
            self._check_addr(where, value)
        elif type_ == "range":
            for k in ("start", "end", "pointer"):
                if k in value:
                    self._check_addr(f"{where}.{k}", value[k])
            fixed = None
            try:
                fixed = self.m.resolve_range(value)
            except ManifestError:
                pass
            if fixed and fixed[1] <= fixed[0]:
                self.err(where, "the range is empty or reversed")
        elif type_ in INLINE:
            for name, t, _r, _d in INLINE[type_]:
                if name in value:
                    self._check_refs(f"{where}.{name}", value[name], t)

    def _check_addr(self, where: str, value) -> None:
        try:
            address = self.m.resolve(value)
        except ManifestError as e:
            return self.err(where, str(e).split(": ", 1)[-1])
        game = self.m.table("game")
        mem1 = game.get("mem1_size", 0x1800000)
        mem2 = game.get("mem2_size", 0)
        in_mem1 = 0x80000000 <= address <= 0x80000000 + mem1
        in_mem2 = mem2 and 0x90000000 <= address <= 0x90000000 + mem2
        if not (in_mem1 or in_mem2):
            self.err(where, f"0x{address:08X} is outside guest memory")

    def references(self) -> None:
        for key, spec in SCHEMA.items():
            for label, entry in _entries(self.doc, key):
                for name, type_, _req, _doc in spec["fields"]:
                    if name in entry:
                        self._check_refs(f"{label}.{name}", entry[name], type_)

    def semantics(self) -> None:
        m = self.m
        game = m.table("game")
        if not _GAME_ID.match(game.get("id", "")):
            self.err("game.id", "must be six characters, upper-case letters and digits")
        if game.get("platform") == "gamecube" and game.get("mem2_size"):
            self.err("game.mem2_size", "a GameCube has no second memory")

        modules = m.entries("module")
        if modules and not any(x.get("obtain") == "executable" for x in modules):
            self.err("module", "one module must be the executable (obtain = \"executable\")")
        for i, mod in enumerate(modules):
            label = f"module '{mod.get('name')}'"
            load = mod.get("load", "fixed" if mod.get("kind") == "dol" else "runtime")
            if mod.get("compile") and load == "runtime" and mod.get("load_address") is None:
                self.err(label, "is compiled and loaded at run time, so it needs a load_address (and a pin)")
            if mod.get("compile") and load == "runtime" and not mod.get("pins") and not mod.get("note"):
                self.warn(label, "is compiled at a run-time address with no pin named: say in a note why "
                                 "the address is stable")
            if mod.get("obtain") == "memory-dump" and not mod.get("dump"):
                self.err(label, "obtain = \"memory-dump\" needs a 'dump' table")
            if mod.get("obtain") == "unpack" and not mod.get("unpack"):
                self.err(label, "obtain = \"unpack\" needs an 'unpack' table")
            if mod.get("obtain") in ("disc-file", "unpack", "memory-dump") and not mod.get("disc_path"):
                self.err(label, "needs a disc_path")
            if mod.get("compile") and not mod.get("sha1"):
                self.warn(label, "is compiled but has no sha1: a build cannot check its input")
            for sec_name, s in (mod.get("sections") or {}).items():
                if s.get("size", 0) <= 0:
                    self.err(f"{label} section '{sec_name}'", "size must be positive")
            dump = mod.get("dump") or {}
            if dump.get("covers") and dump["covers"] not in (mod.get("sections") or {}):
                self.err(label, f"dump.covers names the section '{dump['covers']}', which is not defined")

        for pin in m.entries("pin"):
            label = f"pin '{pin.get('name')}'"
            if not pin.get("writes"):
                self.err(label, "has no writes")
            if not pin.get("relies_on_sha1"):
                self.warn(label, "names no code hash it relies on")
            for w in pin.get("writes", []):
                if "address" not in w and "file_offset" not in w:
                    self.err(label, "a write needs an 'address' or a 'file_offset'")
                if ("original" in w) != ("patched" in w):
                    self.warn(label, "a write has only one of 'original' and 'patched': tools cannot apply or "
                                     "check it")

        configs = m.entries("configuration")
        if sum(1 for c in configs if c.get("primary")) > 1:
            self.err("configuration", "only one configuration can be primary")
        if configs and not any(c.get("ships") for c in configs):
            self.warn("configuration", "none is marked 'ships': find out which the product uses and measure there")

        for scene in m.entries("scene"):
            label = f"scene '{scene.get('name')}'"
            need = {"savestate": "state", "input-recording": "recording", "boot-codes": "codes"}.get(scene["reach"])
            if need and need not in scene:
                self.err(label, f"reach = \"{scene['reach']}\" needs '{need}'")
            if "input" in scene and not re.fullmatch(
                    rf"neutral|{INPUT_STEP}(,\s*{INPUT_STEP})*", scene["input"]):
                self.err(label, f"cannot read the input script '{scene['input']}'")
            if "gate" in scene.get("uses", []) and not scene.get("dump_steps"):
                self.warn(label, "is used for gates but has no dump_steps: only hash gates can run on it")

        for d in m.entries("difference"):
            label = f"difference '{d.get('name')}'"
            kind, by = d["pinned"], d.get("by")
            if kind in ("setting", "pin", "scene", "noise") and not by:
                self.err(label, f"pinned = \"{kind}\" needs 'by'")
            elif kind == "setting" and by not in {s.get("key") for s in m.entries("setting")}:
                self.err(label, f"no setting has the key '{by}'")
            elif kind == "pin" and by not in self._names("pin"):
                self.err(label, f"no pin is named '{by}'")
            elif kind == "scene" and by not in self._names("scene"):
                self.err(label, f"no scene is named '{by}'")
            elif kind == "noise" and by not in self._names("noise"):
                self.err(label, f"no noise set is named '{by}'")
            if kind == "open":
                self.warn(label, "is open: two runs may differ for this reason")

        for n in m.entries("exactness.noise"):
            if not n.get("words") and not n.get("ranges"):
                self.err(f"noise '{n.get('name')}'", "names no words and no ranges")
            for scene_name in n.get("reference_pairs") or {}:
                if scene_name not in self._names("scene"):
                    self.err(f"noise '{n.get('name')}'", f"reference_pairs names scene '{scene_name}', which is not "
                                                         "defined")
                elif n.get("scenes") and scene_name not in n["scenes"]:
                    self.err(f"noise '{n.get('name')}'", f"reference_pairs names scene '{scene_name}', where the set "
                                                         "does not apply")

        hash_names = self._names("hash")
        for g in m.entries("exactness.gate"):
            label = f"gate '{g.get('name')}'"
            if g["kind"] == "hash":
                if not g.get("hashes"):
                    self.err(label, "kind = \"hash\" needs 'hashes'")
                if "by" not in g:
                    self.err(label, "kind = \"hash\" needs 'by' (field or step)")
                if g.get("within") or g.get("ignore") or g.get("dead_stacks"):
                    self.err(label, "'within', 'ignore' and 'dead_stacks' belong to memory gates; a hash's "
                                    "exclusions are its 'zero' list")
                for h in g.get("hashes", []):
                    if h not in hash_names:
                        pass  # reported by references()
            else:
                if g.get("hashes") or g.get("by"):
                    self.err(label, "'hashes' and 'by' belong to hash gates")
                for region in g.get("within", []):
                    try:
                        m.region(region)
                    except ManifestError as e:
                        self.err(label, str(e).split(": ", 1)[-1])
                for noise_name in g.get("ignore", []):
                    n = next((x for x in m.entries("exactness.noise") if x.get("name") == noise_name), None)
                    if n and n.get("configurations") and not set(n["configurations"]) & set(g["configurations"]):
                        self.err(label, f"ignores noise '{noise_name}', which is not declared for any of the "
                                        "gate's configurations")
                for noise_name in g.get("pass_named", []):
                    n = next((x for x in m.entries("exactness.noise") if x.get("name") == noise_name), None)
                    if noise_name in g.get("ignore", []):
                        self.err(label, f"both ignores and passes by name the noise '{noise_name}'")
                    if n and not n.get("reference_pairs"):
                        self.err(label, f"passes noise '{noise_name}' by name, which records no reference_pairs: "
                                        "only what two reference runs show against each other may pass")
            for scene_name in g.get("scenes", []):
                scene = next((s for s in m.entries("scene") if s.get("name") == scene_name), None)
                if scene and g["kind"] == "memory" and not scene.get("dump_steps"):
                    self.err(label, f"is a memory gate on scene '{scene_name}', which has no dump_steps")
        gates = m.entries("exactness.gate")
        for c in configs:
            mine = [g for g in gates if c["name"] in g.get("configurations", [])]
            if gates and not mine:
                self.warn(f"configuration '{c['name']}'", "no gate applies: exactness there is unproven")
            elif mine and not any(g.get("against") == "self" for g in mine):
                self.warn(f"configuration '{c['name']}'", "no gate compares a build with itself: the noise floor "
                                                          "there is not checked")

        probe = m.table("probe")
        if probe.get("select_value") and "select_equals" not in probe:
            self.err("probe", "'select_value' needs 'select_equals'")
        if m.entries("probe.timer") and not (probe.get("timer_call") and probe.get("timer_return")):
            self.err("probe", "timers need 'timer_call' and 'timer_return'")
        for v in m.entries("probe.value"):
            if v.get("width") not in (1, 2, 4):
                self.err(f"probe value '{v.get('name')}'", "width must be 1, 2 or 4")

        build = m.table("build")
        if build:
            for name, value in (build.get("switches") or {}).items():
                if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
                    self.err(f"build.switches.{name}", "a switch is an environment variable name in capitals")
            if build.get("pgo") and not m.entries("build.training"):
                self.err("build", "pgo = true needs at least one [[build.training]]")
            for t in m.entries("build.training"):
                scene = next((s for s in m.entries("scene") if s.get("name") == t.get("scene")), None)
                if scene and "training" not in scene.get("uses", []):
                    self.warn(f"build.training '{t.get('scene')}'", "the scene is not marked for training use")
            self.derived_switches(build.get("switches") or {})

        for q in m.entries("question"):
            for command in q.get("blocks", []):
                if command not in READINESS:
                    self.err(f"question on '{q.get('about')}'", f"'{command}' is not a harness command "
                                                                f"({', '.join(READINESS)})")

    def derived_switches(self, switches: dict) -> None:
        """Recompiler switches whose value restates a fact must agree with the fact."""
        m = self.m

        def hexes(text: str) -> set[int]:
            return {int(x, 16) for x in text.split(",") if x}

        roots = m.entries("fact.closed_unit")
        if "DOLRECOMP_CLOSED_ROOTS" in switches and roots:
            fact = {m.resolve(r) for u in roots for r in u.get("roots", [])}
            if hexes(switches["DOLRECOMP_CLOSED_ROOTS"]) != fact:
                self.warn("build.switches.DOLRECOMP_CLOSED_ROOTS", "differs from the roots under fact.closed_unit")
        if "DOLRECOMP_PSQ_GQR" in switches and m.entries("fact.packed_load"):
            fact = {f"{p['gqr']}:{p['value']:x}" for p in m.entries("fact.packed_load")}
            if set(switches["DOLRECOMP_PSQ_GQR"].lower().split(",")) != fact:
                self.warn("build.switches.DOLRECOMP_PSQ_GQR", "differs from fact.packed_load")
        probe = m.table("probe")
        if "DOLRECOMP_INDIRECT_CALL_EXITS" in switches and probe.get("timer_call") is not None:
            try:
                call = m.resolve(probe["timer_call"])
                if call not in hexes(switches["DOLRECOMP_INDIRECT_CALL_EXITS"]):
                    self.warn("build.switches.DOLRECOMP_INDIRECT_CALL_EXITS",
                              f"does not hold the probe's timer_call (0x{call:08X}): the probe would not see "
                              "timed calls")
            except ManifestError:
                pass


# --------------------------------------------------------------------------------------------------------------
# The field-by-field reference, generated from the schema.
# --------------------------------------------------------------------------------------------------------------

def reference_markdown() -> str:
    """The reference section of docs/manifest.md."""
    out: list[str] = []
    for key, spec in SCHEMA.items():
        if key == "":
            title = "Top level"
        elif key.endswith("[]"):
            title = f"`[[{key[:-2]}]]`"
        else:
            title = f"`[{key}]`"
        out += [f"### {title}", "", spec["doc"], "", "| Field | Type | Required | Meaning |", "|---|---|---|---|"]
        for name, type_, required, doc in spec["fields"]:
            out.append(f"| `{name}` | {_type_text(type_)} | {'yes' if required else 'no'} | {doc} |")
        out.append("")
    out += ["### Inline tables", ""]
    for name, fields in INLINE.items():
        out += [f"**{name}**", "", "| Field | Type | Required | Meaning |", "|---|---|---|---|"]
        for fname, type_, required, doc in fields:
            out.append(f"| `{fname}` | {_type_text(type_)} | {'yes' if required else 'no'} | {doc} |")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _type_text(type_: str) -> str:
    if type_.startswith("list("):
        return "list of " + _type_text(type_[5:-1])
    if type_.startswith("table("):
        return "table of " + _type_text(type_[6:-1])
    if type_.startswith("enum("):
        return " \\| ".join(f"`{x}`" for x in type_[5:-1].split("|"))
    if type_.startswith("ref("):
        return f"name of a {type_[4:-1]}"
    return {"str": "string", "int": "integer", "bool": "boolean", "number": "number", "sha1": "SHA-1",
            "addr": "address", "range": "range", "scalar": "string, number or boolean"}.get(type_, type_)
