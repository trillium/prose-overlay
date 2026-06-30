# Stack-Overflow Paper Trail — Exploration Plan

> Source research: [`STACK_OVERFLOW_PAPER_TRAIL.md`](./STACK_OVERFLOW_PAPER_TRAIL.md). Companion plans: [`UNDO_REDO_PLAN.md`](./UNDO_REDO_PLAN.md), [`HAT_ALLOC_OVERFLOW_ANALYSIS.md`](../HAT_ALLOC_OVERFLOW_ANALYSIS.md).
> Drafted 2026-06-30. **This is an exploration plan, not an implementation commitment.** Every slice is a separate experiment with its own keep/kill decision.

## 1. TL;DR

- Goal of the *whole* exploration: **does a small, gated, on-disk paper trail catch the next stack overflow we hit?** If yes, expand. If no, back out — we picked the wrong capture layer.
- Start with slice A only: `faulthandler` to a fixed file, behind an env-var gate, default **off**. ~10 LOC, zero changes to hot paths, zero new dependencies.
- Learning goal of slice A: *when Talon dies on a known-bad overflow (the `HAT_ALLOC_OVERFLOW_ANALYSIS.md` callback-proxy crash, intentionally reproduced), does `faulthandler.log` actually contain a Python traceback?* If yes → slice B is justified. If no → Talon catches the signal first, and we need a different capture layer (most likely the system `.ips` files alone).
- Every slice is independently revert-able by `git revert <sha>` **and** independently disabled at runtime by unsetting one env var. No flag = no behavior change. Slices never overwrite each other's artifacts.
- The paper trail is a **separate file tree** from `prose_overlay_debug.py` (justified in §4). Composing them is a v2 question, not a v0 one.
- Per [research §0.7 "Is there actually any Rust in this pipeline today?"](./STACK_OVERFLOW_PAPER_TRAIL.md#6-open-questions-to-answer-before-implementing), this stack is Python → QuickJS only. The Rust-side advice is parked. Slices that target Rust are explicitly out of scope.
- Per [research §1 "macOS DiagnosticReports"](./STACK_OVERFLOW_PAPER_TRAIL.md#1-tldr-recipe--minimum-viable-setup), the env-var correlation-id trick is free — but it's a *slice unto itself* (E), gated and tested separately, because writing to `os.environ` from a Talon plugin is the kind of foundational thing that's annoying to undo if it interferes with something.
- We are *not* shipping the v1 stack from the research doc as-one. The research doc bundles five techniques into "v1." This plan splits them into five experiments because two of them (D, E) have real risk of leaving foundational debt.

## 2. Decision-tree shape (the modular spine)

```
A — bare faulthandler to a fixed file (env-var gated, default off)
  ├─ catches a reproduced overflow with a useful Python traceback → B
  ├─ fires but the traceback is useless (just QuickJS C frames) → STOP; rely on macOS .ips alone
  └─ doesn't fire at all (Talon swallows the signal) → STOP; need a different capture layer

B — last_command.json preamble write before JS bridge calls
  ├─ file is on disk before the crash, contents identify the dying utterance → C
  ├─ file write is buffered/lost in a crash → switch to O_SYNC fsync, or shelve
  └─ writes are too noisy / slow down hot path measurably → narrow to allocate-hats only

C — events.ndjson append log for layer-transition events (O_APPEND)
  ├─ a dangling `begin` reliably localizes the failure layer → D (consider)
  ├─ too many events, signal-to-noise is bad → narrow event set (begin/end only)
  └─ event-log syscall cost shows up in hat reallocation latency → ship A+B, stop here

D — dump_traceback_later watchdog for hangs (Talon-side)
  ├─ catches a real hang the user hits in normal use → keep
  ├─ false-positives swamp signal (5s timer fires on slow-but-fine paths) → tune threshold or drop
  └─ no observed hang in N weeks of use → drop, no value justified

E — macOS DiagnosticReports correlation (env-var stamping)
  ├─ optional — only if A-C land cleanly AND we hit a true crash that bypasses A
  ├─ env var actually appears in the .ips file → keep, document the join recipe
  └─ env var doesn't make it into the .ips → drop, the cost was zero anyway
```

Edges between slices are **AND** gates: B doesn't start until A returns a useful signal. C doesn't start until B is in. D and E are independent and can be skipped or run in parallel after C.

Each slice ships as one commit with a single env var to disable. Each can be removed by `git revert <sha>` without touching the others.

## 3. Per-slice specs

### Slice A — faulthandler to a fixed file

**Goal:** Find out whether faulthandler, registered from inside a Talon plugin, actually captures the Python traceback when Talon's embedded QuickJS dies on a reproduced overflow. This is the single fact that decides everything downstream.

**Files touched:**
- New: `prose_overlay_trail.py` (~30 LOC — module-level init only, no API surface beyond a docstring describing how to disable)
- Modified: `prose_overlay.py` (+2 LOC — `from . import prose_overlay_trail  # noqa: F401` near the top, after the canvas/instance wiring so it imports last)

**Env-var gate:** `PROSE_OVERLAY_TRAIL` — `"1"` enables, anything else (including unset) disables. Default OFF. Checked once at module import, not per-call.

**Storage path:** `~/Library/Logs/prose_overlay_trail/faulthandler.log`
- *Not* under `~/.talon/` (would mingle with `prose_overlay_debug.jsonl` and Talon-owned state; harder to wipe).
- *Not* under the plugin directory (would land inside the sync rsync target, gets copied around for nothing, possibly committed by accident; matches [research §6 q4](./STACK_OVERFLOW_PAPER_TRAIL.md#6-open-questions-to-answer-before-implementing) — keep it out of the repo).
- *Not* `/tmp/` (cleared on reboot, useless for "last week's mystery crash").
- `~/Library/Logs/<app>/` is Apple's documented convention and is the directory `ReportCrash` writes near.
- Created on plugin import with `mkdir(parents=True, exist_ok=True)`.

**Keep criterion:** Force a hat-allocator overflow per the `HAT_ALLOC_OVERFLOW_ANALYSIS.md` recipe (revert Option A, run a phrase that triggers it). `faulthandler.log` exists and contains a Python traceback whose topmost frame is inside `prose_overlay_hats_js.py` or `talon.lib.js`. That proves the capture layer works.

**Kill criterion:** Either (a) the file is empty / missing after the reproduced crash, or (b) registering faulthandler breaks Talon's own signal handling (Talon stops cleanly handling SIGINT, or crashes earlier than before). Either is a hard "stop, this approach doesn't fit Talon."

**Reversibility:**
- Run-time disable: `unset PROSE_OVERLAY_TRAIL` and restart Talon. Module imports, sees no flag, returns at the top.
- Code revert: `git revert <slice-A-sha>` — one new file, two-line import in `prose_overlay.py`. Clean.
- Disk cleanup: `rm -rf ~/Library/Logs/prose_overlay_trail/` — no other slice writes there yet.

**Async-signal-safety claim:** `faulthandler` is implemented in CPython using only `write(2)` to a pre-opened fd plus the libunwind walker; it makes no allocator calls or libc calls outside the AS-safe set listed in [signal-safety(7)](https://man7.org/linux/man-pages/man7/signal-safety.7.html). See [Python `faulthandler` docs](https://docs.python.org/3/library/faulthandler.html) — the module documents this guarantee explicitly. We rely on it; we do not write our own signal handler in this slice.

```python
# prose_overlay_trail.py — slice A only
import faulthandler
import os
import pathlib

_TRAIL_ENABLED = os.environ.get("PROSE_OVERLAY_TRAIL") == "1"

if _TRAIL_ENABLED:
    _TRAIL_DIR = pathlib.Path.home() / "Library" / "Logs" / "prose_overlay_trail"
    _TRAIL_DIR.mkdir(parents=True, exist_ok=True)
    # File handle MUST live for the process lifetime — see faulthandler docs.
    # Buffering=0 is implicit for the underlying fd; line buffering at the
    # Python wrapper is fine because the C-level handler bypasses the wrapper.
    _fault_fp = open(_TRAIL_DIR / "faulthandler.log", "a", buffering=1)
    # chain=True is the 3.10+ default — keep explicit so any Talon-installed
    # handler still runs after ours.
    faulthandler.enable(file=_fault_fp, all_threads=True, chain=True)
```

That's the whole slice. No new API, no new call sites in the bridges, no event log, no preamble file, no env stamping. The point is to learn one thing.

---

### Slice B — `last_command.json` preamble

**Prerequisite:** Slice A keep-criterion satisfied.

**Goal:** Learn whether a synchronous "preamble" write *before* the risky JS call lands on disk with enough fidelity that a post-mortem can answer "what was the user trying to do when it died?"

**Files touched:**
- Modified: `prose_overlay_trail.py` (+~40 LOC — adds `begin_command()` / `end_command()` with `tmp + os.replace` atomicity, per [research §3.A](./STACK_OVERFLOW_PAPER_TRAIL.md#a-python-preamble-file-lastcommandjson))
- Modified: `prose_overlay_hats_js.py` (+~6 LOC — wrap the existing `_fn(...)` call in `begin_command` / `end_command`)
- Modified: `prose_overlay_targets_js.py` (+~6 LOC — same pattern as hats)
- *Not yet:* `prose_overlay_actions_cursorless.py` (the action surface). Reason: that file calls *through* the JS bridges, which already wrap themselves in B. Wrapping again would double-write the preamble and confuse a future correlation join.

**Env-var gate:** Same `PROSE_OVERLAY_TRAIL=1`. Slice B's call sites are *unconditional* if the trail is enabled — once you have it, you want every bridge crossing covered. Per-bridge gating would be a foundational mistake (config sprawl); per-call gating would be premature optimization.

**Storage path:** `~/Library/Logs/prose_overlay_trail/last_command.json` — same directory as A. One file, overwritten via `tmp + os.replace()` atomicity.

**Keep criterion:** After a reproduced crash, `cat ~/Library/Logs/prose_overlay_trail/last_command.json` shows the utterance / action / args from the *most recent* attempt. Multiple consecutive non-crashing calls also leave the latest one visible. The file is never empty mid-flight.

**Kill criterion:** Either (a) the file contents don't match the dying call (write was buffered, lost, or written *after* the crash signal — meaning the atomicity model is wrong), or (b) the per-call write shows up as latency in hat reallocation (>5 ms added). If (a), upgrade to `os.fsync(fd)` after the rename and re-test; if that still fails, shelve. If (b), narrow to allocate-hats only and re-evaluate.

**Reversibility:**
- Run-time disable: same env var.
- Code revert: `git revert <slice-B-sha>` — diff is local to three files. Bridges return to their pre-slice-B form (one `try/except` around `_fn(...)`).
- Disk cleanup: `rm ~/Library/Logs/prose_overlay_trail/last_command.json`.

**Async-signal-safety claim:** Slice B writes happen *before* the risky call, not from a signal handler. Atomicity comes from POSIX `rename(2)` being atomic on the same filesystem. No AS-safe requirement applies here — this is a normal foreground write that has to be *durable* before the crash, not concurrent with it.

---

### Slice C — `events.ndjson` append log

**Prerequisite:** Slices A + B keep-criteria satisfied.

**Goal:** Learn whether a per-layer-transition append log adds useful narrative on top of A+B, *without* hurting hot-path latency. The dangling-`begin` pattern from [research §3.D](./STACK_OVERFLOW_PAPER_TRAIL.md#d-ndjson-event-log-opened-o_append) is the specific value claim under test.

**Files touched:**
- Modified: `prose_overlay_trail.py` (+~25 LOC — `_emit()` writing to an `O_APPEND` fd held open at module init, plus a `trace_js()` context manager)
- Modified: `prose_overlay_hats_js.py` (+~3 LOC — wrap `_fn(...)` in `trace_js("proseAllocateHats")` inside the existing `begin_command` / `end_command` bracket)
- Modified: `prose_overlay_targets_js.py` (+~3 LOC — same pattern with `trace_js("proseResolveTarget")`)

**Env-var gate:** Same `PROSE_OVERLAY_TRAIL=1`. *Additional* sub-gate `PROSE_OVERLAY_TRAIL_EVENTS=0` (default `1` when the parent gate is on) to disable just the event-log slice without touching A+B. This is the only place a sub-gate is justified, because C is the slice most likely to show measurable cost.

**Storage path:** `~/Library/Logs/prose_overlay_trail/events.ndjson` — `O_APPEND | O_WRONLY | O_CREAT`, mode `0o644`. Fd held open for process life (mirrors faulthandler's pattern). Lines are well under 4 KB so they're atomic w.r.t. signals per [open(2) `O_APPEND`](https://man7.org/linux/man-pages/man2/open.2.html) and [signal-safety(7)](https://man7.org/linux/man-pages/man7/signal-safety.7.html) (`os.write` is on the AS-safe list).

**Keep criterion:** Reproduce a crash. `tail -n 5 events.ndjson` shows a clean sequence `py:begin → js:begin → ...` with the trailing `js:end` *missing*. The dangling `begin` correctly names the layer that died. False-positive rate (an unmatched `begin` during normal use, no crash) is < 1% of utterances.

**Kill criterion:** Either (a) noise — every utterance produces an unmatched event because an exception path skipped `end_command`, making dangling-`begin` useless as a crash signal, or (b) cost — the per-call write shows up as >2 ms latency on the hat-reallocation hot path. If (a), tighten the `end_command` `finally` block. If (b), the slice is unjustified and we ship A+B only.

**Reversibility:**
- Run-time disable: `export PROSE_OVERLAY_TRAIL_EVENTS=0`. Keeps A+B running.
- Code revert: `git revert <slice-C-sha>`.
- Disk cleanup: `rm ~/Library/Logs/prose_overlay_trail/events.ndjson` — log rotates by truncation on every Talon start (see §4 on log rotation).

**Async-signal-safety claim:** `os.write(fd, bytes)` calls `write(2)` directly with no Python-level buffering; `write(2)` is on the [signal-safety(7) AS-safe list](https://man7.org/linux/man-pages/man7/signal-safety.7.html). `O_APPEND` makes the seek+write a single atomic kernel step per [open(2)](https://man7.org/linux/man-pages/man2/open.2.html). We do not call `_emit` from inside a signal handler in this slice — but if a future slice ever does (e.g. a custom SIGSEGV handler from us, not faulthandler), the call site is already AS-safe.

---

### Slice D — `dump_traceback_later` watchdog

**Prerequisite:** Slices A + B in. C is optional.

**Goal:** Learn whether the silent-hang case (infinite loop in QuickJS, not a signal) actually happens to us in normal use, and whether the watchdog catches it.

**Files touched:**
- Modified: `prose_overlay_trail.py` (+~10 LOC — `dump_traceback_later(N)` inside `begin_command`, `cancel_dump_traceback_later()` inside `end_command`)

**Env-var gate:** `PROSE_OVERLAY_TRAIL_WATCHDOG=0` default off — even when the parent gate is on, this one stays opt-in. Reason: a 5-second timer that fires from a non-crashed thread is the most likely slice to interact badly with Talon's main loop, and the "did we hang?" question is rare enough that running this without a need is pure cost.

**Storage path:** Same `faulthandler.log` as slice A — `dump_traceback_later` writes to the same fd faulthandler uses.

**Keep criterion:** A real hang the user actually hits leaves a dated thread-dump in `faulthandler.log` that names a useful frame (QuickJS C frame, or a JS bridge call site). At least one such event in N weeks of use.

**Kill criterion:** Either (a) no observed hang in 4 weeks → drop, no justification, or (b) false-positives swamp signal (timer fires on slow-but-fine paths like first JS context load), making the log noisy. If (b), raise the threshold (5s → 15s) and re-evaluate; if still noisy, drop.

**Reversibility:**
- Run-time disable: `unset PROSE_OVERLAY_TRAIL_WATCHDOG`.
- Code revert: `git revert <slice-D-sha>`.

**Async-signal-safety claim:** `dump_traceback_later` is documented AS-safe per the same [faulthandler docs](https://docs.python.org/3/library/faulthandler.html) as slice A. The dump fires from CPython's internal watchdog thread, not from a signal handler, so the AS-safety bar is actually lower — but the writes still go through the same AS-safe fd path so we don't lose the guarantee.

---

### Slice E — macOS DiagnosticReports correlation (env stamping)

**Prerequisite:** Slices A + B in. Independent of C, D.

**Goal:** Learn whether `os.environ["PROSE_CORR_ID"] = id` actually round-trips into the `.ips` crash report's env dump, so that a *fully native crash that bypasses faulthandler* can still be joined back to `last_command.json`.

**Files touched:**
- Modified: `prose_overlay_trail.py` (+~3 LOC — `os.environ["PROSE_CORR_ID"] = corr_id` inside `begin_command`)

**Env-var gate:** `PROSE_OVERLAY_TRAIL_ENVSTAMP=0` default off. Reason: writing to `os.environ` from inside a Talon plugin is a foundational poke — it mutates global process state. If anything downstream (Talon, another plugin) reads `os.environ` and is surprised by an opaque `PROSE_CORR_ID` key, we want to find that out at opt-in time, not silently.

**Storage path:** N/A — this slice doesn't write a file. It mutates `os.environ`. The artifact lands in `~/Library/Logs/DiagnosticReports/Talon-*.ips` if and when Talon crashes, written by macOS's `ReportCrash` daemon.

**Keep criterion:** A real (or intentionally reproduced) crash produces a `.ips` file in `~/Library/Logs/DiagnosticReports/`, and `grep PROSE_CORR_ID Talon-*.ips` returns the id that was current at crash time. Per [research §6 q3](./STACK_OVERFLOW_PAPER_TRAIL.md#6-open-questions-to-answer-before-implementing), this is a one-time smoke test.

**Kill criterion:** Env var doesn't appear in the `.ips` env dump (CPython doesn't actually call `setenv(3)` on macOS — it might just update `os.environ` the dict and never push to libc). If so, the slice provided zero value and is dropped. The cost of the slice was zero so there's nothing to undo beyond the revert.

**Reversibility:**
- Run-time disable: `unset PROSE_OVERLAY_TRAIL_ENVSTAMP`. The `os.environ` write only happens if the gate is set; a stale `PROSE_CORR_ID` from a previous session will persist until next Talon restart, which is fine.
- Code revert: `git revert <slice-E-sha>`.

**Async-signal-safety claim:** N/A — `os.environ` mutation happens in foreground code, before the risky call. The capture (the `.ips` write) is handled by macOS's `ReportCrash` daemon in a separate process.

## 4. Foundational risks to dodge

Things that, if done wrong, would be expensive to undo. Risk → cheap dodge.

**Path lock-in.** Hardcoding `~/.talon/...` mingles trail artifacts with Talon-owned state and the plugin's debug log; mingling implies a future "did this slice or `prose_overlay_debug.py` write that?" forensic problem.
- **Dodge:** Pick a fresh directory we own (`~/Library/Logs/prose_overlay_trail/`), create it on first import, never share it. Cleanup is one `rm -rf`.

**Hook lock-in (signal handlers).** Registering a SIGSEGV handler in a plugin that runs inside Talon could collide with Talon's own handlers. Slice A uses `faulthandler.enable(chain=True)` which is documented to call the previous handler after ours — but we don't *know* Talon has installed one to chain to, and we don't know if Talon's handler is well-behaved when chained from.
- **Dodge:** Per [research §6 q2](./STACK_OVERFLOW_PAPER_TRAIL.md#6-open-questions-to-answer-before-implementing), make this an explicit observation during slice A. If Talon's behavior changes (SIGINT no longer cleanly exits Talon, for instance), kill slice A immediately.
- **Dodge:** Never install a *custom* signal handler ourselves. faulthandler is C-level CPython code with documented AS-safety; our code stays Python-level only.

**File-write contention.** If two plugins (or two instances of this plugin) write to the same `events.ndjson`, the `O_APPEND` semantics still hold per-line, but interleaved output makes the dangling-`begin` heuristic unreliable.
- **Dodge:** Path is plugin-specific (`~/Library/Logs/prose_overlay_trail/`), not generic. If a future second writer ever lands, prefix events with `pid`.

**Log rotation / unbounded size.** `events.ndjson` (slice C) is append-only and grows forever. `faulthandler.log` (slice A) appends one block per crash, so it grows slowly — but `dump_traceback_later` (slice D) at a 5-second cadence could spam it if the watchdog mis-fires.
- **Dodge for C:** Truncate on Talon start (`open(..., "w").close()` at module import time, *before* opening the append fd). Loses cross-session history, which we don't need for the experiment. If we later decide cross-session matters, switch to a 10 MB rolling rename (`events.ndjson.1`, `.2`, etc.) — a future slice C.1.
- **Dodge for A/D:** Same truncate-on-start. Crash forensics are about "what just happened," not "what happened last week" — for the latter, the macOS `.ips` files are already kept by the OS.

**Coupling with `prose_overlay_debug.py`.** That module writes JSONL state-diffs to `~/.talon/prose_overlay_debug.jsonl`. It and the paper trail are *related* but answer different questions. `prose_overlay_debug.py` is "show me state transitions when I'm developing"; the paper trail is "tell me what died when I'm not." Forcing them to share a transport would mean either (a) the debug module starts writing AS-safe (overkill), or (b) the paper trail loses its AS-safety guarantees (unacceptable).
- **Dodge:** Keep them in separate files, separate directories, separate enable flags. Document the difference. A v2 unification — single transport, two consumers — is a question for *after* both modules have proven their value.

**Toggling state — flag sprawl.** Five env vars (`PROSE_OVERLAY_TRAIL`, `_EVENTS`, `_WATCHDOG`, `_ENVSTAMP`, …) is already a small DSL.
- **Dodge:** Parent gate `PROSE_OVERLAY_TRAIL` is required; sub-gates only exist for slices with measurable cost (C, D, E). Slices A and B share the parent gate. Document the variable list in the trail-dir `README.md` (auto-written on first init, single source of truth).

## 5. Integration touchpoints with in-flight work

**`prose_overlay_debug.py` — same-file vs. separate-file decision.** Separate. Three reasons: (1) debug is dev-time only (off in production usage), trail is production-time (off until something seems wrong); (2) debug writes from any state mutation, trail writes *only* from the JS bridge boundaries — the call sites barely overlap; (3) debug uses Python-buffered `open(..., "a")` writes which are NOT AS-safe, trail uses `os.write` on a raw fd which is. Composing them would mean rewriting debug to be AS-safe, which it doesn't need to be. The right composition layer is a *reader* tool: a future `scripts/triage.py` that joins both logs by timestamp. Out of scope here.

**`HAT_ALLOC_OVERFLOW_ANALYSIS.md` — does the paper trail catch that crash?** The analysis pinpoints the JS→Python `NewProxy` callback crossing as the overflow site, and notes that Option A (return-value pattern) is already shipped. So the *current* code doesn't reproduce the crash. To validate the paper trail, the reproduction step in slice A is: temporarily revert `prose_overlay_hats_js.py` to the `NewProxy` callback shape, run a phrase, and observe. If slice A's faulthandler captures a Python traceback whose topmost relevant frame is inside `talon.lib.js` or `prose_overlay_hats_js.py:88`, the keep-criterion is met. **The reverted state is reverted *back* immediately after the test** — Option A stays shipped. Note: per the analysis, the QuickJS-side overflow surfaces as a JS `InternalError: stack overflow` that propagates to Python as a normal exception — *not* a native SIGSEGV. If that's what happens here, slice A's faulthandler won't fire (no signal). Instead, the existing `try/except` in `compute_hat_assignments` (line 102) catches it. That changes the experiment: we want a *native* crash to validate faulthandler, and a QuickJS-throw to validate slice B+C. The reproduction recipe should include both — see §6 q1.

**`prose_overlay_hats_js.py` + `prose_overlay_targets_js.py` — bridge sites.** Both files have one risky call: `result_json: str = str(_fn(...))`. Both files already wrap that call in a `try/except`. Slice B wraps it with `begin_command` / `end_command`; slice C adds `trace_js(...)` inside. The bracket pattern is:

```python
corr_id = trail.begin_command(utterance, "allocate_hats", {"n_tokens": len(tokens)})
try:
    with trail.trace_js(corr_id, "proseAllocateHats"):
        result_json: str = str(_fn(...))
    trail.end_command(corr_id, ok=True)
except Exception as e:
    trail.end_command(corr_id, ok=False, err=repr(e))
    raise   # preserve existing fallback semantics; outer except still runs
```

The outer `try/except` in the bridge (the one that flips `_using_fallback = True`) is untouched. The wrapping is purely additive. If `trail` is disabled (env-var off), `begin_command` / `end_command` / `trace_js` are no-op stubs and the code reads as the unwrapped version did. (No-op stubs are exported from `prose_overlay_trail.py` unconditionally so the bridges don't grow an `if _TRAIL_ENABLED:` branch at every call site — that branch is foundational debt.)

**Utterance source.** `begin_command` takes an `utterance` argument. The bridges don't currently know the utterance — they're called from action handlers in `prose_overlay_actions_cursorless.py` that do know it. Two choices: (a) pass the utterance down (changes the bridge signatures — *foundational* — bad), or (b) record `utterance` once in the action handler via a thread-local, read in the bridge. Recommendation: **defer this question to slice B**, and in slice B start with `utterance=""` (empty) and the action name only. The "what utterance" question is decidable from `events.ndjson` timing + Talon's own log; we don't need the trail to be self-sufficient on day one.

## 6. Open questions for Trillium

1. **Should slice A's reproduction recipe try both crash modes?** A native SIGSEGV (which faulthandler catches) and a QuickJS `InternalError: stack overflow` (which propagates as a Python exception and does *not* fire faulthandler). If only the former, slice A is the validator. If both, slice A only validates against native; B+C are the validator against the JS-exception case. My read: cover both, because both are real failure modes from `HAT_ALLOC_OVERFLOW_ANALYSIS.md`.
2. **Are we willing to bounce Talon for the reproduction tests?** Forcing the overflow per the analysis recipe requires reverting Option A, restarting Talon (the bundle is loaded once at module init), running the phrase, then re-applying Option A and restarting again. ~5 minutes per cycle. If that's too disruptive, slice A's keep/kill decision waits until a crash happens organically — which the analysis suggests is unlikely now that Option A is in. That's the *good* case but it leaves the paper trail unvalidated.

---

*Plan ends. Slice A is one commit, one file, ten lines, one env var. Everything after it is conditional on what slice A teaches.*
