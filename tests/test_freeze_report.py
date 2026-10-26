"""Tests for reports/freeze-report.py on made-up logs (no work folder, no game): what it reads of a log's freezes,
its stop line and its summary line, what the judge of freeze-run.sh passes and fails, and how a linker's map names
a call stack's places."""

import importlib.util
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("freeze_report", os.path.join(HERE, "..", "reports", "freeze-report.py"))
fr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fr)

REPORT = """warning: fzgx: freeze: no game frame for {seconds} s (report {n} of this freeze; game frame 825, race step {step}; in the race; the core is not waiting for the relay)
warning: fzgx: freeze: emulated CPU, 8 samples 10 ms apart (as last stored: native code keeps them only at its exits): pc 81860000 lr 81800BD0 (a host call) x8
warning: fzgx: freeze: in those 70 ms: emulated time advanced 0 ticks, 0 network hook calls, 0 data window accesses; msr 0000B03A (interrupts on), pending exceptions 00000004, interrupt cause 00010008 mask 00000FFC (0400: draw done, 0200: token, 0800: command list, 0100: video)
warning: fzgx: freeze: the game's thread, host code, 8 samples: ntdll.dll+162244 x8
warning: fzgx: freeze: the game's thread, call stack (innermost first): ntdll.dll+162244 < runner.exe+1234 < runner.exe+2010
warning: fzgx: freeze: the picture's thread, call stack (innermost first): runner.exe+3000
warning: fzgx: freeze: command list: write 0155D6E0 read 0155D6E0 (safe 0155D6E0) distance 0, base 0155B000 end 0161AFE0, breakpoint 00000000; read enable 1, link 0, breakpoint enable 0, at breakpoint no; high watermark 0, low 1; a command processor interrupt does not wait; picture on its own thread yes, deterministic no, sync no; emulator running
"""
STOP = ("fzgx: stop: the game's window was asked to close: a close message from outside the window (another program, the "
        "launcher); the game stood still when it was asked (for 4.7 s by then)\n")
DOWN = "fzgx: stop: the emulator has shut down, 25.4 s after the stop was asked for\n"
SUMMARY = ("1 2026-10-13T11:57:32Z match=m3 course=16 racers=30 players=1 seat=0 delay=2 present=console end=closed "
           "steps=1500 freezes={freezes} stood={stood} stuck={stuck} waits={waits} | countdown s=7.6 frames=364 | race s=48.5 | after s=0.0")


DUMP = "warning: fzgx: stop: the emulator has not shut down 5 s after the stop was asked for; where its threads are:\n" + \
    "".join(REPORT.format(seconds="0", n=1, step=0).splitlines(keepends=True)[1:])
WAIT = ("warning: fzgx: wait: no game frame for 2.0 s: the core waits for the relay's inputs (report 1 of this wait; game "
        "frame 2263, race step 1703; it gives up after 15 s)\n")


def log(first_moves=True, second_reports=2, stop=STOP, freezes=2, stood="4.9", stuck="yes", waits=0, first_step=1000,
        dump=DUMP, wait=""):
    """The log freeze-run.sh's game leaves, or one that differs from it in the named way."""
    text = "fzgx: go (this game's system time at boot: 0)\n" + REPORT.format(seconds="2.0", n=1, step=first_step)
    if first_moves:
        text += "warning: fzgx: freeze: the game moves again; it stood for 2.8 s (1 report)\n"
    for n in range(1, second_reports + 1):
        text += REPORT.format(seconds=f"{2.05 * n:.1f}", n=n, step=1500)
    return (text + wait + stop + dump + DOWN + "fzgx: race summary: " +
            SUMMARY.format(freezes=freezes, stood=stood, stuck=stuck, waits=waits) + "\n")


def file(freezes=2, stuck="yes"):
    return "an older line without the words\n" + SUMMARY.format(freezes=freezes, stood="4.9", stuck=stuck, waits=0) + "\n"


class FreezeReport(unittest.TestCase):
    def test_a_log_is_read_as_its_freezes_its_stop_and_its_summary(self):
        freezes, waits, stop, summary = fr.read(log())
        self.assertEqual([[r["seconds"] for r in f["reports"]] for f in freezes], [[2.0], [2.0, 4.1]])
        self.assertEqual([f["moved"] for f in freezes], [2.8, None])
        self.assertEqual([f["step"] for f in freezes], [1000, 1500])
        self.assertTrue(all(r["parts"] == set(fr.PARTS) for f in freezes for r in f["reports"]))
        self.assertEqual(waits, [])
        self.assertTrue(stop.startswith("the game's window was asked to close"))
        self.assertEqual((summary["freezes"], summary["stood"], summary["stuck"], summary["end"], summary["waits"]),
                         ("2", "4.9", "yes", "closed", "0"))
        # a log with none of it: no freeze, no wait, no stop, no summary
        self.assertEqual(fr.read("fzgx: go\nfzgx: step 599, official 598\n"), ([], [], None, None))

    def test_a_wait_and_a_race_that_ends_are_read_as_what_they_are(self):
        text = (REPORT.format(seconds="2.0", n=1, step=1500) +
                "warning: fzgx: freeze: the race is over for this game (lost, or its recording ended); it had stood for 4.5 s (1 report)\n" +
                WAIT + WAIT.replace("2.0 s", "4.1 s").replace("report 1", "report 2") +
                "warning: fzgx: wait: the race is over for this game (lost, or its recording ended); it had waited for 15.1 s (2 reports)\n")
        freezes, waits, _, _ = fr.read(text)
        self.assertEqual((freezes[0]["moved"], freezes[0]["left"]), (4.5, True))
        self.assertEqual(waits, [dict(reports=[2.0, 4.1], ended=15.1, step=1703)])

    def test_the_run_of_the_test_passes_and_each_thing_it_lacks_fails(self):
        self.assertIsNone(fr.judge(log(), file()))
        self.assertIsNone(fr.judge(log(dump=""), file()))
        self.assertIn("not the two", fr.judge(log(second_reports=0), file()))
        self.assertIn("in the countdown", fr.judge(log(first_step=150), file()))
        self.assertIn("first stand", fr.judge(log(first_moves=False), file()))
        self.assertIn("second stand", fr.judge(log(second_reports=1), file()))
        self.assertIn("freeze 1's report 1 lacks: command list",
                      fr.judge(log().replace("fzgx: freeze: command list: ", "fzgx: freeze: nothing: ", 1), file()))
        # the second report without its lines: the dump a slow shutdown gets, after the stop line, does not stand
        # in for them (it did: its lines were counted for the freeze before it)
        cut = log()
        at = cut.index("report 2 of this freeze")
        end = cut.index("fzgx: stop: the game's window")
        cut = cut[:cut.index("\n", at) + 1] + cut[end:]
        self.assertIn("freeze 2's report 2 lacks", fr.judge(cut, file()))
        self.assertIn("a wait for the relay", fr.judge(log(wait=WAIT), file()))
        self.assertIn("does not name the close", fr.judge(log(stop="fzgx: stop: Escape was pressed in the game's window\n"), file()))
        self.assertIn("stood still", fr.judge(log(stop=STOP.replace("; the game stood still when it was asked (for 4.7 s by then)", "")), file()))
        self.assertIn("not the length", fr.judge(log(stop=STOP.replace("4.7 s by then", "30.1 s by then")), file()))
        self.assertIn("shut down", fr.judge(log().replace(DOWN, ""), file()))
        self.assertIn("no summary", fr.judge(log().replace("fzgx: race summary: ", "fzgx: summary: "), file()))
        self.assertIn("stuck=no", fr.judge(log(stuck="no"), file()))
        self.assertIn("freezes=1", fr.judge(log(freezes=1), file()))
        self.assertIn("waits=1", fr.judge(log(waits=1), file()))
        self.assertIn("shorter", fr.judge(log(stood="1.0"), file()))
        self.assertIn("race-summary.txt", fr.judge(log(), file(stuck="no")))
        self.assertIn("race-summary.txt", fr.judge(log(), ""))

    def test_a_map_names_the_places_of_a_stack(self):
        text = """ Preferred load address is 0000000140000000

  Address         Publics by Value              Rva+Base               Lib:Object

 0000:00000000       __guard_flags              0000000000000100     <absolute>
 0001:00000000       ?StandStill@net@fzgx@@YAXAEAUSession@12@I@Z 0000000140001000 f   core:freeze.cpp.obj
 0001:00001000       ?NormalStep@net@fzgx@@YAXAEAVGuest@2@AEAUSession@12@@Z 0000000140002000 f   core:frame.cpp.obj
 0001:00002000       ??R<lambda_1>@?1??RunGpuLoop@FifoManager@Fifo@@QEAAXXZ@QEBA@XZ 0000000140003000 f   video:Fifo.cpp.obj
"""
        maps = {"runner.exe": fr.read_map(text)}
        self.assertEqual(maps["runner.exe"][0], [0x1000, 0x2000, 0x3000])
        line = "call stack: ntdll.dll+162244 < runner.exe+1234 < runner.exe+2010 < runner.exe+3000 < runner.exe+10"
        self.assertEqual(fr.named(line, maps),
                         "call stack: ntdll.dll+162244 < runner.exe+1234 [fzgx::net::StandStill+234] < runner.exe+2010 "
                         "[fzgx::net::NormalStep+10] < runner.exe+3000 [??R<lambda_1>@?1??RunGpuLoop@FifoManager@Fifo@@QEAAXXZ@QEBA@XZ+0] "
                         "< runner.exe+10")


if __name__ == "__main__":
    unittest.main()
