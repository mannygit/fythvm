# ctypes Dictionary Runtime

## Question

What does a pure Python + `ctypes` dictionary runtime look like once the fixed runtime
records and the variable word-entry protocol are combined?

## Setup

This lab uses the real package-level runtime in
[dictionary.py](/Users/manny/fythvm/src/fythvm/dictionary.py:1). It does not JIT
anything. The point is debug visibility:

- real Python `ctypes` classes
- real append-only word creation
- real newest-first traversal
- real hidden-word lookup skipping

This is intentionally the Pythonic consumer end of the earlier labs, not a new raw
source-of-truth emitter.

## How to Run

```bash
uv run python explorations/lab/ctypes-dictionary-runtime/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/ctypes-dictionary-runtime/run.py
```

## What It Shows

The run prints:

- the actual Python source for the key `ctypes` classes and the runtime object
- a live dictionary with created words
- newest-first traversal
- lookup traces that skip hidden words
- the runtime’s own debug snapshot

## Pattern / Takeaway

A pure Python + `ctypes` runtime is valuable even before execution exists. It makes
the memory shape, offsets, and lookup rules inspectable in a way that is cheap to run
and easy to debug.

## Non-Obvious Failure Modes

One easy mistake is assuming a debug-visible Python runtime is "just a toy" and can
freely diverge from the real planned layout. That removes most of the value. The
useful version is the one that preserves the actual fixed-record and variable-entry
protocol.

Another easy mistake is treating `immediate`, `compiling`, and `hidden` as having the
same role. In this prototype, `hidden` affects lookup; the others are preserved as
metadata only.

## Apply When

- you want to debug dictionary layout and lookup without involving execution
- you want a visibility-friendly reference runtime next to future JIT work
- you need concrete Python objects to inspect while refining the memory protocol

## Avoid When

- you need to execute words or compile code into the dictionary already
- you need a final optimized runtime instead of a debug-visible prototype
- you want to treat this as a replacement for the lower-level layout labs

## Next Questions

- What is the first execution path worth layering on top of this runtime?
- Which parts of the runtime should stay pure Python for visibility even after JIT
  machinery arrives?
- Should the package eventually expose a richer structured trace for lookup and word
  creation steps?
