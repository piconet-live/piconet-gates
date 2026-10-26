"""launch-file.py: a run's launch file written from a named one of port/configs. Run by scripts/check.sh."""
import json
import os
import re
import subprocess
import tempfile
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "setup"))
import parts  # noqa: E402  the other parts' checkouts (port/setup/pins.tsv): the protocol's formats, the launcher's code
TOOL = os.path.join(HERE, "..", "runs", "launch-file.py")
CONFIGS = os.path.join(HERE, "..", "..", "configs")


def run(*args):
    done = subprocess.run(["python3", TOOL, *args], capture_output=True, text=True, timeout=60)
    return done.returncode, done.stdout.strip(), done.stderr.strip()


class LaunchFile(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.dir.name, "launch", "run.json")

    def tearDown(self):
        self.dir.cleanup()

    def test_a_named_file_with_its_places_filled(self):
        status, printed, _ = run("forced-race-2x3-9-17", self.out, "bundle=C:\\Some\\b", "replay=C:\\r\\race.fzrp")
        self.assertEqual((status, printed), (0, self.out))
        made = json.load(open(self.out))
        self.assertEqual(made["bundle"], "C:\\Some\\b")
        self.assertEqual(made["replay"], {"file": "C:\\r\\race.fzrp"})
        self.assertEqual(made["debug"], {"forceRollback": {"every": 2, "depths": [3, 9, 17]}})

    def test_every_test_game_shows_the_frame_rate_unless_its_file_says_otherwise(self):
        # the owner, 2026-10-18: the frame rate in the game window in all tests; a harness run's too
        for args in (("playback", "bundle=b", "replay=r"), ("gate-scene", "bundle=b", "run=C:\\r", "--harness", "race300")):
            status, _, said = run(args[0], self.out, *args[1:])
            self.assertEqual(status, 0, said)
            self.assertIs(json.load(open(self.out))["showFrameRate"], True)
        status, _, _ = run("playback", self.out, "bundle=b", "replay=r", "--set", "showFrameRate=false")
        self.assertEqual(status, 0)
        self.assertIs(json.load(open(self.out))["showFrameRate"], False)

    def test_the_file_is_named_as_windows_names_it_on_any_drive(self):
        # a work folder on another drive than C: (the final build's is on D:): the runner was given /mnt/d/...
        import importlib.util
        spec = importlib.util.spec_from_file_location("launch_file", TOOL)
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        self.assertEqual(tool.windows("/mnt/c/Some/w/port/launch/a.json"), "C:\\Some\\w\\port\\launch\\a.json")
        self.assertEqual(tool.windows("/mnt/d/Some/w/port/launch/a.json"), "D:\\Some\\w\\port\\launch\\a.json")
        self.assertEqual(tool.windows("/tmp/x/a.json"), "/tmp/x/a.json")

    def test_one_more_key_by_its_dotted_name(self):
        status, _, _ = run("playback", self.out, "bundle=b", "replay=r", "run=C:\\runs\\x", "--set", "debug.lateSteps=5",
                           "--set", "debug.trace={run}\\trace.csv")
        self.assertEqual(status, 0)
        self.assertEqual(json.load(open(self.out))["debug"], {"lateSteps": 5, "trace": "C:\\runs\\x\\trace.csv"})

    def test_a_harness_run_says_in_its_launch_file_what_the_harness_needs_of_the_game(self):
        # a scene from a saved state, with the manifest's own scenes: the saved state and the automation folder
        # allowed, the user folder's emulator settings left as the harness wrote them, the probe in the run's folder,
        # the scene's pad script, the timers, its dumps
        status, _, said = run("gate-scene", self.out, "bundle=b", "run=C:\\runs\\g1", "--harness", "race300")
        self.assertEqual(status, 0, said)
        self.assertEqual(json.load(open(self.out))["debug"],
                         {"forcePatches": True, "automation": True, "userSettings": True,
                          "probe": "C:\\runs\\g1\\probe.csv", "pad": "0:100", "taskTimers": True,
                          "taskDumps": "600,1200,2000", "loadState": True})
        # the reference of the same scene asks for the emulator's own compiler, and has no bundle
        status, _, said = run("gate-scene-reference", self.out, "run=C:\\runs\\g2", "--harness", "racego")
        self.assertEqual(status, 0, said)
        made = json.load(open(self.out))
        self.assertNotIn("bundle", made)
        self.assertTrue(made["debug"]["jit"] and made["debug"]["loadState"] and made["debug"]["automation"])
        self.assertTrue(made["debug"]["userSettings"])
        status, _, said = run("gate-scene-reference-single-core", self.out, "run=C:\\runs\\g4", "--harness", "racego")
        self.assertEqual(status, 0, said)
        self.assertTrue(json.load(open(self.out))["debug"]["singleCore"])
        # a scene of another manifest that boots: no saved state, no dumps; a key the file holds is kept
        manifest = os.path.join(self.dir.name, "manifest.toml")
        with open(manifest, "w") as f:
            f.write('[[scene]]\nname = "adhoc"\nreach = "boot"\ninput = "0:0"\nfields = 100\n')
        status, _, said = run("playback", self.out, "bundle=b", "replay=r", "run=C:\\runs\\p1", "--set", "debug.pad=neutral",
                              "--harness", "adhoc", "--manifest", manifest)
        self.assertEqual(status, 0, said)
        self.assertEqual(json.load(open(self.out))["debug"],
                         {"pad": "neutral", "automation": True, "userSettings": True,
                          "probe": "C:\\runs\\p1\\probe.csv"})
        # a scene that is not there, and a run's folder nobody named
        status, _, said = run("playback", self.out, "bundle=b", "replay=r", "run=x", "--harness", "no-such-scene")
        self.assertEqual(status, 1)
        self.assertIn("has no scene 'no-such-scene'", said)
        status, _, said = run("playback", self.out, "bundle=b", "replay=r", "--harness", "race300")
        self.assertEqual(status, 1)
        self.assertIn("{run} is not filled", said)

    def test_a_place_nobody_filled_and_a_file_that_is_not_there(self):
        status, _, said = run("playback", self.out, "bundle=b")
        self.assertEqual(status, 1)
        self.assertIn("{replay} is not filled", said)
        self.assertFalse(os.path.exists(self.out))
        status, _, said = run("no-such-set-up", self.out)
        self.assertEqual(status, 1)
        self.assertIn("playback-race-late-2", said)   # it lists what there is

    def test_every_named_file_says_what_it_is_for_and_who_uses_it(self):
        names = sorted(n for n in os.listdir(CONFIGS) if n.endswith(".json"))
        self.assertGreaterEqual(len(names), 17)
        for name in names:
            config = json.load(open(os.path.join(CONFIGS, name)))
            self.assertGreater(len(config.get("about", "")), 40, name)
            self.assertRegex(config["about"], r"\(.*(\.sh|scenes)", name)

    def test_the_adapter_applies_what_the_core_decides_for_the_picture_and_the_window(self):
        # No test compiles the runner's adapter (it is the emulator's and Windows' side). What it decides about a
        # picture's way, the window's kept place and the backend's full screen is plain state in the core, tested
        # there (port/core/tests/test_screen.cpp, test_place.cpp); here the adapter's source is held to using it:
        # the lines that apply each decision, by their text. A line dropped or rewritten past the core fails here.
        def text(name):
            with open(os.path.join(HERE, "..", "..", "moderngekko", "src", name), encoding="utf-8") as f:
                return " ".join(f.read().split())
        pictures, screen, frame = text("pictures.cpp"), text("screen.cpp"), text("frame_screen.cpp")
        # "console" and "copy" need the emulator's Immediately Present XFB; "console" alone holds its pictures
        self.assertIn("fzgx::present::SetupOf(fzgx::present::WayOf(o.present, o.debug.single_core))", pictures)
        self.assertIn("if (setup.immediate_xfb) Config::SetCurrent(Config::GFX_HACK_IMMEDIATE_XFB, true);", pictures)
        self.assertIn("s_holds = setup.holds;", pictures)
        # held for their time by the emulator's GPU loop, never by a wait: no thread of the runner sleeps for it
        self.assertIn("if (setup.holds) VideoCommon::Presenter::SetImmediateSwapHold(TheMoment);", pictures)
        # (a drawn frame between two steps, fzgx/hfr.h: its own time, a fraction of a field after the true picture's,
        # and the longer limit; every other picture its first line's time and the 4 ms limit, as before)
        self.assertIn("TimePoint due = picture.intended_present_time; long long most = fzgx::present::MOST_WAIT_US;", pictures)
        self.assertIn("switch (fzgx::present::At(left.count(), most))", pictures)
        self.assertIn("case fzgx::present::Moment::Wait: ++s_held; return due;", pictures)
        self.assertIn("s_drawn = setup.holds && fzgx::hfr::On();", pictures)
        self.assertNotIn("SleepUntil", pictures)
        # the backend is asked right before every present
        self.assertIn("DrawPanel(); // (panel.cpp: before a race only; one load of a flag otherwise) DrawOverlays(); "
                      "// (spectator_overlay.cpp: the course map, the replay bar, its lanes, the standings) "
                      "FollowFullscreen();", pictures)
        # what is asked of the backend and when, and a refusal: the core's two functions, and what each answer does
        self.assertIn("switch (fzgx::screen::Before(s_screen.ask, wanted, g_gfx->IsFullscreen()))", screen)
        self.assertIn("case fzgx::screen::Tell::Ask: g_gfx->SetFullscreen(true); break;", screen)
        self.assertIn("case fzgx::screen::Tell::GiveBack: g_gfx->SetFullscreen(false); break;", screen)
        self.assertIn("if (fzgx::screen::After(s_screen.ask, held)) g_gfx->SetFullscreen(false);", screen)
        self.assertIn("s_state.options.full_screen != fzgx::screen::EXCLUSIVE", screen)
        # the window's place: read, the restore begun before the window is moved, written only by the tracker's word
        restore = frame[frame.index("bool RestorePlace("):frame.index("void KeepPlace(")]
        self.assertLess(restore.index("s_screen.place.BeginRestore(*kept);"), restore.index("SetWindowPos("))
        self.assertLess(restore.index("SetWindowPos("), restore.index("PostMessageW(window, PLACE_RESTORED, 0, 0);"))
        self.assertIn("s_screen.place.Note(seen); if (const std::optional<place::Kept> now = s_screen.place.ToWrite(); "
                      "now && place::WriteKept(UserFolder(), *now)) s_screen.place.Written(*now);", frame)
        self.assertIn("if (message == PLACE_RESTORED) s_screen.place.Restored();", frame)
        # leaving full screen: the thread that presents is told before the window changes
        leave = frame[frame.index("void SetFullscreen("):frame.index("bool FullscreenKey(")]
        self.assertLess(leave.index("TellFullscreen(false);"), leave.index("SetWindowLongPtrW(window, GWL_STYLE, s_screen.windowed_style);"))

    def test_the_settings_userSettings_leaves_to_the_files_are_as_many_as_the_pages_say(self):
        # "debug.userSettings" leaves to the user folder every emulator setting the runner otherwise sets itself: one
        # Set or Stock call of pins.cpp each. The format's page says how many there are, and
        # a setting added to the list or taken from it changes that number
        root = os.path.join(HERE, "..", "..", "..")
        with open(os.path.join(root, "port", "moderngekko", "src", "pins.cpp"), encoding="utf-8") as f:
            names = re.findall(r"^ +(?:Set|Stock)\(Config::(\w+)", f.read(), re.M)
        self.assertGreater(len(names), 0, "no Set or Stock call was found in pins.cpp")
        self.assertEqual(len(names), len(set(names)), "a setting is set twice")
        with open(parts.path_in("REPO_PROTOCOL", "protocol/formats.md"), encoding="utf-8") as f:
            said = re.search(r"\((\d+); `port/moderngekko/src/pins\.cpp`\)", f.read())
        self.assertEqual(said and int(said.group(1)), len(names), "protocol/formats.md, section 2")

    def test_the_settings_that_can_drop_the_pictures_interrupt_are_set_with_the_pace(self):
        # an emulator that is behind by more than [Core] MaxFallback milliseconds gives the lost time up, and with
        # GFX.ini's [Hacks] VISkip on it then leaves out the picture's interrupt, which the game counts its fields
        # by (the review of the lockdown, 8 October). Both are set with the pace's settings, at the stock value,
        # and the format's page names both where it lists them
        root = os.path.join(HERE, "..", "..", "..")
        with open(os.path.join(root, "port", "moderngekko", "src", "pins.cpp"), encoding="utf-8") as f:
            pace = re.search(r"^void PinPace\(\)\n\{\n(.*?)^\}", f.read(), re.M | re.S).group(1)
        for name in ("MAIN_MAX_FALLBACK", "GFX_HACK_VI_SKIP"):
            self.assertIn(f"  Stock(Config::{name});\n", pace)
        with open(parts.path_in("REPO_PROTOCOL", "protocol/formats.md"), encoding="utf-8") as f:
            row = next(line for line in f if line.startswith("| How fast the game runs |"))
        self.assertIn("`MaxFallback`", row)
        self.assertIn("`[Hacks] VISkip`", row)

    def test_an_alert_of_the_emulators_is_no_message_box_whatever_the_user_folder_says(self):
        # [Interface] UsePanicHandlers on shows an alert as a message box, which holds the game until somebody
        # answers it. The launcher writes it off into a new user folder; the runner sets it off for the run, so a
        # file that says otherwise changes nothing (and is named in the game's log, as every setting set here)
        root = os.path.join(HERE, "..", "..", "..")
        with open(os.path.join(root, "port", "moderngekko", "src", "pins.cpp"), encoding="utf-8") as f:
            self.assertIn("  Set(Config::MAIN_USE_PANIC_HANDLERS, false);\n", f.read())
        with open(parts.path_in("REPO_PROTOCOL", "protocol/formats.md"), encoding="utf-8") as f:
            row = next(line for line in f if line.startswith("| The console, and a debugger's doors |"))
        self.assertIn("`UsePanicHandlers` off", row)
        with open(parts.path_in("REPO_LAUNCHER", "net/src/Launcher.Core/Files/RecompLaunch.UserFolder.cs"), encoding="utf-8") as f:
            self.assertIn('("Interface", "UsePanicHandlers", "False")', f.read())


if __name__ == "__main__":
    unittest.main()
