# llvmlite IR inspection tooling

## Question

How do you inspect and compare llvmlite IR without hiding the emitted LLVM?

## Setup

This lab builds two tiny modules with the same function shape but different global
initializers. It demonstrates two practical helper patterns:

- capture the raw `str(module)` output immediately and keep that snapshot
- diff the raw LLVM text, with line numbers as a reader aid rather than a substitute

The point is not to build a pretty report generator. The point is to preserve the
actual LLVM while making variant-to-variant comparison easy enough to use during
experimentation.

## How to Run

```bash
uv run python explorations/lab/ir-inspection-tooling/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/ir-inspection-tooling/run.py
```

## What It Shows

The script prints:

- a snapshot summary for each module variant
- the raw LLVM IR for each snapshot
- a line-numbered view of the same IR for quick reading
- a unified diff of the captured raw text

In the demo, the function body stays the same while the `bias_seed` global changes.
That makes the important point obvious: some meaningful IR changes live in globals or
attributes, not just in the obvious function body.

## Pattern / Takeaway

Use one helper to freeze the exact IR text and one helper to diff that text later.
Keep any annotation layer thin and additive. The LLVM should stay visible, not get
translated into a different representation before you can inspect it.

## Non-Obvious Failure Modes

The easy mistake is to treat IR inspection as a summary problem instead of a snapshot
problem.

If you stringify too late, earlier variants are gone. If you compare only headers or
only a function summary, you can miss important differences like a changed global
initializer. If the helper normalizes too aggressively, it can hide the very thing you
were trying to investigate.

## Apply When

Use this pattern when you are:

- iterating on a small codegen change and need to compare variants
- debugging a change in globals, attributes, or instruction ordering
- trying to keep raw LLVM visible while still making comparisons readable

## Avoid When

Do not replace semantic analysis with text diffing when you actually need an IR pass
or verifier-level answer.

Avoid turning the helper into a big reporting layer. Once the abstraction starts to
obscure the LLVM, it stops being useful for experiments.

## Next Questions

- When is a structural IR summary useful, and when does it become misleading?
- Would a side-by-side view add value for larger modules, or is a raw diff enough?
- Which extra annotations are worth keeping if the module becomes much larger?
