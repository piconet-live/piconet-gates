"""A test's launcher is silent (the project's standing rule 4): every script under port/ that writes a launcher's
settings.json puts "soundMuted": true in it. The launcher makes sounds of its own since 0.2.0 (the lobby's three
tones, at volume 50 unless the settings say otherwise), and --mute reaches only the game.

The fault this holds: quickplay-run.sh wrote its launchers' settings without it, so a scripted Quick Play run on the
owner's PC would have sounded at every vote, machine stage and race start."""

import os
import re
import unittest

PORT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


def scripts():
    for folder, _, names in os.walk(PORT):
        if os.sep + "tests" in folder[len(PORT):] or "__pycache__" in folder:
            continue
        for name in names:
            if name.endswith((".sh", ".ps1", ".py", ".cmd")):
                yield os.path.join(folder, name)


class EveryWrittenLauncherSettingsFileIsMuted(unittest.TestCase):
    def test_a_line_that_writes_settings_json_has_the_mute_just_before_it(self):
        writers = []
        for path in scripts():
            with open(path, encoding="utf-8", errors="replace") as file:
                lines = file.read().split("\n")
            for number, line in enumerate(lines):
                # written: a redirection into it, or a write call that names it
                if re.search(r">\s*\"?[^\"\s]*settings\.json", line) or re.search(r"(write|dump)\w*\(.*settings\.json", line):
                    writers.append((os.path.relpath(path, PORT), number + 1, "\n".join(lines[max(0, number - 3):number + 1])))
        self.assertTrue(writers, "no script under port/ writes a launcher's settings.json: has the search gone blind?")
        for path, number, text in writers:
            with self.subTest(script=path, line=number):
                self.assertIn("soundMuted", text)
                self.assertRegex(text, r"soundMuted\W+true")


if __name__ == "__main__":
    unittest.main()
