# Chunked musttail memory ops

## Question

How do you build a tail-recursive copy or compare helper in llvmlite that peels
memory in 8-byte, 4-byte, then 1-byte chunks without losing verifier safety?

## Setup

This lab builds two small JIT functions:

- `chunked_copy(dst, src, count, trace, trace_index) -> void`
- `chunked_compare(left, right, count, trace, trace_index) -> i32`

Both functions recurse on themselves with `musttail` after handling the largest
available chunk. The same control-flow shape is used for both:

1. check for `count == 0`
2. try an 8-byte chunk
3. try a 4-byte chunk
4. fall back to a 1-byte chunk

Each step writes the chosen chunk size into a trace buffer so the runtime output can
show which path was taken.

## How to Run

```bash
uv run python explorations/lab/musttail-chunked-memory-ops/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/musttail-chunked-memory-ops/run.py
```

## What It Shows

The output prints:

- the generated LLVM IR for the working functions
- the chunk plan recorded at runtime for a compare call and a copy call
- the compare result for equal and mismatched inputs
- a verifier error for a deliberately broken `musttail` shape

That makes the recursion policy visible in both the IR and the observed behavior.

## Pattern / Takeaway

Use `musttail` only when the recursive call is the final action in the block and the
caller/callee signature is kept compatible across every recursive step. For this kind
of memory peeler, the recursive call is not an optimization hint; it is part of the
contract.

## Non-Obvious Failure Modes

The easy mistakes here are mental-model mistakes, not syntax mistakes:

- assuming LLVM will "just" optimize a recursive call into a tail call later
- putting any instruction after a `musttail` call, even a harmless-looking one
- changing the signature between recursive steps so the tail-call shape is no longer
  compatible
- treating 8-byte and 4-byte loads as automatically safe on any pointer without
  thinking about alignment

The lab includes a broken-shape verifier failure so this constraint stays explicit.

## Apply When

Use this pattern when:

- you want a simple, explicit chunked memory operation in LLVM IR
- you need predictable tail-recursive control flow instead of a loop builder
- you are experimenting with low-level copy or compare helpers that naturally peel in
  fixed-size chunks

## Avoid When

Do not use this shape if:

- the recursive structure is only there because it looks clever
- you need a general-purpose memmove/memcmp replacement for arbitrary pointers and
  unaligned addresses
- the tail-call legality is not something you are prepared to keep exact

## Next Questions

- Should a future lab compare this shape against a plain loop-based lowering?
- Is there a safe generalized version that handles unaligned heads and tails before
  the chunked tail recursion starts?
- Which memory operations are best expressed as `musttail` recursion versus loops?
