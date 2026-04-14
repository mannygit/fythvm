# Metaprogramming IR Builders

## Question

When is a small llvmlite helper worth the abstraction, and when does it start hiding
the control-flow shape you actually need to understand?

## Setup

This lab builds the same `clamp(x, 0, 10)` behavior two ways:

- a handwritten branch/phi sequence with explicit blocks
- a helper-driven version that reuses one thin `if / else / merge` utility twice

The helper is intentionally narrow. It removes repeated merge boilerplate, but it does
not become a framework or a codegen DSL.

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

The output prints one module containing both functions, then calls them with the same
inputs.

- The handwritten version makes the blocks and merge point explicit.
- The helper-driven version removes repeated `cbranch` / `phi` boilerplate.
- The helper-driven version also turns the clamp into nested binary decisions, so the
  emitted IR is less immediately obvious than the handwritten shape.

That is the useful boundary: one thin helper is good when it shortens repetitive block
plumbing, but composition starts to hide the CFG shape you may need while debugging.

## Pattern / Takeaway

Bless one small helper around a repeated IR pattern, not a broad abstraction layer.

For this case, the right helper is a very small `if / else / merge` builder:

- take a condition
- emit then / else / merge blocks
- return the merged value

That keeps codegen terse without making the builder graph disappear.

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

## Apply When

Use this pattern when:

- you are repeating the same small branch/phi idiom several times
- the emitted CFG is still simple enough that one helper call does not obscure it
- you want to keep exploratory code shorter without losing all visibility into the IR

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
