"""The spectator log's reader (port/gates/reports/spectator-log.py) on made-up files: a data window with a few log
entries and a rollback log. No game data."""
import os, subprocess, sys, tempfile, unittest

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(here, "..", "..", "facts", "generated"))
import facts

SCRIPT = os.path.join(here, "..", "reports", "spectator-log.py")
HEAD = "at_us,step,depth,forced,catch_up,extra,ahead,track_us,restore_us,blocks,hook_us,first_us,resim_us,resim_n,sched,owed,held"


def window(entries, place=None):
    """A data window holding `entries` (step, racer, mode, camera mode, height, a, b, c) from the log's start."""
    win = bytearray(facts.WINDOW_END - facts.WINDOW)
    for i, (step, racer, mode, camera, height, a, b, c) in enumerate(entries):
        at = facts.SPEC_LOG - facts.WINDOW + 8 * i
        win[at:at + 8] = step.to_bytes(2, "big") + bytes([racer, mode << 4 | camera, height, a, b, c])
    at = facts.SPEC_LOGGED - facts.WINDOW
    win[at:at + 4] = (len(entries) if place is None else place).to_bytes(4, "big")
    return bytes(win)


class TheSpectatorLog(unittest.TestCase):
    def read(self, entries, depths, *options, place=None):
        with tempfile.TemporaryDirectory() as folder:
            dump, log = os.path.join(folder, "d.win"), os.path.join(folder, "rb.csv")
            with open(dump, "wb") as f:
                f.write(window(entries, place))
            with open(log, "w") as f:   # a frame's line holds its first step; the log's entry the step after its steps
                steps = [entries[0][0] - 1] + [e[0] for e in entries] if entries else []
                f.write(HEAD + "\n" + "".join(f"0,{s},{d},0,0,0,0,0,0,0,0,0,0,0,0,0,0\n" for s, d in zip(steps, depths + [0])))
            done = subprocess.run([sys.executable, SCRIPT, dump, log, *options], capture_output=True, text=True)
            return done.returncode, done.stdout.strip().split("\n")

    def test_choices_the_cameras_hold(self):
        entries = [(100, 3, 0, 9, 0, 3, 2, 9), (101, 3, 0, 9, 0, 3, 2, 9), (102, 4, 0, 9, 0, 4, 2, 9), (103, 4, 0, 9, 0, 4, 1, 5),
                   (104, 4, 3, 9, 7, 4, 1, 7), (105, 4, 6, 0, 2, 4, 3, 0)]
        status, out = self.read(entries, [0, 0, 5, 0, 0, 2])
        self.assertEqual(status, 0, out)
        self.assertIn("6 frames logged, steps 100 to 105; 3 changes of choice", out[-1])
        self.assertIn("frames with a rollback 2 (deepest 5), changes on one 2", out[-1])
        self.assertIn("frames settling after a change: 0; frames where the cameras did not hold the choice: 0; frames "
                      "where they followed a racer who is out: 0", out[-1])
        self.assertIn("frame     2 step   102 depth  5 | chosen: racer  4 mode 0 height  0 | game: camera mode 9,   4   2   9", out)
        self.assertEqual(len(self.read(entries, [0] * 6, "--all")[1]), 7)

    def test_a_choice_takes_a_few_frames_to_show(self):
        # a manual shot: the type in the step of the choice with variant 1, the height a step later; a type the
        # game picks instead is the mode a frame later. Neither is a fault; the same for longer is
        steady = [(100 + i, 3, 2, 9, 0, 3, 0, 0) for i in range(6)]
        choice = [(106, 3, 3, 9, 5, 3, 1, 1), (107, 3, 3, 9, 5, 3, 1, 5), (108, 3, 3, 9, 5, 3, 1, 5)]
        picked = [(109, 3, 3, 9, 5, 3, 3, 1), (110, 3, 5, 9, 1, 3, 3, 1), (111, 3, 5, 9, 1, 3, 3, 1)]
        status, out = self.read(steady + choice + picked, [0] * 12)
        self.assertEqual(status, 0, out)
        self.assertIn("frames settling after a change: 2; frames where the cameras did not hold the choice: 0", out[-1])
        self.assertIn("(settling)", "\n".join(out))
        late = [(106 + i, 3, 3, 9, 5, 3, 1, 1) for i in range(6)]    # the height never comes
        status, out = self.read(steady + late, [0] * 12)
        self.assertEqual(status, 1)
        self.assertIn("frames settling after a change: 3; frames where the cameras did not hold the choice: 3", out[-1])

    def test_a_choice_the_cameras_lost_fails(self):
        tv, shot, chase = (3, 0, 9, 0, 3, 2, 9), (3, 2, 9, 4, 3, 0, 4), (3, 6, 0, 1, 3, 2, 0)
        for good, lost in ((tv, (3, 0, 9, 0, 2, 2, 9)),              # the TV cameras follow another racer
                           (shot, (3, 2, 9, 4, 3, 0, 3)),            # a manual shot's variant
                           (shot, (3, 2, 9, 4, 2, 0, 4)),            # its racer
                           (chase, (3, 6, 0, 1, 3, 1, 0)),           # the chase camera's view
                           (chase, (3, 6, 0, 1, 5, 2, 0))):          # the chase camera's racer
            entries = [(100 + i,) + good for i in range(8)] + [(108,) + lost] + [(109 + i,) + good for i in range(4)]
            status, out = self.read(entries, [0] * len(entries))
            self.assertEqual(status, 1, lost)
            self.assertIn("NOT HELD", "\n".join(out))
            self.assertIn("did not hold the choice: 1", out[-1])
        # a type that is not the mode's, for good
        entries = [(100 + i,) + shot for i in range(8)] + [(108 + i, 3, 2, 9, 4, 3, 1, 4) for i in range(8)]
        status, out = self.read(entries, [0] * len(entries))
        self.assertEqual(status, 1)
        self.assertIn("did not hold the choice: 5", out[-1])

    def test_a_frame_that_follows_a_racer_who_is_out_fails(self):
        # the height's byte carries the bit; the height itself is read without it
        good = (3, 2, 9, 4, 3, 0, 4)
        entries = [(100 + i,) + good for i in range(6)] + [(106, 3, 2, 9, 4 | 0x80, 3, 0, 4)] + [(107,) + good]
        status, out = self.read(entries, [0] * len(entries))
        self.assertEqual(status, 1)
        self.assertIn("height  4 | game: camera mode 9,   3   0   4   <-- FOLLOWS A RACER WHO IS OUT", "\n".join(out))
        self.assertIn("did not hold the choice: 0; frames where they followed a racer who is out: 1", out[-1])

    def test_the_racer_asked_for_out_and_the_cameras_on_another(self):
        # the second bit: the choice (racer 3) is out, the cameras are on racer 5, which is no fault
        good, moved = (3, 0, 9, 0, 3, 2, 9), (3, 0, 9, 0x40, 5, 2, 9)
        entries = [(100 + i,) + good for i in range(6)] + [(106 + i,) + moved for i in range(6)]
        status, out = self.read(entries, [0] * len(entries))
        self.assertEqual(status, 0, out)
        self.assertIn("(the racer asked for is out)", "\n".join(out))
        self.assertIn("frames with the racer asked for out and the cameras on another: 6", out[-1])

    def test_a_log_that_went_round_is_read_from_its_oldest_entry(self):
        entries = [(200 + i, 1, 0, 9, 0, 1, 0, 0) for i in range(facts.SPEC_LOG_ENTRIES)]
        entries[0], entries[1] = (5832, 1, 0, 9, 0, 1, 0, 0), (5833, 1, 0, 9, 0, 1, 0, 0)     # the two newest
        status, out = self.read(entries, [0] * len(entries), place=2)
        self.assertEqual(status, 0)
        self.assertIn(f"{facts.SPEC_LOG_ENTRIES} frames logged, steps 202 to 5833", out[-1])

    def test_a_game_that_never_spectated(self):
        self.assertEqual(self.read([], []), (1, ["the log is empty: this game never spectated"]))


if __name__ == "__main__":
    unittest.main()
