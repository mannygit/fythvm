# Previous-Link List IR Abstractions

## Question

What should an IR helper own for a newest-first linked list whose nodes live in
linear memory as `[previous link][data...]`?

## Setup

This lab models the old `~/fyth` linked-list helper shape directly:

- memory is byte-addressed
- each node stores its previous node offset in the 32-bit cell immediately before its
  public data offset
- `0` means null
- the head of the list is the newest node

The lab has two variants:

- the raw variant is the source of truth and emits the byte-offset loads, stores, and
  loop phis directly
- the helper variant introduces `PreviousLinkNode` and `PreviousLinkListIR` so the
  node convention and loop scaffolding are named once without hiding the control-flow

Both variants emit:

- `append`
- `count`
- `get_nth` newest-first traversal

## How to Run

```bash
uv run python explorations/lab/previous-link-list-ir-abstractions/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/previous-link-list-ir-abstractions/run.py
```

## What It Shows

The script:

- builds raw and helper-based JIT functions for append, count, and nth-node lookup
- appends the same three values through both variants
- proves that both variants produce the same node offsets and identical backing bytes
- decodes the resulting newest-first traversal from host-side Python
- prints the emitted LLVM IR

The interesting comparison is not "raw versus magic." The helper version still makes
the loop and predecessor loads visible; it just centralizes the `[previous][data]`
shape and the byte-offset cell access machinery.

## Pattern / Takeaway

For a previous-link list in linear memory, the reusable helper should own:

- the fact that the public node offset points at data, not at the previous-link cell
- byte-offset cell access helpers
- the named node concept
- modern loop scaffolding for newest-first traversal

It should not hide the actual traversal shape. Counting and nth-node selection should
still read as explicit "walk until null, load previous from offset minus one cell"
logic.

## Non-Obvious Failure Modes

The first failure mode is reading the previous link from the public node offset. That
lands on the data cell, not on the link. The helper exists partly to make `offset - 4`
the canonical operation instead of a repeated hand-written subtraction.

The second failure mode is letting the first real node live at offset `0`. In this
shape, `0` is the null sentinel, so the first data cell has to start one cell later.

The third failure mode is abstracting the traversal so aggressively that it stops being
clear which offsets are loop-carried and which edge actually exits. The helper variant
uses a modern loop helper, but it still leaves the CFG visible.

## Apply When

Use this pattern when:

- the list head is a newest-first previous link
- nodes live inside a larger linear-memory region
- public APIs should talk about data offsets, not internal link slots
- you want append and traversal helpers for IR generation without committing to a
  higher-level container runtime

## Avoid When

Avoid this pattern when:

- the structure needs cheap random access or deletion
- the node shape is not actually `[previous link][data...]`
- a host-side debug/runtime structure is enough and no IR emission helper is needed

## Next Questions

- Should this helper eventually be promoted into `fythvm.codegen` once there is a
  second real package consumer?
- Which dictionary-specific operations belong above this helper rather than inside it?
- Is a callback-based traversal API worth keeping, or are named concrete operations
  like `count` and `get_nth` the clearer abstraction boundary?
