# port/gates: the gates of the native form

One table says whether a build holds: `gates.sh`. It wraps the scripts beside it and under `runs/`; a row passes only
when its commands and the judge both do. What each row compares and what a pass looks like: its line in `gates.sh`
and its judge in `gate-judge.py`. The build a gate is given is made by [../build](../build/README.md).

| File | What |
|---|---|
| `gates.sh`, `gates-table.sh` | The table: each row's inputs (one missing: "not run: needs X"), its commands, the judge's verdict; the time each row was given and took, and the whole pass's (30 minutes at most: the full check runs beside the playbacks of kept recordings, and playbacks run three side by side). `gates-table.sh` is its machinery, sourced; the rows are in `gates.sh`. A pass says its rows to the progress file one window shows (the release-build handbook; `tests/test_gates_progress.py`) |
| `gate-native.sh`, `time-native.sh` | The gate scenes against the JIT of the same round (row `batch`); the timing batch (row `timing`) |
| `replay-check.sh` | A recording played back against its own checksums (`AT_ONCE=N`: N playbacks side by side, each under its own name for the harness and in its own user folder, one busy check for the set; default 1; its cases with stand-ins: `tests/test_replay_check.py`): rows `fork`, `forced`, `control`, `crash`, `roundtrip`, and the end of every two-game run |
| `gate-judge.py`, `judge_*.py`, `replay-compare.py` | The judges: what a run must have left behind to count as a game that ran and ended as it should. They read files only; a recording through `replay-compare.py` (two recordings of one race, step by step) |
| `logs.py` | The one reader of a test game's pacing log (`pace.csv`: its records by kind, the columns as the log's header names them, the clock's rate) and its rollback log (`rb.csv`), for the judges and `reports/` |
| (none: a PC's own) | A PC's machine sharing (the CPU window, the timed runs' lock, the build lock, the harness turn), the busy check and the owner's watch set are in no repository: a folder the PC names (the runner's `port/setup/pins.tsv` PC_SCRIPTS_DEFAULT, filled in `~/.config/piconet/pins.tsv`), used where it is there (`port/setup/lib.sh` `pc_take`, `pc_release`). Without it every script here runs all the same and says once what it leaves out |
| `room-for-games.sh` | `room-for-games.sh GAMES`: has Windows the memory left to start that many games (its free commit; 1.5 GB a game and 2.5 GB that stays free)? Every script here that starts a game asks first and starts nothing on a no (status 3, one sentence): `replay-check.sh` for each set, `gate-native.sh`, `time-native.sh`, `runs/launcher-run.sh`, `runs/pair-run.sh`, `runs/mixed-run.sh`, `runs/quickplay-run.sh`. Its cases: `tests/test_room_for_games.py` |
| [`runs/`](runs/README.md), [`reports/`](reports/README.md) | The scripts that start a game: one game, a match race, two games, two builds in one race, Quick Play; what a run's logs say |
| [`vendor/harness/`](vendor/harness/README.md) | The test harness every game of the gates starts through (`recomp.py run`, `time`, `gate`), copied from recomp-kit |
| `pins.tsv`, `runner.sh`, `switches.tsv` | The gates are a repository of their own (piconet-gates, private), checked out at the runner's `port/setup/pins.tsv` REPO_GATES (`port/gates`): `pins.tsv` REPO_RUNNER (`../..`) names that runner, `runner.sh` finds it and refuses a pair that does not name each other; the gates' switch registry |
| [`release/`](release/README.md) | The launcher's release: the game build, the player copy made for a stack (the service's `stacks.py`), the installer's folder, Velopack's pack and the upload to piconet-live/piconet-launcher's releases (only with `RELEASE=1`); signing hook `SIGN=azure`, off |
| `check.sh`, `tests/` | The gates' own check (the runner's `port/check.sh` runs it when the gates are checked out): the judges and the scripts on made-up folders, by plain unittest. No game |

## Running the gates

Optional tests of a build, with real games (muted, each closing by itself), on Windows with WSL as the build. They
need your own F-Zero GX (USA) disc image (its path: `DISC_DEFAULT` in `~/.config/piconet/pins.tsv`, a table of
`port/setup/pins.tsv`'s form), a work folder from `port/setup/setup.sh` and a build in it, `port/build/build.sh NAME` (`FIRST_BOOT=1` once, for the rows through the launcher). The harness that
starts the games is here, in `vendor/harness`. One command, for every row or some (`ONLY`):

    PORT_WORK=WORK ONLY="roundtrip fork" port/gates/gates.sh NAME --launcher launcher-NAME   # --dry-run: what would run

A row reads `pass`, `FAIL` (and the first difference), `did not finish` (a busy PC: run it again) or `not run: needs
X` (what to make, and how); the exit status is 0 only when every row passed. A playback passes with 0 steps
differing. A PC's own busy check and build locks are used where they are there (`port/setup/lib.sh`).

## Games' limits

The rows that start Quick Play visits, each with the limit of its games (`MINUTES` and a minute for the stop;
`tests/test_game_limits.py` holds `gates.sh` to these lines):

- **`quickplay`** (7 min; its games' limit 15 min: `MINUTES=14` and a minute). Two launchers, a watcher, simulated players, two races on a local server
- **`thirty`** (5 min; its games' limit 11 min: `MINUTES=10` and a minute). Three games and 27 simulated players, five laps, to the finish
- **`service`** (its games' limit 13 min: `MINUTES=12` and a minute). Quick Play on the real online service
