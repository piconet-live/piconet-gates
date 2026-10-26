"""logs.py: the two logs of a test game that the reports and the judges read, read one way here.

  pace.csv  the runner's pacing log (the launch file's "debug.paceLog"; the runtime's FzgxProbe, StartPaceLog).
            Comment lines "# ..." (its start, the columns of each record, the graphics backend), then records: a
            kind letter, a comma, the columns of LAYOUT, all times in microseconds of one clock.
  rb.csv    the core's rollback log ("debug.rollbackLog"): a CSV with a header line, a row for every displayed frame
            of the race phase (at_us, step, depth, forced, catch_up, ... as its header names them).

The pacing log's records, as the log's own header lines name their columns (a record's place K is LAYOUT[kind][K - 1];
column(kind, name) gives the place). WHOLE: the fewest places of a record of each kind the readers take as whole;
one cut short at the file's end has fewer and is left out (pacing()). records() is the plain split, for a reader
that judges a record's length itself (judge_game.py's spin takes the 23 places of an older log's F records)."""
import collections
import csv
import os

LAYOUT = {
    "F": ("end_us", "field", "cpu_thread_cycles", "mode", "submode", "race_frame", "racer0_flags", "racer0_energy",
          "pad1_buttons", "stick_x", "stick_y", "c_x", "c_y", "trigger_l", "trigger_r", "pad1_reads", "fallback_steps",
          "interpreted", "chunk_checks", "chunks_failing", "run_loop_trips", "idles", "fallback_jit_cycles",
          "fallback PCs", "interpreted PCs", "checked chunks"),   # a field ended (the CPU thread)
    "P": ("before_wait_us", "after_wait_us", "after_present_us", "thread_cycles_since_last_present", "thread_id",
          "draws", "primitives", "vertex_bytes", "uniform_bytes", "textures_created", "textures_uploaded",
          "textures_alive"),   # a picture was presented (the video thread)
    "T": ("start_us", "duration_us", "what", "thread_id"),   # a stretch of graphics work of 2 ms or more
    "X": ("time_us", "duration_us", "what", "width", "height", "layers", "levels", "format", "samples", "during",
          "address"),   # a texture made or given up by the backend
    "N": ("time_us", "cache_entries", "pooled_textures", "invalidated_this_frame"),   # the texture cache at a frame's end
    "E": ("start_us", "duration_us", "to_texture", "to_memory", "xfb", "depth", "width", "height", "format",
          "address"),   # a copy out of the frame buffer
    "S": ("start_us", "duration_us", "what", "thread_id"),   # a shader or pipeline built
    "R": ("time_us", "port", "strength"),   # a rumble command (port 0: port 1)
    "C": ("time_us", "time_stamp_counter"),   # the clock's calibration: the C records give the cycles' rate
}
WHOLE = dict(F=26, P=6, S=5, T=5, E=11, X=10, N=5, R=4, C=3)
RATE = 3394.0   # cycles a microsecond, when a log has fewer than two C records


def column(kind, name):
    """The place of a column in a split record of that kind (the kind letter is place 0)."""
    return LAYOUT[kind].index(name) + 1


def _lines(source):
    if isinstance(source, str):
        if not os.path.exists(source):
            return
        with open(source, encoding="utf-8", errors="replace") as f:
            yield from f
    else:
        yield from source


def records(source):
    """Every record of a pacing log (a path, or its lines), split at its commas, its line end stripped: place 0 is
    the kind letter. Nothing for a file that is not there."""
    for line in _lines(source):
        if line[1:2] == "," and line[:1] in LAYOUT:
            yield line.rstrip("\r\n").split(",")


class Pacing:
    """A pacing log's whole records by kind (self[kind]: a list of split records, in the file's order) and its comment
    lines without their "# " (notes). An empty one for a file that is not there."""

    def __init__(self, source):
        self.notes, self.records = [], collections.defaultdict(list)
        for line in _lines(source):
            if line.startswith("# "):
                self.notes.append(line.rstrip("\r\n")[2:])
            elif line[1:2] == "," and line[:1] in LAYOUT:
                row = line.rstrip("\r\n").split(",")
                if len(row) >= WHOLE[row[0]]:
                    self.records[row[0]].append(row)

    def __getitem__(self, kind):
        return self.records[kind]

    def rate(self, default=RATE):
        """The time stamp counter's cycles a microsecond, from the first and the last C record."""
        c = self.records["C"]
        return (int(c[-1][2]) - int(c[0][2])) / (int(c[-1][1]) - int(c[0][1])) if len(c) > 1 else default


def pacing(source):
    return Pacing(source)


def rollback_log(path):
    """The rollback log's rows as dicts by its header's names; [] when the file is not there. A row cut short at the
    file's end (fewer cells than names) is left out."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f)
        names = next(reader, [])
        return [dict(zip(names, row)) for row in reader if names and len(row) >= len(names)]
