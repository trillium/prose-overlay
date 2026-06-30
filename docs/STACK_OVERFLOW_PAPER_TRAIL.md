# Stack-Overflow Paper Trail — Research

> **Provenance.** Synthesized 2026-06-29 from a background research-agent sweep of stack-overflow capture techniques across Python, embedded JS (QuickJS / V8 / Node), Rust FFI, and macOS, scoped to this plugin's Python → JS → (sometimes Rust) command pipeline.
> **Companion docs:** [`VIEWPORT_RESEARCH.md`](./VIEWPORT_RESEARCH.md), [`UNDO_REDO_RESEARCH.md`](./UNDO_REDO_RESEARCH.md), [`HAT_ALLOC_OVERFLOW_ANALYSIS.md`](./HAT_ALLOC_OVERFLOW_ANALYSIS.md) (the prior root-cause analysis on QuickJS callback-proxy crossings).

## Context — what we're trying to capture

When a voice command runs through this plugin, the call path looks like Python action → JS (QuickJS embedded by Talon) → sometimes Rust (Cursorless's hat-allocation core). Stack overflows happen during execution and may surface as a JS exception, a signal, or silent process death — we don't always know which. We want the user to be left with **persistent on-disk evidence** of:

- Which voice command was being executed (utterance, action, args).
- The Python → JS → Rust call chain at the moment of overflow — at least the topmost frame on each side.
- State context: recent actions, current Cursorless target, buffer state if reachable.
- A timestamp + stable correlation id so the user can match the trail to the Talon log entry that disappeared.
- **Persistence guarantees:** must be on disk *before* the crash completes. Cannot rely on the crashing process flushing a buffer.

---

## 1. TL;DR recipe — minimum viable setup

Ship a stack-overflow paper trail tonight by combining **two cheap, async-signal-safe artifacts** plus one **macOS freebie**:

- **`last_command.json`** — a Python-side preamble file written *before* every JS/Rust call. Contains utterance, action name, args, timestamp, and a correlation id. Overwritten on each new command, so its contents at investigation time describe the most recent attempt — i.e. the one that crashed.
- **`faulthandler` → fixed file** — `faulthandler.enable(file=open(...), all_threads=True)` writes the Python traceback of every thread on `SIGSEGV / SIGFPE / SIGABRT / SIGBUS / SIGILL`. This is the only thing the standard library promises will survive a native crash. ([Python docs](https://docs.python.org/3/library/faulthandler.html))
- **`faulthandler.dump_traceback_later(N, repeat=True)`** — watchdog timer that dumps tracebacks if a command runs more than N seconds, catching the JS/Rust *hang* case that doesn't fire a signal.
- **An `events.ndjson` append log** — every layer transition (`py→js begin`, `js→rust begin`, `rust→js end`, `js→py end`) writes one line opened **`O_APPEND`** so writes are atomic w.r.t. signals. ([signal-safety(7)](https://man7.org/linux/man-pages/man7/signal-safety.7.html), [open(2)](https://man7.org/linux/man-pages/man2/open.2.html))
- **macOS DiagnosticReports** — every hard crash that escapes faulthandler ends up as a `.ips` JSON file in `~/Library/Logs/DiagnosticReports/`. ([Apple — Interpreting the JSON crash report](https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report)) Stamp a correlation id into the process environment via `os.environ["PROSE_CORR_ID"] = ...` before the risky call — Apple's IPS dump includes the process's env, so the id round-trips into the system crash log and lets you join it back to `last_command.json`.

### Code skeleton (drop into `prose_overlay/`)

```python
# prose_overlay_trail.py — Python-side paper trail
import faulthandler, json, os, time, uuid, pathlib

TRAIL_DIR = pathlib.Path(__file__).parent / "trail"
TRAIL_DIR.mkdir(exist_ok=True)
LAST_CMD = TRAIL_DIR / "last_command.json"
EVENTS = TRAIL_DIR / "events.ndjson"
FAULTLOG = TRAIL_DIR / "faulthandler.log"

# Faulthandler — keep the file handle alive for the life of the process
_fault_fp = open(FAULTLOG, "a", buffering=1)
faulthandler.enable(file=_fault_fp, all_threads=True)

# Events file opened O_APPEND so write() is atomic & async-signal-safe
_events_fd = os.open(EVENTS, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)

def _emit(layer: str, phase: str, corr_id: str, **fields):
    rec = {"t": time.time(), "layer": layer, "phase": phase, "id": corr_id, **fields}
    os.write(_events_fd, (json.dumps(rec) + "\n").encode())

def begin_command(utterance: str, action: str, args: dict) -> str:
    corr_id = uuid.uuid4().hex[:12]
    os.environ["PROSE_CORR_ID"] = corr_id   # leaks into macOS crash report
    payload = {"id": corr_id, "t": time.time(), "utterance": utterance,
               "action": action, "args": args, "pid": os.getpid()}
    # Write+rename for atomicity
    tmp = LAST_CMD.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    tmp.replace(LAST_CMD)
    _emit("py", "begin", corr_id, action=action)
    # Watchdog: if we don't end_command in 5s, dump all threads
    faulthandler.dump_traceback_later(5.0, repeat=False, file=_fault_fp)
    return corr_id

def end_command(corr_id: str, ok: bool, err: str | None = None):
    faulthandler.cancel_dump_traceback_later()
    _emit("py", "end", corr_id, ok=ok, err=err)

# Use around JS calls:
def trace_js(corr_id: str, fn_name: str):
    class _C:
        def __enter__(self):  _emit("js", "begin", corr_id, fn=fn_name); return self
        def __exit__(self, *a): _emit("js", "end", corr_id, exc=str(a[1]) if a[1] else None)
    return _C()
```

Wrap the existing call site in `prose_overlay_hats_js.py`:

```python
corr_id = trail.begin_command(utterance, "allocate_hats", {"n_tokens": len(tokens)})
try:
    with trail.trace_js(corr_id, "proseAllocateHats"):
        result_json = str(_fn(json.dumps(tokens), json.dumps(old_list), stability, ...))
    trail.end_command(corr_id, ok=True)
except Exception as e:
    trail.end_command(corr_id, ok=False, err=repr(e))
    raise
```

**What you get at investigation time:** open `trail/last_command.json` → know which utterance died. Tail `trail/events.ndjson` → find the dangling `begin` with no `end` to see which layer it died in. Read `trail/faulthandler.log` → Python traceback at signal time. Search `~/Library/Logs/DiagnosticReports/` for a `.ips` containing `PROSE_CORR_ID=<id>` → native stack.

---

## 2. What stack overflow looks like at each layer

| Layer | Symptom | Signal that fires | Reaches Python? |
|---|---|---|---|
| **Pure Python recursion** | `RecursionError` raised at `sys.getrecursionlimit()` | None — pure exception | Yes, normal try/except |
| **Python C extension overflow** | Native segfault on C stack | `SIGSEGV` | Only via `faulthandler` |
| **QuickJS (Talon's engine)** | `InternalError: stack overflow` thrown from `js_check_stack_overflow` before the C stack actually overflows | None — it's a JS exception ([QuickJS bytecode interpreter](https://deepwiki.com/bellard/quickjs/2.4-bytecode-interpreter)) | Yes, propagates back through `talon.lib.js` as a Python exception |
| **QuickJS native overflow (rare)** | C stack genuinely overflows past the bytecode guard | `SIGSEGV` | Only via `faulthandler` |
| **V8 / Node (if you ever switch)** | JS `RangeError: Maximum call stack size exceeded` (engine cap), OR native crash → diagnostic report if `--report-on-fatalerror` set ([Node.js diagnostic report](https://nodejs.org/api/report.html)) | None for JS RangeError; `SIGABRT` for native fatal | JS case: yes. Native case: only via diagnostic report file |
| **Rust** | `thread '...' has overflowed its stack\nfatal runtime error: stack overflow\n` to stderr, then `abort()`. Rust installs a `sigaltstack` handler for exactly this. ([rust #69533](https://github.com/rust-lang/rust/issues/69533), [Rust PR #133170 — print backtrace on stackoverflow](https://github.com/rust-lang/rust/pull/133170)) | `SIGSEGV` → handled on alt stack → `SIGABRT` | Reth's `sigsegv_handler.rs` shows the production pattern of overriding it with a custom AS-safe handler ([Reth sigsegv_handler](https://reth.rs/docs/src/reth_cli_util/sigsegv_handler.rs.html)) |
| **Rust FFI via N-API / napi-rs** | Rust `abort()` kills the host Node process. `panic::catch_unwind` does **not** catch stack overflow — only panics ([napi-rs FFI](https://dev.to/daanyaalsobani/calling-rust-from-nodejs-a-practical-guide-to-napi-rs-47om)) | `SIGABRT` from Rust's handler | Node process dies; only diagnostic report survives |
| **Rust via wasm** | wasm has its own shadow stack; overflow → `RuntimeError: call stack exhausted` trap, surfaces as JS exception | None — wasm trap | Yes, as JS exception |

**Key invariant for this specific stack:** because Talon embeds **QuickJS** and QuickJS *probes* the stack before each call via `js_check_stack_overflow` ([quickjs.h](https://github.com/bellard/quickjs/blob/master/quickjs.h)), the overwhelming majority of observed "stack overflows" will be `InternalError: stack overflow` thrown as JS exceptions — i.e. they propagate back to Python as normal exceptions you can `try/except`. The fully native crash case is much rarer than the Rust-side machinery might suggest.

---

## 3. Paper-trail patterns

### A. Python preamble file (`last_command.json`)
- **Captures:** utterance + action + args + correlation id + pid + wall time.
- **Persistence:** `tmp + os.replace()` is atomic on POSIX. The file always represents the most recent *fully-flushed* command attempt. Survives any crash because it was on disk before the risky call started.
- **Complexity:** ~20 lines.
- **Fit:** Perfect. Highest-ROI single artifact.

### B. `faulthandler` enabled to fixed file
- **Captures:** Python traceback of all threads on `SIGSEGV`, `SIGFPE`, `SIGABRT`, `SIGBUS`, `SIGILL`. Implemented in C with only async-signal-safe ops. ([faulthandler docs](https://docs.python.org/3/library/faulthandler.html))
- **Persistence:** Writes via `write()` to a held-open fd — survives even if Python's allocator is broken at signal time. **Caveat:** file must remain open for the life of the process; you cannot use `with open(...)`.
- **Complexity:** 3 lines.
- **Fit:** Mandatory baseline.

### C. `faulthandler.dump_traceback_later(N, repeat=True)`
- **Captures:** Thread tracebacks at hang time. Implemented as a watchdog thread inside CPython.
- **Persistence:** Same fd as B. Fires from a *non-crashed* thread, so it works even when the crashing thread is stuck in C code.
- **Complexity:** 2 lines.
- **Fit:** Catches the silent-hang case (e.g. infinite loop in QuickJS) that signals don't catch.

### D. NDJSON event log opened `O_APPEND`
- **Captures:** Layer-transition events. Combined with `begin`/`end` discipline, the dangling `begin` identifies the failure layer.
- **Persistence:** `O_APPEND` makes `write()` **atomic w.r.t. signals and processes** — the kernel does the seek+write as a single step ([open(2) `O_APPEND`](https://man7.org/linux/man-pages/man2/open.2.html)). `os.write()` on the raw fd is async-signal-safe ([signal-safety(7)](https://man7.org/linux/man-pages/man7/signal-safety.7.html)). Lines smaller than `PIPE_BUF` (~4 KB on macOS) are never torn.
- **Complexity:** ~30 lines.
- **Fit:** Excellent. Pairs with B+C to localize failures to a specific layer.

### E. mmap ring buffer for high-frequency events
- **Captures:** Same as D but at much higher rate without syscall cost per event.
- **Persistence:** `MAP_SYNC` gives true crash-safe persistence — but it's Linux-only and DAX-only. ([mmap(2)](https://man7.org/linux/man-pages/man2/mmap.2.html)) On macOS you only get **kernel-best-effort** writeback unless you `msync(MS_SYNC)` at known checkpoints. ([Wuffs mmap-ring-buffer example](https://github.com/google/wuffs/blob/main/script/mmap-ring-buffer.c))
- **Complexity:** Significant — needs format spec, head/tail atomics, reader tool.
- **Fit:** Overkill for voice commands (1–10 transitions per command). Skip until you're tracing wasm hot loops.

### F. Pre-flight stack depth probe
- **Captures:** Estimated remaining stack before a deep call. With **`stacker::remaining_stack()`** (Rust) you can early-return "would-have-overflowed" rather than actually overflow. ([stacker crate](https://docs.rs/stacker)) With **`JS_SetMaxStackSize`** (QuickJS) you can raise the budget rather than detect — but Talon doesn't expose this.
- **Persistence:** N/A — this is prevention, not capture. Pair with B to log the avoided overflow.
- **Complexity:** Low in Rust, requires patched Talon for QuickJS.
- **Fit:** Mediocre. Pre-flight checks bloat hot paths and the actual fix (per [`HAT_ALLOC_OVERFLOW_ANALYSIS.md`](./HAT_ALLOC_OVERFLOW_ANALYSIS.md)) is structural — remove the callback-proxy crossing.

### G. Custom `sigaltstack` + JSON-writing signal handler (Rust side)
- **Captures:** Native backtrace at the actual overflow site.
- **Persistence:** Must use only async-signal-safe APIs — no allocation, no locks. The `backtrace` crate is **not** AS-safe. Rust's stdlib handler uses libunwind frame-by-frame with a pre-allocated buffer. ([Rust PR #133170](https://github.com/rust-lang/rust/pull/133170))
- **Complexity:** High. C-level signal-handler code in Rust.
- **Fit:** Only if you ship your own Rust FFI library. Not applicable to the current Cursorless-in-QuickJS pipeline.

### H. macOS DiagnosticReports (free)
- **Captures:** Full native stack of every thread, register state, image list, *process environment*. Stored in `~/Library/Logs/DiagnosticReports/<process>-<date>-<pid>.ips`. Format is two back-to-back JSON dictionaries: metadata header + detailed body. ([Apple — Interpreting JSON crash report](https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report), [Apple — Acquiring crash reports](https://developer.apple.com/documentation/xcode/acquiring-crash-reports-and-diagnostic-logs))
- **Persistence:** Written by `ReportCrash` system daemon after process death. Guaranteed.
- **Complexity:** Zero on the production side; you just need a parser to correlate.
- **Fit:** Take it. The correlation trick — `os.environ["PROSE_CORR_ID"] = id` before the risky call — is the cheapest way to join `.ips` files to the app-level trail.

### I. External watchdog / sentinel file
- **Captures:** Crash *fact* — marker file present, producing process gone.
- **Persistence:** Inherent — survives because the watchdog is a different process.
- **Complexity:** Medium — needs a daemon (launchd plist). For Talon use, you can probably skip in favor of B+C, but it's the model that Sentry / Crashpad / Breakpad use ([Sentry signal handling](https://docs.sentry.io/platforms/native/advanced-usage/signal-handling/), [Sentry stack overflow](https://docs.sentry.io/platforms/native/advanced-usage/stack-overflow-handling/)).
- **Fit:** Skip for v1. Add for v2 if Talon itself dies (vs. just the voice command).

### J. FFI-boundary checkpoints (the "begin/end pair" pattern)
- **Captures:** Which side of which boundary held control at crash time.
- **Persistence:** Inherits from the event log it writes to (D).
- **Complexity:** Low — wrap each call site.
- **Fit:** Excellent. Turns D from "we crashed" into "we crashed in JS holding a callback proxy."

---

## 4. Tools / libraries table

| Tool | Layer | What it does | What survives a crash | Plug-in for this stack |
|---|---|---|---|---|
| `faulthandler` (stdlib) — [docs](https://docs.python.org/3/library/faulthandler.html) | Python | Python traceback dump on signal, watchdog timer | File written by AS-safe `write()` during signal | **Use as v1 baseline** — 3 lines of code |
| `tracemalloc` (stdlib) | Python | Allocation snapshots | Only if snapshotted proactively | Skip — wrong tool for stack overflow |
| `sentry-sdk` (Python) — [native signal handling](https://docs.sentry.io/platforms/native/advanced-usage/signal-handling/) | Python | Captures Python exceptions, ships to Sentry | Network call, may not complete before death | Skip locally — plugin shouldn't phone home |
| `talon.lib.js` (Talon built-in) — [Talon docs](https://talonvoice.com/docs/) | JS | Wraps QuickJS; JS `InternalError: stack overflow` surfaces as Python exception | Yes — normal Python exception | Already in use. Just `try/except` it |
| QuickJS `JS_SetMaxStackSize` — [quickjs.h](https://github.com/bellard/quickjs/blob/master/quickjs.h) | JS engine | Configure native stack budget | N/A | Not exposed by Talon — can't reach |
| Node `--report-on-fatalerror` — [Node.js diagnostic report](https://nodejs.org/api/report.html) | JS host | JSON crash report with JS + native stack + heap stats | Yes — Node writes file before exit | Only if you migrate off QuickJS |
| `process.on('uncaughtException')` — [Node errors docs](https://nodejs.org/api/errors.html) | JS host | Last-ditch JS handler | Process continues by default — but **stack overflow is unrecoverable** | Document the boundary |
| `node:diagnostics_channel`, `node:trace_events` | JS host | In-process tracing pipes | Buffered — not crash-safe by default | Pair with diagnostic report |
| `backtrace` crate — [docs.rs/backtrace](https://docs.rs/backtrace) | Rust | Capture symbolicated stack | NOT async-signal-safe — uses allocation/locks | Use in `panic::set_hook`, not in signal handler |
| `panic::set_hook` + `catch_unwind` — Rust stdlib | Rust | Catch panics, run callback | Only panics — does **not** catch stack overflow | Document the boundary |
| `signal-hook` crate — [docs.rs/signal-hook](https://docs.rs/signal-hook) | Rust | Cross-platform signal multiplexing | Yes if handler is AS-safe | For your own Rust FFI |
| `stacker` crate — [docs.rs/stacker](https://docs.rs/stacker) | Rust | `remaining_stack()` + `maybe_grow()` heap fallback | Prevention, not capture | Only if you own Rust code in the pipeline |
| `minidump-writer` crate — [GitHub](https://github.com/rust-minidump/minidump-writer) | Rust | Breakpad-compatible minidump from signal handler | Yes — designed for this exact case | Heavy; skip unless you own Rust FFI |
| `tracing` + `tracing-appender` — [docs.rs/tracing-appender](https://docs.rs/tracing-appender) | Rust | Structured logging w/ rolling files | `non_blocking` is **NOT crash-safe** unless you hold `WorkerGuard` and panic unwinds | Use blocking writer or hold guard explicitly |
| `human-panic` / `color-eyre` | Rust | Pretty panic dumps to file | Panic only, not overflow | Document boundary |
| Sentry Native / Crashpad / Breakpad — [Sentry stack overflow](https://docs.sentry.io/platforms/native/advanced-usage/stack-overflow-handling/) | Native | Signal handler → minidump file → external uploader | Yes — external process uploads | Industrial-strength; overkill for plugin |
| macOS `ReportCrash` → `.ips` JSON — [Apple docs](https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report) | OS | Per-process JSON crash dump in `~/Library/Logs/DiagnosticReports/` with env, registers, threads | Yes — written by separate daemon | **Free; just stamp a correlation id into env** |
| `/usr/bin/sample` | macOS | User-space sampling profiler against a running pid | N/A — diagnose hang as it happens, not after | Useful manual tool when watchdog fires |
| `os_log` | macOS | Unified system log | Yes — written by `logd` daemon | Skip for plugin (noisy, low signal) |
| OpenTelemetry tracing | Cross-language | Distributed-style span tracking | Buffered, network — not crash-safe | Wrong tool |

---

## 5. Recommended stack

### v1 (ship tonight — under 100 LOC)

Add a single file `prose_overlay/prose_overlay_trail.py` with the skeleton above. Wire it into the three Python shims:

- `prose_overlay_actions_js.py` → wrap `_fn(...)` in `begin_command` / `trace_js` / `end_command`.
- `prose_overlay_hats_js.py` → same.
- `prose_overlay_targets_js.py` → same.

#### File layout in `prose_overlay/trail/`

```
prose_overlay/trail/
├── last_command.json          # Overwritten each call. Pre-call state.
├── events.ndjson              # O_APPEND. One line per begin/end event.
├── faulthandler.log           # Faulthandler writes here on SIGSEGV/timeout.
└── README.md                  # "Open last_command.json first" investigation guide.
```

Add a `.gitignore` for the directory (local diagnostic data).

**Coverage guarantee for v1:**
- *JS-side QuickJS overflow (the actual observed bug)*: caught as Python exception in your existing `try/except`, end event logs `ok=False`. Done.
- *Native segfault in Talon's C code*: `faulthandler.log` contains Python traceback at signal time. `events.ndjson` last `begin` shows which layer.
- *Hang (infinite loop in JS)*: `dump_traceback_later(5.0)` fires, dumps all threads to `faulthandler.log`.
- *Talon process death*: `~/Library/Logs/DiagnosticReports/Talon-*.ips` produced by macOS. Grep for `PROSE_CORR_ID` in the env dump to find which command did it.
- *Investigation: "what did I just say when it died?"*: `cat trail/last_command.json`. One file. One open. Done.

### v2 (later, only if v1 misses something)

- Add `scripts/triage_trail.py` that joins `events.ndjson` + `last_command.json` + the newest `.ips` file matching the correlation id, and prints a single multi-line summary.
- Move `events.ndjson` to an mmap'd ring buffer if event rate exceeds ~1000/s (you're nowhere near this).
- Add an external launchd watchdog daemon that monitors a `current.lock` sentinel file and writes a `crashed_at_<id>.json` if Talon dies while a command was in flight.
- If you ever move parts off QuickJS into a Rust FFI: install a `sigaltstack` Rust handler that writes a JSON record (AS-safe, no allocation), and ship the `minidump-writer` crate.

---

## 6. Open questions to answer before implementing

1. **Does Talon's main loop run command actions on the main thread or a worker thread?** `faulthandler.enable(all_threads=True)` covers both, but `dump_traceback_later` defaults to the calling thread only — confirms which thread we register from.
2. **Will registering `faulthandler` chain or override Talon's existing signal handlers?** `faulthandler.enable(chain=True)` (default-on in 3.10+) chains to the previous handler, which is what you want. Need to verify Talon hasn't installed its own incompatible SIGSEGV handler.
3. **Is `os.environ` writes through to the OS process environment on macOS?** CPython mirrors `os.environ` to libc `setenv`, which `ReportCrash` does dump — but worth a one-time smoke test (force a crash, check the `.ips`).
4. **Where do you want `trail/` to live?** Plugin dir is convenient but gets committed to dotfiles by accident. Suggest `~/Library/Application Support/talon/prose_overlay_trail/` to keep it out of the repo.
5. **Retention policy?** `events.ndjson` is append-only and grows forever. v1: rotate at 10 MB. Or just `truncate(0)` on each Talon start.
6. **Do you want a correlation-id surface on the user side?** E.g. a `last_corr_id.txt` you can read aloud / paste into a bug report. Cheap to add; might be ergonomic.
7. **Is there actually any Rust in this pipeline today?** The prompt frames this as Python → JS → Rust, but the codebase shows Python → QuickJS only. The Rust-side advice is preserved for future relevance but currently has no hook point. Confirm before scoping.

---

## Files referenced

- [`HAT_ALLOC_OVERFLOW_ANALYSIS.md`](./HAT_ALLOC_OVERFLOW_ANALYSIS.md) — prior root-cause analysis (QuickJS callback proxy crossing).
- `prose_overlay_hats_js.py` — primary instrumentation site.
- `prose_overlay_actions_js.py` — secondary instrumentation site.
- `prose_overlay_targets_js.py` — tertiary instrumentation site.

---

## Sources

- [Python `faulthandler` docs](https://docs.python.org/3/library/faulthandler.html)
- [`signal-safety(7)` — async-signal-safe functions](https://man7.org/linux/man-pages/man7/signal-safety.7.html)
- [`open(2)` — `O_APPEND` atomicity](https://man7.org/linux/man-pages/man2/open.2.html)
- [`mmap(2)` — `MAP_SYNC` crash-safe mappings](https://man7.org/linux/man-pages/man2/mmap.2.html)
- [QuickJS source — `quickjs.h`](https://github.com/bellard/quickjs/blob/master/quickjs.h)
- [QuickJS bytecode interpreter overview (DeepWiki)](https://deepwiki.com/bellard/quickjs/2.4-bytecode-interpreter)
- [QuickJS `InternalError: stack overflow` issue](https://github.com/bellard/quickjs/issues/23)
- [QuickJS stack overflow in `JS_CallInternal`](https://github.com/quickjs-ng/quickjs/issues/775)
- [Node.js Diagnostic Report API](https://nodejs.org/api/report.html)
- [Node.js Errors / `uncaughtException`](https://nodejs.org/api/errors.html)
- [Apple — Interpreting JSON crash reports](https://developer.apple.com/documentation/xcode/interpreting-the-json-format-of-a-crash-report)
- [Apple — Acquiring crash reports and diagnostic logs](https://developer.apple.com/documentation/xcode/acquiring-crash-reports-and-diagnostic-logs)
- [Talon Voice docs](https://talonvoice.com/docs/)
- [Rust issue #69533 — `sigaltstack` guard](https://github.com/rust-lang/rust/issues/69533)
- [Rust PR #133170 — print backtrace on stack overflow](https://github.com/rust-lang/rust/pull/133170)
- [Rust PR #113565 — nicer SIGSEGV backtraces](https://github.com/rust-lang/rust/pull/113565)
- [Reth `sigsegv_handler.rs` reference implementation](https://reth.rs/docs/src/reth_cli_util/sigsegv_handler.rs.html)
- [`stacker` crate docs](https://docs.rs/stacker)
- [`stacker::remaining_stack`](https://docs.rs/stacker/latest/stacker/fn.remaining_stack.html)
- [`stacker::maybe_grow`](https://docs.rs/stacker/latest/stacker/fn.maybe_grow.html)
- [`tracing-appender` docs](https://docs.rs/tracing-appender/latest/tracing_appender/)
- [`tracing-appender` `WorkerGuard`](https://docs.rs/tracing-appender/latest/tracing_appender/non_blocking/struct.WorkerGuard.html)
- [Sentry — Signal Handling for Native SDKs](https://docs.sentry.io/platforms/native/advanced-usage/signal-handling/)
- [Sentry — Handling Stack Overflows](https://docs.sentry.io/platforms/native/advanced-usage/stack-overflow-handling/)
- [Sentry SDK Development — Signal Handlers](https://develop.sentry.dev/sdk/platform-specifics/native-sdks/signal-handlers/)
- [napi-rs practical guide](https://dev.to/daanyaalsobani/calling-rust-from-nodejs-a-practical-guide-to-napi-rs-47om)
- [Snellman — Ring buffer implementation patterns](https://www.snellman.net/blog/archive/2016-12-13-ring-buffers/)
- [Wuffs mmap ring buffer example](https://github.com/google/wuffs/blob/main/script/mmap-ring-buffer.c)
