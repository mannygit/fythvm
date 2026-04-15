# llvmlite mem intrinsics

## Question

How do you wire LLVM's `memcpy`, `memmove`, and `memset` intrinsics in llvmlite when
`IRBuilder` does not expose convenience helpers for them?

## Setup

This lab builds one small JIT module with three exported functions:

- `copy_bytes(dst, src, count)` using `llvm.memcpy`
- `move_bytes(dst, src, count)` using `llvm.memmove`
- `fill_bytes(dst, byte_value, count)` using `llvm.memset`

The lab stays deliberately raw. There is no Pythonic companion variant because the
useful thing to preserve is the exact API shape:

- declare the intrinsic with `module.declare_intrinsic(...)`
- call it like any other function
- pass the trailing `i1 isvolatile` argument explicitly

The host harness uses `ctypes` buffers so the before/after byte patterns are visible
alongside the emitted LLVM IR.

For the hand-built contrast case, see
[musttail-chunked-memory-ops](/Users/manny/fythvm/explorations/lab/musttail-chunked-memory-ops/README.md:1),
which explores explicit chunked copy and compare lowering instead of LLVM's built-in
memory intrinsics.

## How to Run

```bash
uv run python explorations/lab/llvmlite-mem-intrinsics/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/llvmlite-mem-intrinsics/run.py
```

## What It Shows

The output prints:

- the emitted LLVM IR, including the declared intrinsic names
- a `memcpy` example copying between disjoint buffers
- a `memmove` example over overlapping regions in one buffer
- a `memset` example filling a byte range with a fixed value

That makes both the declaration pattern and the runtime behavior concrete.

## Pattern / Takeaway

Current llvmlite supports LLVM `mem*` intrinsics through `Module.declare_intrinsic`,
not through `IRBuilder.memcpy()` / `memmove()` / `memset()` helpers.

The reusable pattern is:

1. choose the overloaded pointer and count types
2. declare the intrinsic explicitly
3. emit a normal call
4. pass the trailing `i1 isvolatile` argument yourself

Once that is clear, the intrinsic calls are not magical. They are just ordinary
call-sites with a slightly awkward declaration step.

## Non-Obvious Failure Modes

The first trap is assuming `IRBuilder` has convenience helpers for the memory
intrinsics. In the installed llvmlite used by this repo, it does not.

The second trap is forgetting that `declare_intrinsic(...)` and the actual call have
different arities. For `memcpy` and `memmove`, the declaration is driven by three
overload types, but the call still needs a fourth `i1 isvolatile` argument. `memset`
is similar: two overload types, then four runtime arguments.

Another easy mistake is thinking `memcpy` and `memmove` are interchangeable because
their signatures look the same. The overlap example exists to keep that difference
visible.

## Apply When

Use this pattern when:

- you want LLVM's built-in memory intrinsics instead of hand-rolled loops
- you need to emit copy, move, or fill operations directly in llvmlite
- you want a minimal demonstration of the exact declaration and call shape

## Avoid When

Do not use this lab as a full memory-runtime design. It is only about wiring the
intrinsic calls.

Avoid treating this as proof that LLVM intrinsics are always the right answer. If the
interesting part of the experiment is control flow, chunking, tail calls, tracing, or
alignment policy, a hand-built lowering may still be the better teaching shape.

## Next Questions

- Should a follow-up lab contrast these intrinsics against hand-built copy loops?
- What is the cleanest way to demonstrate alignment attributes or `isvolatile=1`?
- When should a future exploration prefer `llvm.memmove` over a custom overlapping
  copy loop?
