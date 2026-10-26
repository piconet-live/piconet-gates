"""The gates find the runner they test by their pins.tsv REPO_RUNNER (runner.sh), and the runner names the gates by
its port/setup/pins.tsv REPO_GATES: the pair must name each other (the gates are private, piconet-gates, checked out
at the runner's port/gates: the plan-repo-split notes, section 1)."""
import os, shutil, subprocess, tempfile, unittest

gates = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
root = os.path.abspath(os.path.join(gates, "..", ".."))


def source(folder):
    done = subprocess.run(["bash", "-c", '. "$0/runner.sh" && printf "%s\\n%s" "$root" "$GATES_DIR"', folder],
                          capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


class RunnerPin(unittest.TestCase):
    def test_the_gates_here_find_this_runner(self):
        status, out, err = source(gates)
        self.assertEqual(status, 0, err)
        found, named = out.split("\n")
        self.assertEqual(found, root)
        self.assertTrue(os.path.samefile(named, gates))

    def test_gates_the_runner_does_not_name_are_refused(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            for name in ("runner.sh", "pins.tsv"):
                shutil.copy(os.path.join(gates, name), elsewhere)
            with open(os.path.join(elsewhere, "pins.tsv"), "w") as f:
                f.write(f"name\tvalue\tnote\nREPO_RUNNER\t{os.path.relpath(root, elsewhere)}\tthis runner\n")
            status, _, err = source(elsewhere)
            self.assertEqual(status, 1)
            self.assertIn("(its pins.tsv REPO_GATES), not " + os.path.realpath(elsewhere), err)

    def test_no_runner_where_the_pin_says_is_said(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            shutil.copy(os.path.join(gates, "runner.sh"), elsewhere)
            with open(os.path.join(elsewhere, "pins.tsv"), "w") as f:
                f.write("name\tvalue\tnote\nREPO_RUNNER\tno-runner\tnone here\n")
            status, _, err = source(elsewhere)
            self.assertEqual(status, 1)
            self.assertIn("no runner checkout at", err)


if __name__ == "__main__":
    unittest.main()
