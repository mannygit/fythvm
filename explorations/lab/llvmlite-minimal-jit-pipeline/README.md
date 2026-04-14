# Minimal llvmlite JIT pipeline

## Question

What is the smallest complete llvmlite shape that goes from generated IR to a
callable native function?

## Setup

This lab builds a tiny `add(i64, i64) -> i64` function with `llvmlite.ir`,
verifies the module with LLVM bindings, creates a target machine and MCJIT engine,
and then calls the compiled function via `ctypes`.

## How to Run

```bash
uv run python explorations/lab/llvmlite-minimal-jit-pipeline/run.py
```

Local macOS or Windows development should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/llvmlite-minimal-jit-pipeline/run.py
```

## What It Shows

The output is intentionally labeled:

- the target triple currently selected by LLVM
- the generated LLVM IR for the `add` function
- the compiled function pointer address
- a couple of example calls and their results

That makes the full JIT pipeline visible in one place instead of hiding the important
steps behind a helper.

## Pattern / Takeaway

For exploratory llvmlite work, start from a full end-to-end path:

1. build IR
2. initialize the native target and asm printer
3. parse and verify the module
4. create a target machine and execution engine
5. get the function address and call it

That baseline keeps the control flow obvious and gives later labs a stable shape to
modify one concern at a time.

## Non-Obvious Failure Modes

Keep the `ExecutionEngine` alive until after you finish calling any function pointers
you obtained from it.

This is the kind of failure that is easy to hit even when the code looks reasonable:
you can extract an integer function address, drop the last Python reference to the
engine, and still successfully build a `ctypes` callable from that address. The code
looks valid, but the underlying JIT-owned code is no longer safely kept alive, which
can lead to a segfault at call time.

That is not a syntax problem or an obvious "wrong method" error. It is a lifetime
misunderstanding, and exactly the sort of learned-by-doing trap this explorations
area should preserve.

## Apply When

Use this pattern when:

- you need a minimal known-good starting point for a new llvmlite experiment
- you want to inspect the emitted IR before adding more complexity
- you are debugging whether a problem is in IR construction or in a later JIT step

## Avoid When

Do not treat this as the final structure for production codegen. It is intentionally
verbose and explicit so the pipeline is visible. Once a pattern is proven, package
code may justify better abstraction boundaries.

It also does not model control-flow joins, phi nodes, memory management concerns, or
multi-function modules.

## Next Questions

- How should this baseline change once control flow introduces phi nodes?
- Which parts of engine setup deserve a reusable helper versus staying explicit?
- What is the best way to print or diff IR as experiments become more complex?
