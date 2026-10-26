"""Tests for latency-report.py on made-up logs (no work folder, no game): a race whose pad to picture is known by
construction must be read as that, for each input delay; a present made early must read as early; offline play must
say that it follows no press."""

import contextlib
import importlib.util
import io
import json
import os
import struct
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("latency_report", os.path.join(HERE, "..", "reports", "latency-report.py"))
lr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lr)

FIELD = 16_683          # a field, in microseconds
FIRST_FIELD = 100       # the race's step 0 runs in the pass after this field's end
HOOK = 600              # the hook's clock read, this long after the field's start
COPY = 70               # the game's copy, this long after the field's start


def made_up_run(folder, delay, present_after, presses, fields=400, race=True, log=""):
    """A run's folder: `fields` fields from time 1,000,000 on, the pad's buttons changing at the fields in `presses`
    (field: buttons), a picture copied COPY after every field's start and presented `present_after` after it. With
    `race`: the frame in the pass after field f runs step f - FIRST_FIELD, the seat's record for step s is the pad
    of field s + FIRST_FIELD - delay (the pad the frame that ran step s - delay read), and the rollback log has a
    line a frame."""
    t0, pad, pads, lines = 1_000_000, "0000", {}, ["# pacing log; made up"]
    for f in range(fields):
        pad = presses.get(f, pad)
        pads[f] = pad
        end = t0 + (f + 1) * FIELD   # field f ends here; the pass in field f + 1 follows
        lines.append(f"F,{end},{f},20000000,2,36,{max(0, f - FIRST_FIELD)},84000400,42c80000,{pad},128,128,128,128,0,0,2,0,36,0,1,2700,554,80000,,,")
        lines.append(f"E,{end + COPY},50,1,0,1,0,640,448,15,016db000")
        lines.append(f"P,{end + present_after},{end + present_after},{end + present_after + 30},15000000,432,700,40000,1,2,0,0,263")
        lines.append(f"C,{end},{end * 3394}")
    with open(os.path.join(folder, "pace.csv"), "w") as out:
        out.write("\n".join(lines) + "\n")
    with open(os.path.join(folder, "fzgx.log"), "w") as out:
        out.write(log)
    if not race:
        return
    steps = fields - FIRST_FIELD - 2
    with open(os.path.join(folder, "rb.csv"), "w") as out:
        out.write("at_us,step,depth,forced,catch_up,extra,ahead,track_us,restore_us,blocks,hook_us,first_us,resim_us,resim_n,sched,owed,held\n")
        for s in range(steps):
            at = t0 + (s + FIRST_FIELD + 1) * FIELD + HOOK   # in the pass after field s + FIRST_FIELD
            out.write(f"{at},{s},0,0,0,0,0,400.0,0.0,100,500.0,1900.0,0.0,0,-0.50,0.00,0\n")
    header = json.dumps({"seat": 1, "delay": delay, "engine": "native", "module_sha1": "m" * 40, "mod_sha1": "i" * 40}).encode()
    body = b""
    for s in range(steps):
        read = pads.get(s + FIRST_FIELD - delay, "0000")
        mine = bytes.fromhex(read) + b"\x80\x80\x00\x00"
        body += b"\x00" * 6 + mine + struct.pack(">I", s)   # seats 0 and 1, then the step's checksum
    with open(os.path.join(folder, "race.fzrp"), "wb") as out:
        out.write(b"FZRP" + struct.pack(">HI", 2, len(header)) + header + b"FZRF" + struct.pack(">II", 3, 1) + body)


def report(folder):
    said = io.StringIO()
    with contextlib.redirect_stdout(said):
        lr.report(folder, 20)
    return said.getvalue()


PRESSES = {f: ("0100" if k % 2 == 0 else "0000") for k, f in enumerate(range(160, 360, 10))}


class PadToPicture(unittest.TestCase):
    def test_each_delay_reads_as_its_fields_and_its_milliseconds(self):
        for delay in (0, 1, 2):
            with tempfile.TemporaryDirectory() as folder:
                made_up_run(folder, delay, 4_500, PRESSES)
                said = report(folder)
                # stamped by the pass after the pad's field; shown one field for the pass, the delay's, one for the copy
                self.assertIn(f"input delay {delay} (its header)", said)
                self.assertIn(f"presses followed: {len(PRESSES)} of {len(PRESSES)} changes", said)
                self.assertIn(f"in fields: {{1: {len(PRESSES)}}}", said)
                self.assertIn(f"shown in, in fields: {{{delay + 2}: {len(PRESSES)}}}", said)
                want = ((delay + 1) * FIELD + 4_500) / 1000
                self.assertIn(f"PAD TO PICTURE (the pad's sample to the present call), ms: median {want:.2f}, least {want:.2f}", said)
                self.assertIn("presentation field", said)

    def test_a_present_at_the_copy_reads_as_that_much_sooner(self):
        with tempfile.TemporaryDirectory() as folder:
            made_up_run(folder, 2, COPY + 40, PRESSES, log="warning: fzgx: TEST SETTING: presentation is \"copy\" (the launch file's \"present\")\n")
            said = report(folder)
            self.assertIn("presentation copy", said)
            self.assertIn(f"PAD TO PICTURE (the pad's sample to the present call), ms: median {(3 * FIELD + COPY + 40) / 1000:.2f}", said)
            self.assertIn("a picture is shown this long after its field began, ms: median 0.11", said)
            self.assertIn("intervals off 16.68 ms by more than 1 / 2 / 4 ms: 0 / 0 / 0", said)

    def test_offline_play_follows_no_press_and_says_so(self):
        with tempfile.TemporaryDirectory() as folder:
            made_up_run(folder, 0, 4_000, PRESSES, race=False)
            said = report(folder)
            self.assertIn("no race (offline play)", said)
            self.assertIn("presses followed: none", said)
            self.assertNotIn("PAD TO PICTURE", said)
            self.assertIn("a picture is shown this long after its field began, ms: median 4.00", said)


if __name__ == "__main__":
    unittest.main()
