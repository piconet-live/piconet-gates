"""The profile is trained on its own runner (scripts/release-build.sh): AGAIN=1 and RUNNER=FILE for runs/profile.sh
(moved from port/setup/tests/test_again.py with the script). Its dry runs in a made-up work folder: nothing is built
and no game is started."""
import os, shutil, subprocess, tempfile, unittest

root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
PROFILE = "port/gates/runs/profile.sh"


@unittest.skipUnless(shutil.which("wslpath"), "needs WSL's wslpath")
class Profile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = self.tmp.name
        clean = {k: v for k, v in os.environ.items() if k not in ("AGAIN", "RUNNER", "PROFILE", "BUNDLE", "PROGRESS_RUN")}
        self.env = {**clean, "PORT_WORK": self.work, "PORT_LOCKS": self.work}

    def dry(self, script, **env):
        done = subprocess.run([os.path.join(root, script), "t1", "--dry-run"], env={**self.env, **env}, capture_output=True, text=True)
        return done.stdout + done.stderr

    def test_the_profile_is_trained_on_the_runner_named(self):
        self.assertIn("  the two games run on ModernGekko/build/moderngekko-run.exe\n", self.dry(PROFILE))
        kept = os.path.join(self.work, "port", "runner-t1", "moderngekko-run.exe")
        said = self.dry(PROFILE, RUNNER=kept)
        self.assertIn("  the two games run on port/runner-t1/moderngekko-run.exe\n", said)
        self.assertIn(f"profile: missing {kept}\n", said)                        # it is that file the script asks for
        self.assertIn("profile: RUNNER must be a file under", self.dry(PROFILE, RUNNER="/elsewhere/moderngekko-run.exe"))


if __name__ == "__main__":
    unittest.main()
