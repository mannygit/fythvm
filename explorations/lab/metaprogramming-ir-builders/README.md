# Metaprogramming IR Builders

## Question

When is a small llvmlite helper worth the abstraction, and when does it start hiding
the control-flow shape you actually need to understand?

## Setup

This lab builds the same `clamp(x, 0, 10)` behavior two ways:

- a raw branch/phi sequence with explicit blocks, which is the source of truth
- a Pythonic version that wraps the repeated wiring in a tiny context-managed helper

The helper is intentionally narrow. It removes repeated merge boilerplate, but it does
not become a framework or a codegen DSL. The raw baseline still owns correctness.

## How to Run

```bash
uv run python explorations/lab/metaprogramming-ir-builders/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/metaprogramming-ir-builders/run.py
```

## What It Shows

The output prints the raw baseline and the Pythonic variant side by side, then calls
them with the same inputs.

- The raw version makes every block, branch, and phi input explicit.
- The Pythonic version removes repeated `cbranch` / `phi` boilerplate through a tiny
  `BranchMerge` helper with `with ...` blocks for each branch.
- Both versions keep the CFG visible enough to inspect dominance and merge behavior,
  but the Pythonic version reads more like structured Python than block bookkeeping.

That is the useful boundary: one thin helper is good when it shortens repetitive block
plumbing, but composition starts to hide the CFG shape you may need while debugging.

## Pattern / Takeaway

Keep the raw IR-like version as the canonical reference, then layer on one small helper
only when it makes the same shape easier to read.

For this case, the right helper is a very small `if / else / merge` builder:

- take a condition
- emit then / else / merge blocks
- return the merged value

That keeps codegen terse without making the builder graph disappear. If the helper ever
stops exposing the merge structure, it has gone too far.

## Non-Obvious Failure Modes

The main trap is not syntax. It is mental model drift.

- A helper that looks harmless in Python can change the emitted CFG shape by nesting
  branches and merge blocks.
- Once the helper is reused several levels deep, debugging block names and dominance
  becomes harder because the structure is now encoded in helper calls instead of the
  visible builder sequence.
- Python-level reuse can make two code paths look “the same” even though they now emit
  different IR layouts, which matters when you are chasing verifier issues or trying to
  understand why a branch is dominated the way it is.
- If the helper stops naming or exposing its branch blocks, the Pythonic version stops
  being a readable wrapper and becomes a new abstraction layer to debug.

## Apply When

Use this pattern when:

- you are repeating the same small branch/phi idiom several times
- the emitted CFG is still simple enough that one helper call does not obscure it
- you want to keep exploratory code shorter without losing visibility into the IR
- you want the raw builder sequence to remain the correctness baseline while the helper
  evolves only where it is obviously helping readability

## Avoid When

Do not use this style when:

- the helper becomes a general codegen framework
- the real question is about CFG shape, dominance, or merge placement
- a future reader needs the raw block sequence to understand the experiment

## Next Questions

- How far can this helper pattern go before it stops being readable?
- Would a `select`-based form be clearer for some straight-line cases?
- Which repeated builder shapes deserve helpers in this repo, and which should stay
  handwritten?
