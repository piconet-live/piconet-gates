# port/gates/reports: what a run's logs say

Readers only: each takes a run's name (`<work>/port/runs/RUN`) or a log file, starts nothing and writes nothing.
Which log holds what: the port handbook, "Read the pacing and rollback logs".

| File | What |
|---|---|
| `board-report.py` | `board-run.sh`'s verdict: the launcher's board lines (taken, phases, snapshots, a freeze judged and its end, the game's own report) and the game's launch file |
| `run-summary.py` | A run in one form: modes by field, time per field while racing, the core's lines; two runs' machine hashes compared per step (rows `b19`, `match`, `offline`) |
| `pace-report.py` | A pacing log's stalls: a present call over 12 ms, two pictures over 25 ms apart |
| `pace-start.py` | A race's start in a pacing log: long fields at the start gate, the catch-up after the go (row `start`) |
| `rollback-report.py` | A rollback log's cost per depth |
| `freeze-report.py` | What a game's log says of a freeze and of its stop: each freeze's reports, the stop line, the summary's three words; `--map PROGRAM=FILE` names the call stacks' places from a linker's map; `--expect-test` judges `freeze-run.sh` |
| `latency-report.py` | Pad to picture in a race, from the pacing log, the rollback log and the recording (each press followed from the field that read it to the present call that shows its step); the present calls' intervals and where in the field a picture is shown; rollback depth, the game thread's time a field and the fields over 16.68 ms; several runs: whether their recordings are one race. Offline play: the pictures' timing only |
| `map-report.py`, `map-pace.py`, `map_lib.py` | A measuring run of `map-run.sh`: where the game thread's and the video thread's time goes, by host place and by guest place, from the sampler's records; a scene's fields, pictures and video thread from the pacing log alone; what both read with |
| `options-report.py` | A run of `options-run.sh`: what each game's seat sent with its controller options, the two recordings one race |
| `stat-pack-report.py` | A run of `stat-pack-run.sh` (`--only PART`: one part): the races without a pack unchanged (one game against the JIT reference; two games with rollbacks against the build from before stat packs), the pack laid and one race in two games among computer racers, the weight in the racers' blocks, two packs caught, the whole-file pack from a server through Quick Play, the repository's pack in two games, the refused packs |
| `pair-report.py` | A two-game run: steps both recorded, checksums equal, rollbacks, pictures (row `pair`) |
| `spectator-log.py` | A game's spectator log (a `debug.dump` of the data window) beside its rollback log: what was chosen and what the cameras held, a line a displayed frame; exit status 1 when the cameras did not hold a choice |
| `generator-log.py` | The race's two generator words in two games, step by step, from `debug.dump`s of both data windows at one step; exit status 1 when a word differs |
| `smoothing-log.py` | The rivals' smoothing log of a game (a `debug.dump` of its data window): how far a rollback's correction pointed off the road, which the image cuts for a machine on the road, and how far a rival's shadow was from its drawn body |
| `quickplay-report.py` | A Quick Play run: each launcher's races, pictures lost by depth (rows `quickplay`, `thirty`) |

The verdicts are not here: `../gate-judge.py` says whether a run passes.
