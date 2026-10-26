#!/usr/bin/env python3
"""map-report.py RUN [options]: where a frame's time goes in one measuring run of the whole-frame map
(runs/map-run.sh; the speed handbook, section 4).

Reads <work>/port/runs/RUN: samples.txt (the external sampler, port/speed/map-sample.cs), pace.csv (the runner's pacing
log), rb.csv (the core's rollback log). The scene is the race phase: the fields in which the game's mode is 2 and
the race frame counter lies between --from and --to (default: from race frame 600, ten seconds into the race). A
sample belongs to the scene when its time lies in such a field.

The CPU thread (the game thread). Every sample is first "on the processor" or "blocked" (the thread stands in a
system call that waits). On-processor samples are shared out twice:
  by host place: generated code (the module), the run loop, the hooks out of generated code, the emulator's
    scheduled events, the online layer's own code by its source file (undo log, restore, checksum, replay and live
    feed, relay), the probe and the pacing log, the throttle;
  by guest place, from the guest stack read with the sample: the task the task runner was in (under the online
    layer's frame routine: a step; under the game's own call: presentation), the main loop's callees, interrupt
    handlers, other guest threads.
A share times the field's wall time is milliseconds a field. The check every table carries: on-processor samples
over all samples, times the field's wall time, against the thread's cycle counter in the pacing log.

  --from N --to N     race frames of the scene          --top N    rows per table (default 40)
  --exe-map FILE      the runner's link map (it belongs to one runner build)
  --module-map FILE   the module's link map, if one was made (without it generated code is not split by function)
  --functions FILE    the module's generated.h: the guest functions' starts when there is no module map
  --symbols FILE      the bundle's symbols.json (the image's routines by name)
  --tags FILE         map-guest-tags.py's output (which functions of the executable touch which hardware)
  --video, --others   the video thread's tables; every other thread     --detail   the functions inside a place
Reads files only."""
import argparse
import collections
import json
import os
import re
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "setup"))
import work_folder  # noqa: E402
from map_lib import REL, TASK_RETURN, TEXT, Run, Symbols  # noqa: E402

BLOCKING = re.compile(r"^(Nt|Zw)(WaitFor|DelayExecution|RemoveIoCompletion|SignalAndWait|UserMsgWait|UserGetMessage|UserWaitMessage|WaitHighEventPair|"
                      r"ReplyWaitReceive|AlpcSendWaitReceive|DeviceIoControlFile$)")
GENERIC = re.compile(r"^(mem(cpy|set|move|cmp|chr)|_?XXH|__chkstk|_guard|__security|\?\?[23]@|malloc|free|_free|_malloc|realloc|calloc|_Mtx|_Cnd|"
                     r"_Thrd|__std_|strlen|wcslen|_RTC|_Query_perf|\?Get[A-Za-z]+@System@Core|\?\??\$?_[A-Z][A-Za-z_]*@|\?now@|"
                     r"\?(lock|unlock|try_lock|allocate|deallocate)@|\?\?[0-9A-Z_]\?\$(shared_ptr|unique_ptr|vector|basic_string|function|_Func))")
THROTTLE = "the throttle: waiting for real time on the processor (CoreTiming::Throttle)"
MAIN_LOOP = TEXT                       # fn_1_0, main.rel's main loop
FRAME = TEXT + 0xECC                   # fn_1_ECC, the frame's update (the image's frame routine and the task runner are under it)
IRQ = 0x8000D9CC                       # the SDK's interrupt dispatcher: the handler is its callee
THREAD_START = 0x80010A10              # every guest thread but the main one starts under it
IDLE_ENTRY = 0x8004E7D4                # the thread the game is in while it waits for the next field
PHYSICS = ("fn_1_83858", "fn_1_850C4", "fn_1_C4ABC")
STEPS = "the online layer's steps (image:frame_routine)"
WAITERS = [("Throttle@CoreTimingManager", "the throttle: asleep until real time catches up"),
           ("Wait@BlockingLoop", "waiting for the video thread (CoreTiming::Idle -> BlockingLoop::Wait)"),
           ("UndoLog", "the undo log: waiting for its worker threads"), ("PreStep@", "the undo log: waiting for its worker threads"),
           ("Send@Udp", "the relay's socket: send"), ("Receive@Udp", "the relay's socket: receive")]
VIDEO_GROUPS = [
    ("present and frame end (presenter, swap chain, frame-buffer copy to the screen)", r"Presenter|SwapChain|Present|ShowImage|RenderXFB|OnScreenUI|ImGui_Impl|EndFrame|BeginFrame"),
    ("texture cache (lookups, hashing, decoding, copies out of the frame buffer)", r"TextureCache|TextureInfo|TCacheEntry|GetHash64|TMEM@|TextureDecoder|TexDecoder|CopyRenderTargetToTexture|CopyEFB|EFBToTexture|CreateTexture"),
    ("state and pipeline lookups (shader identities, pipeline cache, constants)", r"ShaderUid|ShaderCache|GXPipelineUid|UpdatePipelineConfig|PipelineUid|ShaderManager@|SetConstants|GetSampler|ObjectCache|ShaderGen"),
    ("vertex loading (loaders, index generation, the loaders' own generated code)", r"VertexLoader|RunVertices|IndexGenerator|AddStrip|AddList|AddFan|AddQuads|AddLine|AddPoints|PrepareForAdditionalData|CalculateZSlope|TransformToClipSpace|NativeVertexFormat|CullTest|AddIndices"),
    ("backend submission (Vulkan state, descriptor sets, stream buffers, draw calls; the driver under them)", r"Vulkan@|vma[A-Z]|Vma|VKGfx|StateTracker|StreamBuffer|CommandBufferManager|UploadUniforms|CommitBuffer|DrawIndexed|ResetBuffer"),
    ("the draw flush itself (VertexManagerBase::Flush and its helpers)", r"VertexManagerBase|VertexManager@"),
    ("the FIFO loop's own bookkeeping, once for every 32 bytes (read pointer, distance, SetCPStatusFromGPU, PullEvents)", r"RunGpuLoop|SetCPStatusFromGPU|PullEvents@AsyncRequests|BlockingLoop|GetCommandProcessor@System|GetInstance@System|RefreshPeekCache|GetFifo@System|GetVideoInterface"),
    ("FIFO decoding and register writes (opcode decoder, BP/XF/CP registers, reading the FIFO)", r"OpcodeDecoder|ReadDataFromFifo|LoadBPReg|LoadXFReg|LoadCPReg|BPWritten|XFRegWritten|XFStateManager|BPFunctions|CopyFromEmu|LoadIndexedXF|GetPointerForRange|DataReader|CPMemory"),
]
BACKEND = VIDEO_GROUPS[4][0]
HOST_GROUPS = [
    ("the timing probe and the pacing log (instruments)", r"FzgxProbe"),
    ("online layer: undo log (undo_log.cpp)", r"fzgx_core:undo_log"),
    ("online layer: restore and re-simulation's own code (rollback.cpp)", r"fzgx_core:rollback"),
    ("online layer: the state checksum (checksum.cpp)", r"fzgx_core:checksum"),
    ("online layer: replay record and live feed (replay.cpp)", r"fzgx_core:replay"),
    ("online layer: relay and schedule (relay_wire, udp, session, schedule)", r"fzgx_core:(relay_wire|udp|session|schedule)"),
    ("online layer: a frame's steps (frame.cpp, step.cpp, guest.cpp)", r"fzgx_core:(frame|step|guest)\."),
    ("online layer: the tests' instruments (instruments.cpp)", r"fzgx_core:instruments"),
    ("online layer: other core files", r"fzgx_core:"),
    ("the adapter and the game window (host calls, the data window, the strip)", r"moderngekko_runtime:(adapter|host|game|frame|frame_paint|pins|window|taskbar|mod_loader|module)"),
    ("run loop (StaticRecompCore::Run)", r"\?Run@StaticRecompCore|StaticRecompCore_Run"),
    ("hooks out of generated code: memory and hardware", r"HookExternal|HookSPR"),
    ("hooks: cache control (dcbf, icbi)", r"HookCacheControl|OnICacheInvalidate|InvalidateICache"),
    ("hooks: FIFO flush", r"HookGatherPipeFlush|PublishGatherPipe"),
    ("hooks: one instruction on the interpreter", r"HookInstructionFallback"),
    ("static recomp core, other (sync, chunk checks, budget)", r"StaticRecomp"),
    ("emulator clock and events (CoreTiming)", r"CoreTiming"),
    ("FIFO: gather pipe, command processor", r"GPFifo|CommandProcessor|Fifo\.cpp|FifoManager"),
    ("video interface", r"VideoInterface"),
    ("audio: DSP emulation (HLE, the AX mixer)", r"DSPHLE|UCodes|AXUCode|AX\.cpp|AXVoice|DSP\.cpp|DSPEmulator|DSPCore|@DSP@|Accelerator"),
    ("audio: output (mixer, stream, backend)", r"audiocommon:|AudioInterface|Mixer|cubeb|WASAPI|StreamADPCM"),
    ("MMU and memory map", r"MMU\.cpp|Memmap|MMIO"),
    ("processor interface, exceptions", r"ProcessorInterface|PowerPC\.cpp|Exception"),
    ("fallback JIT (compiler, dispatcher, block cache)", r"Jit64|JitBase|JitCache|JitCommon|PPCAnalyst|BlockCache|x64Emitter"),
    ("interpreter", r"Interpreter"),
    ("serial interface, pads", r"SerialInterface|SI_|SI\.cpp|GCPad|inputcommon:|SDL3"),
    ("disc, EXI, memory card", r"DVD|discio:|EXI|Memcard|GCMemcard"),
    ("video code on this thread (backend, vertex loader, texture cache)", r"videocommon:|videovulkan:|videod3d|Vulkan"),
]


def host_group(name, obj):
    key = name + " " + obj
    return next((g for g, pattern in HOST_GROUPS if re.search(pattern, key)), "emulator, other")


def table(title, counter, total, per_sample_ms, top, note=""):
    print(f"\n{title}{(' (' + note + ')') if note else ''}")
    for key, n in counter.most_common(top):
        print(f"  {n * per_sample_ms:7.3f} ms  {100 * n / total:5.1f}%  {n:6d}  {key}")


def options(args, w):
    """The command line; w is the work folder."""
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--from", dest="first", type=int, default=600)
    ap.add_argument("--to", dest="last", type=int, default=10 ** 9)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--exe-map", default=f"{w}/scratch/map/tools/moderngekko-run.map")
    ap.add_argument("--module-map", default="")
    ap.add_argument("--functions", default="")
    ap.add_argument("--symbols", default="")
    ap.add_argument("--tags", default=f"{w}/scratch/map/tools/guest-tags.json")
    ap.add_argument("--video", action="store_true")
    ap.add_argument("--others", action="store_true")
    ap.add_argument("--mode", type=int, default=2)
    ap.add_argument("--detail", action="store_true")
    ap.add_argument("--window", default="", help="S0,S1: the fields that end between S0 and S1 seconds after the run's first field, whatever the mode")
    a = ap.parse_args(args)
    a.folder = a.run if os.path.isdir(a.run) else f"{w}/port/runs/{a.run}"
    return a


def scene_fields(run, a):
    """The scene's fields: (start, end, cycles, race frame, trips, idles, fallback steps, interpreted)."""
    scene = []
    first_end = run.fields[0][0] if run.fields else 0
    for i in range(1, len(run.fields)):
        end, _, cycles, mode, _, rf, trips, idles, fb, interp = run.fields[i]
        if a.window:
            w0, w1 = (float(x) for x in a.window.split(","))
            inside = first_end + w0 * 1e6 <= end <= first_end + w1 * 1e6
        else:
            inside = mode == a.mode and a.first <= rf <= a.last
        if inside:
            scene.append((run.fields[i - 1][0], end, cycles, rf, trips, idles, fb, interp))
    return scene


def head(run, scene):
    """The scene's header and every thread's time; returns the mean field's wall time and the CPU thread's own."""
    t0, t1 = scene[0][0], scene[-1][1]
    wall_ms = [(e - s) / 1000 for s, e, *_ in scene]
    cpu_ms = [c / run.tsc_per_us / 1000 for _, _, c, *_ in scene]
    q = sorted(cpu_ms)
    print(f"run {os.path.basename(run.folder.rstrip('/'))}: {run.backend}")
    print(f"scene: race frames {scene[0][3]}-{scene[-1][3]}, {len(scene)} fields, {(t1 - t0) / 1e6:.1f} s; {(scene[-1][3] - scene[0][3]) / len(scene):.3f} race frames a field")
    print(f"field wall time: mean {statistics.mean(wall_ms):.3f}, median {statistics.median(wall_ms):.3f} ms; over 20 ms: {sum(1 for w in wall_ms if w > 20)}")
    print(f"CPU thread per field (pacing log): mean {statistics.mean(cpu_ms):.3f}, median {statistics.median(cpu_ms):.3f}, "
          f"90% {q[int(len(q) * .9)]:.3f}, 99% {q[int(len(q) * .99)]:.3f}, longest {q[-1]:.3f} ms")
    print(f"run-loop trips a field: mean {statistics.mean(s[4] for s in scene):.0f}, idle {statistics.mean(s[5] for s in scene):.0f}; "
          f"fallback steps {statistics.mean(s[6] for s in scene):.1f}, interpreted {statistics.mean(s[7] for s in scene):.1f}")
    if run.rollback:
        rb = [r for r in run.rollback if t0 <= int(r["at_us"]) <= t1]
        depth = collections.Counter(int(r["depth"]) for r in rb)
        print(f"displayed frames {len(rb)}: by rollback depth {dict(sorted(depth.items()))}; steps run again a frame {statistics.mean(int(r['resim_n']) for r in rb):.2f}; "
              f"the hook {statistics.mean(float(r['hook_us']) for r in rb) / 1000:.3f} ms, the undo log's tracking {statistics.mean(float(r['track_us']) for r in rb) / 1000:.3f} ms (wall, a frame)")
    print("\nthreads, CPU time per field over the scene (cycle counter read once a second):")
    rows = []
    for tid in run.cycles:
        ms, span = run.thread_ms(tid, t0, t1)
        if span:
            rows.append((ms / span * statistics.mean(wall_ms), tid))
    for per_field, tid in sorted(rows, reverse=True)[:14]:
        print(f"  {per_field:7.3f} ms  {tid:6d}  {run.thread_names.get(tid, '')}")
    print(f"  {sum(r[0] for r in rows):7.3f} ms  all {len(rows)} threads")
    return statistics.mean(wall_ms), statistics.mean(cpu_ms)


def on_processor(sym, cpu):
    """Splits the CPU thread's samples: those on the processor (with their host place), and where the others wait."""
    on, blocked, kernel = [], collections.Counter(), collections.Counter()
    for s in cpu:
        module, name, obj = sym.host(s[1])
        if module in ("ntdll.dll", "win32u.dll") and re.match(r"^(Nt|Zw)", name):
            callers = [n for n, o in sym.callers(s[9]) if not GENERIC.search(n)]
            who = next((label for pattern, label in WAITERS for n in callers[:6] if pattern in n), callers[0][:60] if callers else "?")
            if BLOCKING.match(name):
                blocked[f"{who}  ({name})"] += 1
                continue
            kernel[f"{name} <- {who}"] += 1
        on.append((s, module, name, obj))
    return on, blocked, kernel


class Shares:
    """What the CPU thread's on-processor samples are counted into."""

    def __init__(self, sym, tags):
        self.sym, self.tags = sym, tags
        self.by_host = collections.Counter()
        self.by_host_fn = collections.defaultdict(collections.Counter)
        self.place = collections.Counter()            # (guest place, guest code or emulator work) -> samples
        self.place_host = collections.defaultdict(collections.Counter)
        self.task_rows = collections.defaultdict(lambda: [0, 0])   # (path, task) -> [all samples, in generated code]
        self.child_rows = collections.defaultdict(lambda: [0, 0, 0])  # main loop's callee -> [all, generated, with drawing]
        self.irq_rows = collections.defaultdict(lambda: [0, 0])
        self.rows = collections.Counter()             # the handbook's rows
        self.steps = collections.Counter()            # under the online layer's steps: physics guest code, other guest code, emulator work

    def host_place(self, sample, module, name, obj):
        """The host place of one sample, and the guest function it runs when the module's map says so."""
        sym = self.sym
        rip, stack = sample[1], sample[9]
        guest_fn, fn = 0, name
        if module == "module":
            m = re.match(r"func_([0-9A-F]{8})(_closed|_budget)?", name)
            if m:
                guest_fn = int(m.group(1), 16)
                kind = "the image" if guest_fn >= 0x81800000 else "main.rel" if guest_fn >= REL else "main.dol"
                body = {"_closed": "closed", "_budget": "budget", None: "ordinary"}[m.group(2)]
                host = f"generated code: {kind}"
                self.by_host_fn[host][f"{sym.guest_name(guest_fn)} ({body})"] += 1
                self.by_host_fn["generated code by body"][body] += 1
            elif not sym.has_module_map:
                host = "generated code: the module (no link map: not split by function)"
            else:
                host = "the module's helpers (dispatch, FP and interpreter helpers)"
                self.by_host_fn[host][name] += 1
        elif module == "exe":
            fo = obj
            if GENERIC.search(name):
                c = next(((n, o) for n, o in sym.callers(stack) if not GENERIC.search(n)), None)
                if c:
                    fn, fo = c
            host = host_group(fn, fo)
            self.by_host_fn[host][f"{name[:70]}" + (f" <- {fn[:50]}" if fn != name else "")] += 1
        elif module == "(no module)":
            host = "code outside every module (the fallback JIT's code cache)"
            self.by_host_fn[host][f"{rip >> 16:x}xxxx"] += 1
        else:
            c = next(((n, o) for n, o in sym.callers(stack) if not GENERIC.search(n)), None)
            host = host_group(*c) if c else "system and driver DLLs, caller not found"
            self.by_host_fn[host][f"{module}!{name[:40]}" + (f" <- {c[0][:50]}" if c else "")] += 1
        if module != "module":
            near = [name] + [n for n, o in sym.callers(stack)[:5]]
            if any("Throttle@CoreTimingManager" in n or "SleepUntil@PrecisionTimer" in n for n in near[:4]):
                host = THROTTLE
        return host, guest_fn

    def guest_place(self, sample, host, guest_fn, generated):
        """The guest place of one sample, from the guest stack: (kind, label, task or 0, drawing)."""
        sym, tags = self.sym, self.tags
        task_fn, chain = sample[5], sample[8]
        fns = [sym.guest_function(ra) for ra in reversed(chain)]   # outermost first
        if guest_fn:
            fns.append(guest_fn)
        drawing = host.startswith("FIFO") or host.startswith("hooks: FIFO") or any(tags.get(f) == "gx" for f in fns)
        if IRQ in fns:
            i = fns.index(IRQ)
            handler = fns[i + 1] if i + 1 < len(fns) else 0
            label = sym.guest_name(handler) + (f" [{tags[handler]}]" if handler in tags else "") if handler else "(the dispatcher)"
            self.irq_rows[label][0] += 1; self.irq_rows[label][1] += generated
            return "interrupt handlers", label, 0, drawing
        if TASK_RETURN in chain:
            i = len(chain) - 1 - chain.index(TASK_RETURN)       # position of the task runner in fns
            task = fns[i + 1] if i + 1 < len(fns) else task_fn
            path = STEPS if any(sym.guest_name(f) == "image:frame_routine" for f in fns[:i]) else "the game's own call (presentation tasks)"
            self.task_rows[(path, task)][0] += 1; self.task_rows[(path, task)][1] += generated
            return "tasks", path, task, drawing
        if MAIN_LOOP in fns:
            i = fns.index(MAIN_LOOP)
            child = fns[i + 1] if i + 1 < len(fns) else 0
            sub = fns[i + 2] if child == FRAME and i + 2 < len(fns) else 0
            label = (sym.guest_name(child) if child else "(the main loop itself)") + (" > " + sym.guest_name(sub) if sub else "")
            self.child_rows[label][0] += 1; self.child_rows[label][1] += generated; self.child_rows[label][2] += drawing
            return "main loop outside the tasks", label, 0, drawing
        if fns and fns[0] == THREAD_START:
            return ("idle thread" if len(fns) > 2 and fns[1] == IDLE_ENTRY else "other guest threads"), (sym.guest_name(fns[1]) if len(fns) > 1 else ""), 0, drawing
        return "no guest stack (boot, or between threads)", "", 0, drawing

    def add(self, sample, module, name, obj):
        host, guest_fn = self.host_place(sample, module, name, obj)
        self.by_host[host] += 1
        generated = host.startswith("generated code") or host.startswith("the module's helpers")
        kind, label, task, drawing = self.guest_place(sample, host, guest_fn, generated)
        self.place[(kind, "guest code" if generated else "emulator work")] += 1
        self.place_host[kind][host] += 1
        tname = self.sym.guest_name(task) if task else "?"
        if kind == "tasks" and label == STEPS:
            self.steps["physics tasks, guest code" if generated and tname in PHYSICS else "other tasks, guest code" if generated else f"emulator work: {host}"] += 1
        if not generated:
            self.rows[("emulator", host)] += 1
        elif kind == "tasks":
            where = "steps" if label == STEPS else "presentation"
            self.rows[(f"guest code: tasks, {where}", "physics (fn_1_83858, fn_1_850C4, fn_1_C4ABC)" if tname in PHYSICS else "other tasks")] += 1
        elif kind == "main loop outside the tasks":
            self.rows[("guest code: main loop", "drawing (a GX function on the stack)" if drawing else "the rest")] += 1
        else:
            self.rows[("guest code: " + kind, "")] += 1


def cpu_thread(run, sym, a, scene, wall, measured):
    t0, t1 = scene[0][0], scene[-1][1]
    cpu = [s for s in run.cpu if t0 <= s[0] <= t1]
    if not cpu:
        print("no CPU-thread sample in the scene"); return
    on, blocked, kernel = on_processor(sym, cpu)
    n_all, n_on = len(cpu), len(on)
    # a sample is worth the field's wall time over the samples a field: time sampling, with no other assumption
    per = wall / n_all
    print(f"\nCPU thread: {n_all} samples in the scene, {n_on} on the processor ({100 * n_on / n_all:.1f}%), {n_all - n_on} blocked")
    print(f"sum check: on the processor by samples {n_on * per:.3f} ms a field; the cycle counter {measured:.3f} ms a field; one sample = {per * 1000:.2f} us a field")
    table("blocked in", blocked, n_all, per, 12, "ms of wall time a field")
    table("system calls that do not wait", kernel, n_on, per, 12)
    tags = {}
    if os.path.exists(a.tags):
        tags = {int(k, 16): v for k, v in json.load(open(a.tags)).items() if not v.startswith("~")}
    sh = Shares(sym, tags)
    for s, module, name, obj in on:
        sh.add(s, module, name, obj)
    print_cpu(sh, sym, a, per, n_on)


def print_cpu(sh, sym, a, per, n_on):
    def show(title, counter, top=a.top):
        print(f"\n{title}")
        for key, n in counter.most_common(top):
            print(f"  {n * per:7.3f} ms  {100 * n / n_on:5.1f}%  {n:6d}  {key if isinstance(key, str) else ' | '.join(k for k in key if k)}")

    show("CPU thread, the handbook's rows (ms a field)", sh.rows, 60)
    show("CPU thread by host place", sh.by_host)
    show("CPU thread by guest place", sh.place)
    show("inside the online layer's steps (a rollback frame's cost a step is this over the steps a frame ran)", sh.steps, 16)
    print("\ntasks: all samples inside the call | of them in generated code | path | task")
    for (path, task), (n, g) in sorted(sh.task_rows.items(), key=lambda kv: -kv[1][0])[:a.top]:
        if n * per >= 0.01:
            print(f"  {n * per:7.3f} ms  {g * per:7.3f} ms  {path[:28]:28s}  {sym.guest_name(task) if task else '?'}")
    for path in sorted({k[0] for k in sh.task_rows}):
        n = sum(v[0] for k, v in sh.task_rows.items() if k[0] == path); g = sum(v[1] for k, v in sh.task_rows.items() if k[0] == path)
        print(f"  {n * per:7.3f} ms  {g * per:7.3f} ms  all tasks of: {path}")
    print("\nthe main loop outside the task runner: all samples | in generated code | with drawing (a GX function on the stack, or FIFO work) | callee")
    for label, (n, g, d) in sorted(sh.child_rows.items(), key=lambda kv: -kv[1][0])[:a.top]:
        if n * per >= 0.01:
            print(f"  {n * per:7.3f} ms  {g * per:7.3f} ms  {d * per:7.3f} ms  {label}")
    print("\ninterrupt handlers: all samples | in generated code | handler")
    for label, (n, g) in sorted(sh.irq_rows.items(), key=lambda kv: -kv[1][0])[:12]:
        print(f"  {n * per:7.3f} ms  {g * per:7.3f} ms  {label}")
    if a.detail:
        for host, _ in sh.by_host.most_common(a.top):
            table(f"  -- {host}", sh.by_host_fn[host], n_on, per, 10)
        table("  -- generated code by body", sh.by_host_fn["generated code by body"], n_on, per, 5)
        for gp in sh.place_host:
            table(f"  -- {gp}: host places", sh.place_host[gp], n_on, per, 12)


def video_thread(run, sym, a, scene, wall):
    t0, t1 = scene[0][0], scene[-1][1]
    video = [s for s in run.video if t0 <= s[0] <= t1]
    groups = collections.Counter(); group_fn = collections.defaultdict(collections.Counter); blocked_v = collections.Counter(); n_von = 0
    vtid = next((tid for tid, n in run.thread_names.items() if n == "Video thread"), 0)
    vms, vspan = run.thread_ms(vtid, t0, t1)
    for _, rip, stack in video:
        module, name, obj = sym.host(rip)
        callers = [c[0] for c in sym.callers(stack) if not GENERIC.search(c[0])]
        if module in ("ntdll.dll", "win32u.dll") and BLOCKING.match(name):
            blocked_v[next((c[:60] for c in callers[:4]), "?") + f"  ({name})"] += 1
            continue
        n_von += 1
        own = name if module == "exe" and not GENERIC.search(name) else ""
        g = next((label for label, pattern in VIDEO_GROUPS if own and re.search(pattern, own)), None)
        if g is None and module == "(no module)":
            g = VIDEO_GROUPS[3][0]
        if g is None:
            g = next((label for c in callers[:8] for label, pattern in VIDEO_GROUPS if re.search(pattern, c)), "not placed")
        if g.startswith("the FIFO loop") and module != "exe":
            g = BACKEND if module.startswith("nvoglv") else "not placed"
        groups[g] += 1
        group_fn[g][(own[:70] if own else f"{module}!{name[:30]}") + (" <- " + callers[0][:44] if callers and not own else "")] += 1
        group_fn["by module"]["the graphics driver (nvoglv64.dll)" if module.startswith("nvoglv") else "copies (vcruntime memcpy/memmove)" if module.startswith("vcruntime") else
                              "the loaders' generated code" if module == "(no module)" else "the runner's own code" if module == "exe" else module] += 1
    if not video or not n_von:
        return
    vper = wall / len(video)
    print(f"\nvideo thread: {len(video)} samples, {n_von} on the processor ({100 * n_von / len(video):.1f}%); measured {vms / vspan * wall if vspan else 0:.3f} ms a field; "
          f"sum check {n_von / len(video) * wall:.3f} ms")
    table("video thread blocked in", blocked_v, len(video), vper, 4, "ms of wall time a field")
    table("video thread by function group", groups, n_von, vper, 20)
    table("video thread by module", group_fn["by module"], n_von, vper, 8)
    if a.detail:
        for g, _ in groups.most_common(12):
            table(f"  -- {g}", group_fn[g], n_von, vper, 8)


def other_threads(run, sym, scene, wall):
    t0, t1 = scene[0][0], scene[-1][1]
    for tid, samples in sorted(run.others.items(), key=lambda kv: -len(kv[1])):
        inside = [s for s in samples if t0 <= s[0] <= t1]
        ms, span = run.thread_ms(tid, t0, t1)
        if not inside or not span or ms / span * wall < 0.02:
            continue
        c = collections.Counter()
        for _, rip, stack in inside:
            module, name, _ = sym.host(rip)
            callers = [x for x in sym.callers(stack) if not GENERIC.search(x[0])]
            c[(f"{module}!{name[:50]}" if module != "exe" else name[:60]) + (" <- " + callers[0][0][:50] if callers else "")] += 1
        table(f"thread {tid} {run.thread_names.get(tid, '')}: {ms / span * wall:.3f} ms a field", c, len(inside), 0, 8, "sample counts; blocked included")


def main(args):
    a = options(args, os.environ.get("PORT_WORK", work_folder.WORK_DEFAULT))
    run = Run(a.folder)
    sym = Symbols(run, a.exe_map, a.module_map, a.symbols, a.functions)
    scene = scene_fields(run, a)
    if not scene:
        print("no field of the scene in the pacing log"); return
    wall, measured = head(run, scene)
    cpu_thread(run, sym, a, scene, wall, measured)
    if a.video:
        video_thread(run, sym, a, scene, wall)
    if a.others:
        other_threads(run, sym, scene, wall)


if __name__ == "__main__":
    main(sys.argv[1:])
