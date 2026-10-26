#!/usr/bin/env python3
"""launch-file.py CONFIG OUT [NAME=VALUE ...] [--set KEY=JSON ...] [--harness SCENE [--manifest FILE]]: writes a
run's launch file (the runner's --config FILE; protocol/formats.md section 2) from a named one of port/configs.

CONFIG is a file of port/configs without its .json (playback), or a path. A text in it may hold places in
braces ({bundle}, {replay}, {run}): each NAME=VALUE fills one, and a place nobody filled is an error. --set
KEY=JSON sets one more key, by its dotted name (debug.lateSteps=2, debug.trace='{run}\\trace.csv'); a value that
is no JSON is taken as text, and its places are filled too. For a one-off: a set-up a gate or a script uses gets a
file of its own in port/configs instead.

--harness SCENE: the run is one of the harness (recomp.py run --scene SCENE). The harness starts the
runner with its automation folder, for a scene from a saved state with --load-state, and puts the probe's file,
the scene's pad script, the task timers and the scene's memory dumps into the game's environment. In a start with
a launch file the runner refuses those two options and reads none of those variables unless the file's "debug"
part says so: this adds the keys that say it ("automation", "loadState", "probe" in the run's folder, "pad",
"taskTimers", "taskDumps"), from the scene of the manifest (--manifest FILE; default recomp/manifest.toml), and
"userSettings": the harness's user folder holds the run's emulator settings (no speed limit, the fixed clock),
which the runner otherwise sets itself whatever the folder says. A key the named file already holds is kept. It
needs run=FOLDER, the run's folder as Windows names it.

Every file it writes shows the frame rate in the game window's strip ("showFrameRate": true; the owner,
2026-10-18: in all tests), unless the named file or a --set says otherwise. Picture only: nothing simulated
changes, and a headless start has no strip.

The game's reader is the judge of the result (it refuses a key it does not know); this script only refuses what
it can see without the game: a file that is no JSON object, no "about" line, an unfilled place.
Prints OUT as a Windows path when it is on a Windows drive (/mnt/<letter>/), for the runner's --config.
"""
import json
import pathlib
import re
import sys
import tomllib

CONFIGS = pathlib.Path(__file__).resolve().parents[2] / "configs"
MANIFEST = pathlib.Path(__file__).resolve().parents[3] / "recomp" / "manifest.toml"


def harness_keys(config, scene_name, manifest_path):
    """The "debug" keys a harness run of this scene needs (what the harness's actions.run_env and run_args give the
    runner), put into `config` where it does not hold them."""
    try:
        manifest = tomllib.loads(pathlib.Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"launch-file: --harness: the manifest {manifest_path} cannot be read: {e}")
    scene = next((s for s in manifest.get("scene", []) if s.get("name") == scene_name), None)
    if scene is None:
        raise SystemExit(f"launch-file: --harness: {manifest_path} has no scene '{scene_name}'")
    debug = config.setdefault("debug", {})
    if not isinstance(debug, dict):
        raise SystemExit("launch-file: --harness: \"debug\" is not an object in the file")
    debug.setdefault("automation", True)
    debug.setdefault("userSettings", True)
    debug.setdefault("probe", "{run}\\probe.csv")
    if scene.get("input"):
        debug.setdefault("pad", scene["input"])
    if manifest.get("probe", {}).get("timer"):
        debug.setdefault("taskTimers", True)
    if scene.get("dump_steps"):
        debug.setdefault("taskDumps", ",".join(str(step) for step in scene["dump_steps"]))
    if scene.get("reach") == "savestate":
        debug.setdefault("loadState", True)


def fill(value, places, used):
    """The value with every {name} of its texts filled from `places`."""
    if isinstance(value, dict):
        return {key: fill(member, places, used) for key, member in value.items()}
    if isinstance(value, list):
        return [fill(member, places, used) for member in value]
    if not isinstance(value, str):
        return value

    def one(match):
        name = match.group(1)
        if name not in places:
            raise SystemExit(f"launch-file: the place {{{name}}} is not filled: give {name}=VALUE")
        used.add(name)
        return places[name]
    return re.sub(r"\{([a-z_]+)\}", one, value)


def put(config, dotted, value):
    """Sets config[a][b][c] for the dotted name a.b.c."""
    *path, last = dotted.split(".")
    for key in path:
        config = config.setdefault(key, {})
        if not isinstance(config, dict):
            raise SystemExit(f"launch-file: --set {dotted}: {key} is not an object in the file")
    config[last] = value


def windows(path):
    text = str(path)
    drive = re.match(r"/mnt/([a-z])/", text)   # a Windows drive as WSL mounts it, whichever letter
    return f"{drive.group(1).upper()}:\\" + text[drive.end():].replace("/", "\\") if drive else text


def main(argv):
    if len(argv) < 2 or argv[0].startswith("-"):
        raise SystemExit(__doc__)
    name, out, places, sets, rest = argv[0], pathlib.Path(argv[1]), {}, [], argv[2:]
    scene, manifest = None, MANIFEST
    while rest:
        word = rest.pop(0)
        if word in ("--harness", "--manifest"):
            if not rest:
                raise SystemExit(f"launch-file: {word} takes a value")
            if word == "--harness":
                scene = rest.pop(0)
            else:
                manifest = rest.pop(0)
        elif word == "--set":
            if not rest or "=" not in rest[0]:
                raise SystemExit("launch-file: --set takes KEY=JSON")
            sets.append(rest.pop(0).split("=", 1))
        elif "=" in word and not word.startswith("-"):
            key, value = word.split("=", 1)
            places[key] = value
        else:
            raise SystemExit(f"launch-file: {word} is neither NAME=VALUE nor --set KEY=JSON")
    source = pathlib.Path(name) if name.endswith(".json") else CONFIGS / f"{name}.json"
    if not source.is_file():
        have = ", ".join(sorted(p.stem for p in CONFIGS.glob("*.json")))
        raise SystemExit(f"launch-file: no launch file {source} (port/configs has: {have})")
    try:
        config = json.loads(source.read_text(encoding="utf-8"))
    except ValueError as e:
        raise SystemExit(f"launch-file: {source} is not JSON: {e}")
    if not isinstance(config, dict) or not isinstance(config.get("about"), str) or not config["about"]:
        raise SystemExit(f"launch-file: {source} is not an object with an \"about\" line")
    for key, text in sets:
        try:
            value = json.loads(text)
        except ValueError:
            value = text
        put(config, key, value)
    config.setdefault("showFrameRate", True)
    if scene is not None:
        harness_keys(config, scene, manifest)
    config = fill(config, places, set())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    print(windows(out))


if __name__ == "__main__":
    main(sys.argv[1:])
