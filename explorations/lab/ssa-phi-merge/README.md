# SSA Phi Merge

## Question

When does a control-flow merge need a phi node instead of a straight-line expression?

## Setup

This lab builds two tiny `i64 -> i64` functions with llvmlite:

- `branch_merge`, which chooses between two values on different control-flow edges and
  joins them with a `phi`
- `select_merge`, which uses `select` because both candidate values are safe to compute
  eagerly in straight line

It also builds a deliberately broken merge example that reuses the branch-local value
without a `phi`, then shows the LLVM verifier error.

## How to Run

```bash
uv run python explorations/lab/ssa-phi-merge/run.py
```

## What It Shows

The output is labeled so you can compare three cases:

- the generated IR for the real branch/merge example
- runtime results for `branch_merge` and `select_merge` on the same inputs
- a verifier failure for the broken attempt that tries to use a branch-local value in
  the merge block without a `phi`

The contrast matters. `select` is not a substitute for `phi` in general. It is only a
good fit when both candidate values can be evaluated unconditionally. When each branch
computes a different runtime result, the merge block needs a `phi` to select the value
that actually came from the taken edge.

## Pattern / Takeaway

Use `phi` when a value is defined along multiple incoming control-flow paths and the
merge block needs one runtime value chosen by predecessor.

Use `select` only when the choice is purely between already-safe values and you do not
need a control-flow join.

## Non-Obvious Failure Modes

The easiest mistake is to treat a Python variable name as if it were runtime SSA state.
Rebinding `then_value` or `else_value` in host code does not create a merged runtime
value. It only changes which llvmlite object your script is holding.

Another common mistake is to think textual block order matters more than it does.
LLVM cares about the actual predecessor edges and the incoming block/value pairing on
the `phi`, not about where the blocks happen to appear in the printed IR.

The incoming values on a `phi` must line up with the real edges entering that block.
If you pair a value with the wrong predecessor, or skip the `phi` entirely and try to
use a branch-local value in the merge block, the verifier rejects the module.

## Apply When

Use this pattern when:

- a value is produced on one of several control-flow paths and must survive the join
- you are lowering a high-level `if` expression into SSA form
- you want a minimal example of how branch-local values become merge-block values

## Avoid When

Do not use `phi` if the logic is already a straight-line choice with no control-flow
join. In that case `select` is simpler and easier to read.

Do not use `phi` as a workaround for unclear dataflow. If the real problem is mutable
state, a stack slot or explicit memory location may be the better abstraction. If the
real problem is a join in SSA, a `phi` is the correct tool.

## Next Questions

- How does this pattern change once the branch computes pointer-typed values or
  aggregates?
- When is `select` still preferable once the branch bodies get larger?
- What are the cleanest ways to generate phi-heavy IR from a higher-level AST?
