"""The smoothing log's reader (port/gates/reports/smoothing-log.py) on a made-up data window. No game data."""
import os, struct, subprocess, sys, tempfile, unittest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "..", "facts", "generated"))
import facts

SCRIPT = os.path.join(here, "..", "reports", "smoothing-log.py")


class TheSmoothingLog(unittest.TestCase):
    def half(self, value):
        """The upper half of the float, as the image logs a size; test values are exact in it."""
        return struct.unpack(">H", struct.pack(">f", value)[:2])[0]

    def read(self, frames, entry, counters=None):
        win = bytearray(facts.WINDOW_END - facts.WINDOW)
        for at, value in (counters or {}).items():                  # the effects' counters: word or float
            struct.pack_into(">f" if isinstance(value, float) else ">I", win, facts.EFFECTS_AT - facts.WINDOW + at, value)
        win[facts.SMOOTH_FRAMES_AT - facts.WINDOW:][:4] = frames.to_bytes(4, "big")
        struct.pack_into(">I", win, facts.SMOOTH_FRAMES_AT - facts.WINDOW, frames)
        for k in range(max(1, frames - facts.SMOOTH_LOG_FRAMES + 1), frames + 1):
            step, seat, flags, part, shadow = entry(k)
            struct.pack_into(">HBBHH", win, facts.SMOOTH_LOG - facts.WINDOW + 8 * (k % facts.SMOOTH_LOG_FRAMES), step, seat,
                             flags, self.half(part), self.half(shadow * shadow))
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "d.win")
            with open(path, "wb") as f:
                f.write(win)
            done = subprocess.run([sys.executable, SCRIPT, path], capture_output=True, text=True)
            return done.returncode, done.stdout.strip().split("\n")

    def test_the_rollback_frames_parts(self):
        # a rollback every fourth frame, the part a multiple of 1/8 growing with the frame; frame 400 is the largest
        part = lambda k: (k // 4) / 8 if k % 4 == 0 else 9.0
        status, out = self.read(400, lambda k: (k, k % 30, 3 if k % 4 == 0 else 1, part(k), 0.0))
        self.assertEqual(status, 0, out)
        self.assertEqual(out[0], "400 frames in the log (of 400 race frames), 100 with a rollback, 0 on which the "
                                 "smoothing started over")
        self.assertIn("largest 12.50; over 1: 92, over 5: 60", out[1])
        self.assertTrue(out[2].startswith("the ten largest: 12.5 (step 400, seat 10), 12.4 (step 396, seat 6)"), out[2])
        self.assertIn("largest 0.00; over 1: 0, over 5: 0", out[3])

    def test_the_shadows_distance_and_the_drawing_as_it_was(self):
        # the shadow 8 from the body on one frame in ten, 0.5 on the others; the tests' two flags
        status, out = self.read(200, lambda k: (k, 2, 3 | 8 | 16, 1.0, 8.0 if k % 10 == 0 else 0.5))
        self.assertEqual(out[0], "200 frames in the log (of 200 race frames), 200 with a rollback, 0 on which the "
                                 "smoothing started over (the drawing as it was: "
                                 "the part off the road left in, the shadows left where they were)")
        self.assertEqual(out[3], "a drawn body to its shadow along the road, every frame: middle 0.50, nine in ten below "
                                 "8.00, 99 in a hundred below 8.00, largest 8.00; over 1: 20, over 5: 20")
        self.assertTrue(out[4].startswith("the five largest: 8.0 (step "), out[4])

    def test_a_log_that_went_round_and_one_without_a_rollback(self):
        frames = facts.SMOOTH_LOG_FRAMES + 500
        status, out = self.read(frames, lambda k: (k & 0xFFFF, 1, 3, 2.0, 0.0))
        self.assertEqual(out[0], f"{facts.SMOOTH_LOG_FRAMES} frames in the log (of {frames} race frames), "
                                 f"{facts.SMOOTH_LOG_FRAMES} with a rollback, 0 on which the smoothing started over")
        # one frame in ten started over, and the race's first frame, which is not counted
        status, out = self.read(50, lambda k: (k, 1, 0 if k % 10 == 0 or k == 1 else 1, 0.5, 0.0))
        self.assertEqual((status, out), (0, ["50 frames in the log (of 50 race frames), 0 with a rollback, 5 on which "
                                             "the smoothing started over"]))

    def test_the_effects_counters(self):
        # 120 draws moved: 100 of them 0.6 units from the body without the move (class 6), 20 of them 5 (class 9);
        # 0.0001 after (class 0); kinds 2 and 13
        counters = {0: 120, 4: 25.0, 8: 1e-8, 12: 0, 16 + 4 * 6: 100, 16 + 4 * 9: 20, 80: 120, 144 + 4 * 2: 90,
                    144 + 4 * 13: 30}
        status, out = self.read(50, lambda k: (k, 1, 3, 0.5, 0.0), counters)
        self.assertEqual(status, 0, out)
        self.assertEqual(out[5:], ["a rival's effects drawn while it had an offset: 120 draws moved with its body, 0 "
                                   "left where the game draws them",
                                   "an effect to its drawn body without the move (the offset), in units: 0.5 to 1: 100, "
                                   "4 to 8: 20; largest 5.00",
                                   "an effect to its drawn body as drawn, in units: 0 to 0.015625: 120; largest 0.0001",
                                   "draws by kind: 2: 90, 13: 30"])
        # the tests' bit: the effects left; the first line says so
        status, out = self.read(10, lambda k: (k, 1, 3 | 32, 0.5, 0.0), {12: 7, 16 + 4 * 9: 7, 80 + 4 * 9: 7})
        self.assertIn("the effects left where the game draws them", out[0])
        self.assertIn("0 draws moved with its body, 7 left where the game draws them", out[5])


if __name__ == "__main__":
    unittest.main()
