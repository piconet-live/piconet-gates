# port/gates/vendor/harness: the test harness

The harness that starts, bounds and compares every test game of the gates: `recomp.py run` (one muted, labelled,
bounded game with the probe), `recomp.py time` (the timing table) and `recomp.py gate` (the exactness gates on two
runs' logs and memory dumps). It reads the game's manifest (`recomp/manifest.toml`) and a machine file of the PC
(`recomp/machine-*.toml`, which `port/setup/install.sh` writes into the work folder).

These files are copied from recomp-kit's `tools/harness` (and `tools/manifest/manifest.py`), commit `72a2257`, by
the same author as this repository, under the same licence: GPL-3.0-or-later (the GPL-3.0 text is this repository's
`LICENSE`). Only what the gates use is here: the `run`, `time` and `gate` commands and the modules they import.

Trimmed on 2026-10-25 (the runner scripts audit): `recomp.py` and `actions.py` were cut to those three commands; every
other module is as copied. Taken out, as at recomp-kit `72a2257`:
- the commands `doctor`, `cleanup`, `build`, `emit`, `pgo`, `batch`, `long`, `noise`, `profile`, `census`, `trace`,
  `bisect` and `roots` (their parsers and their branches of `recomp.py dispatch`; `announce` and `roots` there);
- in `actions.py`, what only they used: `build`, `module_build`, `combine_specs`, `switches`, `_disassemble`, `_cmd`,
  `_sets`, `_run`, `_tail`, `_num`, `batch`, `long_runs`, `noise_floor`, `profile`, `counting_run`, `pgo`, `hybrid`,
  `changed_chunks`, `bisect`, `closed_roots_step`, `doctor`, `cleanup`, `stop_registered`, `scenes_for`,
  `configurations`, `restore_config`;
- `main`'s arguments after `--` (they went to the recompiler, for `build` and `emit`): refused now.
To have any of them again, take recomp-kit's harness (`RECOMP_KIT=<a recomp-kit checkout>`, below) or copy the files
anew from `72a2257` or a later commit.

| File | What |
|---|---|
| `recomp.py` | The command line |
| `actions.py` | What each command does, as a plan of steps (`--dry-run` prints it) |
| `machine.py`, `manifest.py` | The machine file and the game's manifest |
| `gate.py`, `deadstack.py`, `probelog.py`, `probeconfig.py`, `timing.py` | The probe's log, the gates and the timing table |
| `locks.py`, `registry.py` | A game at a time on the PC (TIMING.lock and request files in the work folder: the same files as a PC's own lock scripts, PC_SCRIPTS), and the processes a run started |
| `win/` | `launch.ps1` (starts a game with its time limit), `time-limit.ps1` (its watchdog), `show.ps1`: copied to the work folder's `kit-win` by `install.sh` and by every run |

`RECOMP_KIT=<a recomp-kit checkout>` makes every script use that checkout's `tools/harness` in place of this folder
(`port/setup/lib.sh`, `HARNESS_DIR`).
