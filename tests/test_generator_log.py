"""The generator log's reader (port/gates/reports/generator-log.py) on made-up data windows. No game data."""
import os, subprocess, sys, tempfile, unittest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "..", "facts", "generated"))
import facts

SCRIPT = os.path.join(here, "..", "reports", "generator-log.py")


def window(step, final, words):
    """A data window dumped before `step`: `words(s)` gives the two words step s left."""
    win = bytearray(facts.WINDOW_END - facts.WINDOW)
    put = lambda a, v: win.__setitem__(slice(a - facts.WINDOW, a - facts.WINDOW + 4), (v & 0xFFFFFFFF).to_bytes(4, "big"))
    put(facts.STEP_AT, step); put(facts.FINAL_STEPS_AT, final)
    for s in range(max(0, step - facts.GENERATOR_LOG_STEPS), step):
        at = facts.GENERATOR_LOG + 8 * (s & (facts.GENERATOR_LOG_STEPS - 1))
        put(at, words(s)[0]); put(at + 4, words(s)[1])
    return bytes(win)


class TheGeneratorLog(unittest.TestCase):
    def read(self, a, b):
        with tempfile.TemporaryDirectory() as folder:
            files = [os.path.join(folder, name) for name in ("a.win", "b.win")]
            for path, data in zip(files, (a, b)):
                with open(path, "wb") as f:
                    f.write(data)
            done = subprocess.run([sys.executable, SCRIPT, *files], capture_output=True, text=True)
            return done.returncode, done.stdout.strip().split("\n")

    def test_two_games_whose_words_are_equal(self):
        race = lambda s: (s * 7 + 1, s * 13 + 5)
        status, out = self.read(window(5000, 4990, race), window(5000, 4985, race))
        self.assertEqual(status, 0, out)
        first = 5000 - facts.GENERATOR_LOG_STEPS
        self.assertEqual(out[1], f"the executable's generator: steps {first} to 4984 compared ({4985 - first}), 0 differ")
        self.assertEqual(out[2], f"the effects' generator: steps {first} to 4984 compared ({4985 - first}), 0 differ")

    def test_a_word_that_differs_is_named_with_its_first_step(self):
        race = lambda s: (s * 7 + 1, s * 13 + 5)
        watcher = lambda s: (s * 7 + 1 + (s >= 4000), s * 13 + 5)
        status, out = self.read(window(5000, 4990, race), window(5000, 4990, watcher))
        self.assertEqual(status, 1)
        self.assertIn("990 differ, first at step 4000 (00006D61 and 00006D62)", out[1])
        self.assertTrue(out[2].endswith("0 differ"))

    def test_steps_that_are_not_final_are_not_compared(self):
        race = lambda s: (s, s)
        guess = lambda s: (s + (s >= 4990), s)                       # a prediction's entries, not yet run again
        status, out = self.read(window(5000, 4990, race), window(5000, 4990, guess))
        self.assertEqual(status, 0, out)
        status, out = self.read(window(100, 0, race), window(100, 0, race))
        self.assertEqual((status, out[-1]), (1, "no step is in both logs and final in both games: nothing compared"))


if __name__ == "__main__":
    unittest.main()
