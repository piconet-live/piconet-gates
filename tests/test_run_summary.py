"""Tests for run-summary.py's time per field while racing, on made-up probe rows (no work folder, no harness)."""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("run_summary", os.path.join(HERE, "..", "reports", "run-summary.py"))
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

FIELD_US = 16_683


def rows(fields):
    """Probe rows from (mode, race frame, the field's time in us)."""
    out, clock = [], 1000
    for mode, frame, took in fields:
        clock += took
        out.append({"mode": mode, "race_frame": str(frame), "qpc_us": str(clock)})
    return out


def run(stall_at=None, stall_us=300_000, catch_up=10):
    """Menus to field 99, then a race from field 100 (race frame 1) for 900 fields. stall_at: the race frame stands
    for one long field there (a screenshot), and the emulator catches up with short fields afterwards."""
    fields = [("1", 0, FIELD_US)] * 100
    frame, k = 0, 0
    while k < 900:
        if stall_at is not None and 100 + k == stall_at:
            fields.append(("2", frame, stall_us))                      # the picture: no step, a quarter of a second
            fields += [("2", frame + n, 5_500) for n in range(1, catch_up + 1)]
            frame, k = frame + catch_up, k + 1 + catch_up
            continue
        frame, k = frame + 1, k + 1
        fields.append(("2", frame, FIELD_US))
    return rows(fields)


class TheRacesPace(unittest.TestCase):
    def test_a_steady_race_reads_its_pace_with_and_without_a_limit(self):
        racing, times = rs.race_fields(run())
        self.assertEqual((racing[0], len(racing)), (100, 900))
        self.assertAlmostEqual(sum(times) / len(times), 16.683, places=3)
        racing, times = rs.race_fields(run(), before=700)
        self.assertEqual((racing[0], racing[-1], len(racing)), (100, 699, 600))
        self.assertIn("race: 600 fields from field 100, race frame up to 600; per field mean 16.683 ms, max 16.7 ms, "
                      "over 24 ms: 0; measured before field 700", rs.race_line(run(), before=700))
        self.assertNotIn("measured before", rs.race_line(run()))

    def test_a_pictures_stall_inside_the_span_pulls_the_mean_down_and_after_it_does_not(self):
        # the offline row of 2026-10-07: the picture asked for inside the measured span
        stalled = run(stall_at=230)
        racing, times = rs.race_fields(stalled)
        self.assertNotIn(230, racing)                                  # the race frame stood: the long field is not counted
        self.assertLess(sum(times) / len(times), 16.6)                 # and the ten short fields after it are
        # the same run measured before the field the picture is asked at: the game's own pace
        racing, times = rs.race_fields(stalled, before=230)
        self.assertEqual(len(racing), 130)
        self.assertAlmostEqual(sum(times) / len(times), 16.683, places=3)
        late = run(stall_at=760)                                       # the picture after the span
        racing, times = rs.race_fields(late, before=700)
        self.assertEqual(len(racing), 600)
        self.assertAlmostEqual(sum(times) / len(times), 16.683, places=3)

    def test_a_field_on_which_the_race_frame_stood_is_counted_and_the_longest_named(self):
        # the run of 2026-10-07 read "max 23.4 ms, over 24 ms: 0" with a field of 300 ms in its span
        line = rs.race_line(run(stall_at=230))
        self.assertIn("; not counted: 1 fields on which the race frame did not go up by one, the longest 300.0 ms at field 230", line)
        self.assertIn("max 16.7 ms, over 24 ms: 0", line)              # of the race's own fields, as before
        self.assertNotIn("not counted", rs.race_line(run()))
        self.assertNotIn("not counted", rs.race_line(run(stall_at=760), before=700))
        two = run(stall_at=230)
        two.insert(400, dict(two[399], qpc_us=str(int(two[399]["qpc_us"]) + 40_000)))   # the race frame stands once more
        for row in two[401:]:
            row["qpc_us"] = str(int(row["qpc_us"]) + 40_000)
        self.assertIn("not counted: 2 fields on which the race frame did not go up by one, the longest 300.0 ms at field 230",
                      rs.race_line(two))

    def test_a_slow_game_is_still_slow_before_the_limit(self):
        slow = rows([("1", 0, FIELD_US)] * 100 + [("2", n, 17_500) for n in range(1, 901)])
        racing, times = rs.race_fields(slow, before=700)
        self.assertGreater(sum(times) / len(times), 16.8)

    def test_a_run_with_no_race_has_no_line(self):
        self.assertIsNone(rs.race_line(rows([("1", 0, FIELD_US)] * 50)))
        self.assertIsNone(rs.race_line(run(), before=100))


if __name__ == "__main__":
    unittest.main()
