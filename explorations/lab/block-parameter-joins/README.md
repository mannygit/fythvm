# Block Parameter Joins

## Question

What is the general mental model behind phis once a control-flow merge carries more
than one live value?

## Setup

This lab treats phis as lowered block parameters instead of as one-off merge hacks.
It builds four small llvmlite functions:

- `select_merge`, the expression-level degenerate case where one condition chooses one
  scalar value in the same block with `select`
- `zero_live_in_join_raw` and `zero_live_in_join_pythonic`, a branch/join shape with
  multiple predecessors but no merged live-in values
- `tuple_join_raw` and `tuple_join_pythonic`, which merge three live values
  (`x`, `y`, `tos`) through one join block
- `state_join_pythonic`, the same three-value join but wrapped as a named state object

The raw tuple join is the source of truth. The Pythonic variants exist to express the
real reusable abstraction: successor blocks conceptually take an argument tuple, and
LLVM spells those block parameters as phis at block entry.

## How to Run

```bash
uv run python explorations/lab/block-parameter-joins/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/block-parameter-joins/run.py
```

## What It Shows

The output prints:

- the generated IR for the select case, the zero-live-in join, and the tuple/state joins
- runtime results for the raw and Pythonic tuple/state joins on the same inputs
- a short case summary explaining which functions have no join, which have a join with
  zero block parameters, and which have a join with three block parameters

The important contrast is structural:

- `select_merge` has no join block at all; it is a same-block value mux
- `zero_live_in_join_raw` and `zero_live_in_join_pythonic` still have a real CFG join,
  but there are no per-edge values to thread through it
- the tuple/state joins have one real merge block whose entry state depends on the
  predecessor edge, so the block entry must reconstruct that state with one phi per
  live-in

The tuple-style Pythonic variant shows the block-parameter mental model directly:
`with Join(...) as (x, y, tos): ...`

The named-state variant shows why this matters once the merged values start looking
like machine or interpreter state: `state.x`, `state.y`, `state.tos` are still just
block-entry values, but the host-side code can talk about them as one environment.

The refined Pythonic step is `branch_from_here(...)`: predecessor code computes an
outgoing environment and transfers control to the successor carrying that state, rather
than manually capturing the predecessor block, branching, and then calling
`add_incoming(...)` as a separate action.

`in_block(...)` now yields the active block when the calling code needs it, and the
lab also uses a tiny create-and-enter helper for the immediate-use case where a block
does not need to exist as a forward branch target before emission begins.

## Pattern / Takeaway

The general pattern is not "a ternary with a phi." The general pattern is: blocks
conceptually take arguments, predecessors supply those arguments on outgoing edges, and
LLVM lowers those block parameters into phis at block entry.

That gives one reusable model for several shapes:

- `select`: no CFG join, just value selection
- plain merge block: CFG join with zero block parameters, which the same `Join` helper
  can model with an empty parameter list
- `if`/`else` merge: CFG join with one or more block parameters
- loop header: a self-join where the backedge contributes the next iteration state

The tuple-style `Join` helper is the canonical abstraction because it stays close to
raw SSA. A named-state wrapper becomes useful once the merged values represent a real
environment such as interpreter state.

The next layer above `add_incoming(...)` is edge/state transfer. The useful semantic
operation is "branch to this successor carrying this environment," and
`branch_from_here(...)` expresses exactly that without turning the lab into a CFG DSL.

The block-entry helpers are intentionally narrower. They improve readability for
"create this block and start emitting in it now" or "enter this already-declared
block," but they do not replace explicit predeclaration of branch targets.

## Non-Obvious Failure Modes

The easiest mistake is to confuse predecessor-edge values with block-entry values. The
values computed in the predecessor blocks are not the same thing as the phis in the
join block. The predecessor values are the arguments on each edge; the phis are the
block-entry values reconstructed from those edges.

Another easy mistake is to think every conditional can be expressed as a join. The
`select` case is not a join block with hidden phis. It is a same-block value choice, so
there are no incoming edge/value pairs at all.

It is also easy to overfit a one-value merge helper and miss the real abstraction. A
single merged scalar is the baby case. The reusable pattern shows up when several live
values move together and the successor block needs the whole entry environment.

Another subtle mistake is to attach incoming values to the wrong predecessor block. The
incoming block on a phi must be the actual edge source that branches to the join, not
just the block that "morally" produced the value earlier in the CFG.

Finally, a named-state wrapper is only a readability layer. It should not hide that the
underlying lowering is still one phi per field.

It is also easy to stop one abstraction layer too early. `join.add_incoming(...)` is a
useful lowering primitive, but it is not yet the semantic operation most control-flow
code wants to express. The more natural unit is edge transfer: compute outgoing state,
then branch carrying that state.

It is equally easy to overgeneralize the block-entry helper. Sibling CFG targets often
must exist before an earlier `cbranch(...)` or `branch(...)` can name them, so not all
block creation can be collapsed into a single "create and enter" step.

## Apply When

Use this pattern when:

- several live values must survive a control-flow join together
- you want to think about merges as block entry state rather than one phi at a time
- a loop header or continuation block naturally feels like it takes arguments
- interpreter or VM state is being threaded through CFG joins

## Avoid When

Do not use this pattern when the logic is a same-block value choice that can stay as
`select`.

Do not jump straight to named state objects if the merged shape is still a tiny,
single-value conditional. In that case the raw form or a tuple-style join is usually
clearer.

Do not let the Pythonic helper become more magical than the CFG it lowers. The raw
tuple join should remain easy to reconstruct from the lab output.

Do not jump straight to a free-form `goto(block, state)` DSL in this lab. That is the
next abstraction pressure point, but this lab keeps the successor join explicit on the
helper itself.

Do not use the create-and-enter helper for blocks that need to be declared as forward
branch targets first. Predeclare those blocks explicitly and then enter them later.

## Next Questions

- When should loop-header phis be taught directly as block parameters in their own lab?
- What is the cleanest named-state surface once the merged fields look like Forth VM
  state such as `ip`, `sp`, `rp`, and cached `tos`?
- When should `branch_from_here(...)` be propagated into other phi/state-heavy labs,
  and which ones are clearer left raw?
