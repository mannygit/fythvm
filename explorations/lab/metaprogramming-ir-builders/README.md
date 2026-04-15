# Metaprogramming IR Builders

## Question

When is a small llvmlite helper worth the abstraction, and when does it start hiding
the control-flow shape or the compare-lowering shape you actually need to understand?

## Setup

This lab builds two small IR shapes two ways:

- `clamp(x, 0, 10)` using a raw branch/phi sequence and a Pythonic branch helper
- a three-way `classify_score(x)` lowering using explicit `icmp` + `select` and a
  Pythonic compare-lowering helper

The raw versions are the source of truth. The Pythonic versions are the readable layer
that keeps the same behavior but reduces repetition where it actually helps.

The helpers are intentionally narrow. They remove repeated merge or comparison boilerplate,
but they do not become a framework or a codegen DSL. The raw baselines still own correctness.

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
- The raw comparison example lowers repeated threshold checks with explicit `icmp`
  and `select` instructions, so the straight-line decision shape stays visible.
- The Pythonic branch example removes repeated `cbranch` / `phi` boilerplate through a
  tiny `BranchMerge` helper with `with ...` blocks for each branch.
- The Pythonic comparison example removes repeated threshold-check boilerplate through
  a tiny `ComparisonLowering` helper that still emits `icmp` plus `select`.

That is the useful boundary: one thin helper is good when it shortens repetitive block
or compare plumbing, but composition starts to hide either the CFG shape or the
lowering shape you may need while debugging.

## Pattern / Takeaway

Keep the raw IR-like version as the canonical reference, then layer on one small helper
only when it makes the same shape easier to read.

For this case, the right helpers are:

- a very small `if / else / merge` builder for branch/phi repetition
- a small comparison-lowering helper that takes a threshold and returns a `select`
  result from `icmp`

That keeps codegen terse without making the builder graph or the straight-line
comparison shape disappear. If a helper ever stops exposing the structure it wraps,
it has gone too far.

## Non-Obvious Failure Modes

The main trap is not syntax. It is mental model drift.

- A helper that looks harmless in Python can change the emitted CFG shape by nesting
  branches and merge blocks.
- A helper that lowers comparisons can be mistaken for a branch-prediction hint even
  though it is just straight-line SSA lowering with `icmp` and `select`.
- If the compare helper hides the threshold or the selected value, readers lose the
  ability to see which decision is being encoded.
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
- you are repeating the same small compare-lowering idiom several times
- the emitted CFG is still simple enough that one helper call does not obscure it
- you want to keep exploratory code shorter without losing visibility into the IR
- you want the raw builder sequence to remain the correctness baseline while the helper
  evolves only where it is obviously helping readability

## Avoid When

Do not use this style when:

- the helper becomes a general codegen framework
- the real question is about CFG shape, dominance, or merge placement
- the real question is about branch prediction instead of IR lowering
- a future reader needs the raw block sequence to understand the experiment

## Next Questions

- How far can this helper pattern go before it stops being readable?
- Would a `select`-based form be clearer for some other straight-line comparison cases?
- Which repeated builder shapes deserve helpers in this repo, and which should stay
  handwritten?
