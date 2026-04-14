# Quarantined MCJIT global ctor/dtor negative control

## Question

What does the unsupported MCJIT global ctor/dtor path look like, and how can we
document it without turning normal runs into a crash hazard?

## Setup

This lab builds a small llvmlite module that intentionally emits both
`llvm.global_ctors` and `llvm.global_dtors`.

The module also exports ordinary reader functions so the safe path can prove the IR
shape without attempting to execute the risky loader-style hooks. The unsafe runtime
path is only reachable through an explicit child-process opt-in.

## How to Run

```bash
uv run python explorations/lab/mcjit-global-ctor-dtor-negative-control/run.py
```

The default run is safe and only inspects the emitted IR.

If you want to quarantine the unsupported runtime path and observe what happens in
an isolated child process, use:

```bash
uv run python explorations/lab/mcjit-global-ctor-dtor-negative-control/run.py --attempt-unsafe-path
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/mcjit-global-ctor-dtor-negative-control/run.py
```

## What It Shows

The default output shows:

- the host LLVM target triple
- emitted IR containing both `llvm.global_ctors` and `llvm.global_dtors`
- safe zero-valued counters read back from the JITed module
- a clear statement that no ctor/dtor execution was attempted in the parent process

The opt-in child-process path shows the quarantined execution attempt separately.
On macOS, a nonzero exit or signal termination is the expected-failure shape for this
negative control, not a lab bug.

## Pattern / Takeaway

Treat risky platform-specific behavior as evidence to preserve, not a normal runtime
recipe:

1. emit the unsupported shape clearly
2. prove the safe observation path in the parent process
3. isolate any runtime attempt in a subprocess
4. treat failure on macOS as part of the lesson, not as a crash in the main lab

That keeps the negative control useful without making routine lab runs dangerous.

## Non-Obvious Failure Modes

It is easy to confuse "the docs mention this API" with "this path is safe to use."
That is exactly the trap this lab is designed to record. `run_static_constructors()`
and `run_static_destructors()` are exposed by llvmlite, but the presence of the API
does not mean the ctor/dtor path is a good idea on MCJIT/Mach-O.

Another easy mistake is assuming the ctor/dtor arrays behave like normal loader
callbacks on every platform. They do not. This lab exists because the macOS path is
the risky one, and the failure mode can be a crash rather than a clean Python
exception.

Do not let a negative-control note become a production instruction. If the lab is
read later, the point should still be "this path is unsupported and quarantined," not
"here is how to wire up ctors/dtors in real code."

Finally, keep the child-process boundary intact. If the unsupported path is ever run
inline in the parent process, the lab stops being a safe negative control and becomes a
crash hazard again.

## Apply When

Use this pattern when you need to preserve a risky or unsupported behavior as a
documented counterexample:

- a platform-specific JIT path is known to be problematic
- you want to prove the shape of the IR without endorsing the runtime behavior
- a future engineer needs a quarantined reproducer or expected-failure reference

## Avoid When

Do not use this pattern for normal runtime codegen or for a path you intend to rely
on in production.

Avoid running the opt-in child process unless you specifically want to observe the
unsupported behavior in isolation. The default lab output is the safe, preferred
documentation path.

## Next Questions

- Should there be a sibling positive-control lab that shows the explicit lifecycle
  replacement on the same host?
- What is the smallest reproducible macOS-only symptom worth preserving if the
  quarantined child path fails differently on another llvmlite release?
- Should this negative control eventually become a regression test fixture, or stay as
  a human-readable exploration only?
