"""Every path of the repository that a script under port/gates names is there: the scripts call each other by path,
and a move that left one behind would show only in the game run that reaches it. Run by scripts/check.sh."""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
GATES = os.path.dirname(HERE)
ROOT = os.path.normpath(os.path.join(GATES, "..", ".."))
# the folders of the repository under port/ (the work folder has a port folder of its own: runs, scratch, launchers)
NAMED = re.compile(r"(?<![\w./\\-])port/(?:gates|build|setup|image|configs|moderngekko|facts|core|handbook)/[\w./-]*\w")
# beside the script itself: "$here/x", "$(dirname "$0")/x", f"{here}/x"
BESIDE = re.compile(r"""(?:\$here|\$\(dirname "\$0"\)|\{here\})/([\w./-]*\w)""")


def scripts():
    # the gates are a repository of their own since the split (piconet-gates, checked out at the runner's port/gates,
    # which the runner's own git ignores): their files are listed by their own git, as paths of the runner's root
    listed = subprocess.run(["git", "ls-files"], cwd=GATES, capture_output=True, text=True, check=True)
    return ["port/gates/" + p for p in listed.stdout.split() if p.endswith((".sh", ".py")) and "/tests/" not in "/" + p]


class Paths(unittest.TestCase):
    def test_every_script_is_looked_at(self):
        self.assertGreater(len(scripts()), 25)

    def test_a_path_of_the_repository_named_in_a_script_exists(self):
        missing = []
        for script in scripts():
            with open(os.path.join(ROOT, script), encoding="utf-8") as f:
                text = f.read()
            for path in sorted(set(NAMED.findall(text))):
                if not os.path.exists(os.path.join(ROOT, path)):
                    missing.append(f"{script} names {path}")
            for path in sorted(set(BESIDE.findall(text))):
                if not os.path.exists(os.path.join(ROOT, os.path.dirname(script), path)):
                    missing.append(f"{script} names {path} beside itself")
        self.assertEqual(missing, [])

    def test_the_root_a_script_works_out_is_the_repository(self):
        # "$here/../.." in a script two folders down, one more "../" in a folder below
        for script in scripts():
            with open(os.path.join(ROOT, script), encoding="utf-8") as f:
                text = f.read()
            for up in re.findall(r"""(?:\$here|\$\(dirname "\$0"\))/((?:\.\./)*\.\.)["/ ]""", text):
                at = os.path.normpath(os.path.join(ROOT, os.path.dirname(script), up))
                self.assertIn(at, (ROOT, os.path.join(ROOT, "port"), GATES), f"{script}: {up}")
            for up in re.findall(r"""cd "\$here/((?:\.\./)+\.\.)" """, text + " "):
                self.assertEqual(os.path.normpath(os.path.join(ROOT, os.path.dirname(script), up)), ROOT, script)


if __name__ == "__main__":
    unittest.main()
