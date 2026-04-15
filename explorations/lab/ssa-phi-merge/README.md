# SSA Phi Merge

## Question

How does a value-producing conditional, including a ternary-like shape, lower into LLVM SSA?

## Setup

This lab builds two tiny `i64 -> i64` functions with llvmlite:

- `branch_merge`, the raw source-of-truth version that chooses between two values on
  different control-flow edges and joins them with a `phi`
- `branch_merge_pythonic`, which uses a tiny local helper to reduce block-positioning
  noise while keeping the same `then` / `else` / `merge` shape visible
- `select_merge`, which uses `select` because both candidate values are safe to compute
  eagerly in straight line

It also builds a deliberately broken merge example that reuses the branch-local value
without a `phi`, then shows the LLVM verifier error.

The source-level shape is intentionally small because the concept is small:

```c
long branch_merge(long x) {
    return x >= 0 ? x + 10 : x - 10;
}
```

The raw branch/merge form in the lab is the explicit CFG lowering of that value
conditional.

The SSA-ish lowering is the point of the lab:

```text
entry:
  is_non_negative = x >= 0
  br is_non_negative, then, else

then:
  then_value = x + 10
  br merge

else:
  else_value = x - 10
  br merge

merge:
  merged = phi [then_value, then], [else_value, else]
  ret merged
```

## How to Run

```bash
uv run python explorations/lab/ssa-phi-merge/run.py
```

## What It Shows

The output is labeled so you can compare three cases:

- the generated IR for the raw and Pythonic branch/merge functions
- runtime results for `branch_merge`, `branch_merge_pythonic`, and `select_merge` on
  the same inputs
- a verifier failure for the broken attempt that tries to use a branch-local value in
  the merge block without a `phi`

The contrast matters. This lab is fundamentally about a ternary-sized conditional
expression. `select` is the straight-line lowering when both candidate values are safe
to compute eagerly. The raw and Pythonic branch/merge versions show the explicit CFG
lowering of the same idea, where the merge block needs a `phi` to choose the value that
actually came from the taken edge.

The Pythonic variant does not hide the CFG. It only removes the repetitive
`position_at_end` / `branch` bookkeeping that the raw version spells out manually. That
thinness is part of the lab's point. This is a low-level conditional-lowering example,
so the Pythonic layer should stay close to the IR.

For the grown-up version of this idea, see
`explorations/lab/block-parameter-joins/`. That lab treats the merge block as if it
took block arguments and shows how LLVM lowers those arguments into phis.

## Pattern / Takeaway

Use `phi` when a value is defined along multiple incoming control-flow paths and the
merge block needs one runtime value chosen by predecessor.

Use `select` only when the choice is purely between already-safe values and you do not
need a control-flow join.

In a lab this small, a Pythonic builder style should stay thin. A tiny local helper can
remove block-plumbing noise, but the raw version remains the source of truth because the
main lesson is the lowering itself.

This lab is the baby case of the more general block-parameter model: one merged value,
two predecessor edges, one join block.

## Non-Obvious Failure Modes

The easiest mistake is to treat a Python variable name as if it were runtime SSA state.
Rebinding `then_value` or `else_value` in host code does not create a merged runtime
value. It only changes which llvmlite object your script is holding.

Another easy mistake is to let a helper hide the predecessor edges. A context manager
can make the code shorter, but it does not change the SSA rule: the merge block still
needs the actual incoming blocks and values.

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
