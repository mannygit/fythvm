# llvmlite IR inspection tooling

## Question

How do you inspect and compare llvmlite IR without hiding the emitted LLVM?

## Setup

This lab builds two tiny modules with the same function shape but different global
initializers. It demonstrates the pattern twice: once in a raw IR-like style and once
through a small helper object.

- capture the raw `str(module)` output immediately and keep that snapshot
- diff the raw LLVM text, with line numbers as a reader aid rather than a substitute
- bundle the repeated capture/render steps in a helper object without hiding the raw
  LLVM text

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

- a raw variant that spells out snapshot and diff plumbing directly
- a Pythonic variant that uses a helper object to group capture and rendering
- the raw LLVM IR for each snapshot
- a line-numbered view of the same IR for quick reading
- a unified diff of the captured raw text
- a comparison that confirms both variants saw the same inputs and produced the same
  IR text
- the function body and global initializer remain visible instead of getting reduced to
  a summary

In the demo, the function body stays the same while the `bias_seed` global changes.
That makes the important point obvious: some meaningful IR changes live in globals or
attributes, not just in the obvious function body.

The Pythonic helper keeps the same raw data visible. It only packages the repeated
capture and render steps so the code reads more like a small inspection workflow than a
pile of one-off print statements.

## Pattern / Takeaway

Use one helper to freeze the exact IR text and one helper to diff that text later.
Keep any annotation layer thin and additive. The LLVM should stay visible, not get
translated into a different representation before you can inspect it.

The raw variant is the source of truth. The helper-object version is a convenience
layer that should remain easy to compare against the baseline.

## Non-Obvious Failure Modes

The easy mistake is to treat IR inspection as a summary problem instead of a snapshot
problem.

If you stringify too late, earlier variants are gone. If you compare only headers or
only a function summary, you can miss important differences like a changed global
initializer. If the helper normalizes too aggressively, it can hide the very thing you
were trying to investigate.

Another easy mistake is to let the helper become the only thing you trust. If the raw
LLVM text is not still obvious in the output, the inspection layer has gone too far.

## Apply When

Use this pattern when you are:

- iterating on a small codegen change and need to compare variants
- debugging a change in globals, attributes, or instruction ordering
- trying to keep raw LLVM visible while still making comparisons readable
- wrapping repeated inspection steps in a helper object that still leaves the raw IR
  visible

## Avoid When

Do not replace semantic analysis with text diffing when you actually need an IR pass
or verifier-level answer.

Avoid turning the helper into a big reporting layer. Once the abstraction starts to
obscure the LLVM, it stops being useful for experiments.

Do not replace the raw variant with the helper variant. The helper should stay
obviously thinner than the source-of-truth path.

## Next Questions

- When is a structural IR summary useful, and when does it become misleading?
- Would a side-by-side view add value for larger modules, or is a raw diff enough?
- Which extra annotations are worth keeping if the module becomes much larger?
- Should the helper object grow into a shared exploration utility, or stay local to
  this lab?
