"""The machine file: where things are on one PC. Never game facts, never committed with a game's manifest.

See docs/harness.md. Standard library only.
"""
from __future__ import annotations

import os
import tomllib

MACHINE_SCHEMA = 1

# field: (default, meaning). A default of None means required.
FIELDS: dict[str, tuple] = {
    "schema": (None, "Version of this format."),
    "host": ("wsl-windows", "How the harness reaches the tools. Only `wsl-windows` is written: a Linux shell "
                            "(WSL) driving Windows programs."),
    "work": (None, "The work folder as this shell sees it. Everything derived from the game lives under it, "
                   "outside every repository."),
    "work_win": (None, "The same folder as Windows programs see it."),
    "jobs": (16, "Parallel jobs for the recompiler."),
    "runner": ("ModernGekko/build/moderngekko-run.exe", "The runner, under `work`."),
    "runner_process": ("moderngekko", "Text that identifies the runner in the process list."),
    "window_title": ("ModernGekko", "Text in the runner's window title, for labelling a visible run."),
    "recompiler": ("DolRecomp/build/dolrecomp.exe", "The recompiler, under `work`."),
    "module_template": ("ModernGekko/vendor/dolphin/module-template", "The module template, under `work`."),
    "runtime_source": ("ModernGekko/vendor/dolphin", "The runtime's source tree, under `work` (the module "
                                                     "build needs its headers)."),
    "llvm_bin": (None, "LLVM's bin folder, as this shell sees it (llvm-objdump, llvm-dis, llvm-profdata)."),
    "llvm_bin_win": (None, "The same folder as Windows sees it (clang for the module build)."),
    "vcvars": ("", "The Visual Studio environment script, as Windows sees it. Empty when the environment is "
                   "already set."),
    "path_win": ([], "Windows folders put in front of PATH for the module build (where cmake and ninja are, "
                     "when they are not on PATH)."),
    "game": (None, "The extracted disc tree (sys/ and files/), under `work`."),
    "user": ("user", "The emulator's user folder for test runs, under `work`."),
    "user_pristine": ("", "A folder whose contents are copied over `user` before each run (memory cards). "
                          "Empty: nothing is copied."),
    "config": ("", "The emulator's main configuration file, under `work`. With `config_pristine`, restored "
                   "before each batch."),
    "config_pristine": ("", "A known-good copy of `config`, under `work`."),
    "derived": ("derived", "Saved states and memory dumps of modules, under `work`."),
    "scratch": ("scratch", "Profiles and temporary files, under `work`."),
    "shots": ("shots", "Screenshots, under `work`."),
    "cache": ("llvm-cache", "The recompiler's object cache, under `work`."),
    "build_dir": ("builds/{name}", "The recompiler's output folder for a build, under `work`. Generated code "
                                   "goes in its `generated` folder; logs are written beside it."),
    "module_dir": ("builds/{name}/module", "Where a build's module goes, under `work`."),
    "run_dir": ("runs/{run}", "Where a run's files go, under `work`."),
    "shot_file": ("{run}.png", "A run's screenshot, under `shots`."),
    "post_emit": ([], "Commands run on the generated code before the module is built, each a list of words. "
                      "`{generated}` is the generated-code folder, `{kit}` this kit's tools/harness folder."),
    "build_minutes": (10, "Rough minutes for a full build, for the expected end written into BUILD.wanted."),
    "run_seconds_per_field": (0.045, "Rough wall seconds per field of a run, for stating a batch's duration."),
    "tsc_hz": (0, "The time-stamp counter's rate. 0: measured from each log."),
}


class MachineError(Exception):
    """The machine file cannot be used."""


class Machine:
    def __init__(self, doc: dict, path: str = "<memory>"):
        self.path = path
        unknown = sorted(set(doc) - set(FIELDS))
        if unknown:
            raise MachineError(f"{path}: unknown field(s): {', '.join(unknown)}")
        missing = sorted(k for k, (default, _) in FIELDS.items() if default is None and k not in doc)
        if missing:
            raise MachineError(f"{path}: missing field(s): {', '.join(missing)}")
        if doc["schema"] != MACHINE_SCHEMA:
            raise MachineError(f"{path}: schema must be {MACHINE_SCHEMA}")
        self.v = {k: doc.get(k, default) for k, (default, _) in FIELDS.items()}
        if self.v["host"] != "wsl-windows":
            raise MachineError(f"{path}: host '{self.v['host']}' is not supported; only wsl-windows is written")

    @classmethod
    def load(cls, path: str) -> "Machine":
        try:
            with open(path, "rb") as f:
                return cls(tomllib.load(f), path)
        except OSError as e:
            raise MachineError(f"cannot read the machine file {path}: {e}") from e

    def __getitem__(self, key: str):
        return self.v[key]

    # ---- paths -----------------------------------------------------------------------------------------------

    def p(self, *parts: str) -> str:
        """A path under the work folder, for this shell."""
        return os.path.join(self.v["work"], *[x for x in parts if x]).replace("\\", "/")

    def w(self, *parts: str) -> str:
        """The same path as Windows sees it."""
        tail = "\\".join(x.replace("/", "\\") for x in parts if x)
        return self.v["work_win"].rstrip("\\") + ("\\" + tail if tail else "")

    def generated(self, name: str) -> str:
        return self.v["build_dir"].format(name=name)

    def module(self, name: str) -> str:
        return self.v["module_dir"].format(name=name)

    def module_file(self, name: str, game_id: str) -> str:
        """The module's file, under `work`. Its name is the module template's: g<GAMEID>_recomp.dll."""
        return f"{self.module(name)}/g{game_id}_recomp.dll"

    def run(self, run: str) -> str:
        return self.v["run_dir"].format(run=run)

    def shot(self, run: str) -> str:
        return f"{self.v['shots']}/{self.v['shot_file'].format(run=run)}"

    def tool(self, name: str) -> str:
        """An LLVM tool for this shell."""
        return os.path.join(self.v["llvm_bin"], name).replace("\\", "/")

    def lock(self, name: str) -> str:
        """TIMING.lock or BUILD.wanted, in the work folder."""
        return self.p(name)


def reference_markdown() -> str:
    out = ["| Field | Default | Meaning |", "|---|---|---|"]
    for name, (default, doc) in FIELDS.items():
        shown = "required" if default is None else ("`" + str(default) + "`" if default not in ("", []) else "empty")
        out.append(f"| `{name}` | {shown} | {doc} |")
    return "\n".join(out) + "\n"
