# Dictionary Linked Memory Layout

## Question

How do the `words.py` and `memory.py` shapes from `~/fyth` represent a dictionary as
linked entries in linear memory?

## Setup

This lab models a small dictionary in byte-addressed linear memory.

The v1 layout is intentionally narrow:

- each entry starts with a `previous` link cell
- the payload begins immediately after that link cell
- the payload stores a packed name header, the name bytes, padding to cell alignment,
  and one value cell
- `0` means null
- traversal walks newest-first by following the stored previous link

This lab does not try to reconcile the linked-memory model with `core/layout.py`, and
it does not decide broader Forth redefinition or compile-state semantics.

## How to Run

```bash
uv run python explorations/lab/dictionary-linked-memory-layout/run.py
```

## What It Shows

The script prints:

- the memory rules used by the lab
- a sequence of insertions into linear memory
- newest-first traversal through the linked entries
- exact lookup traces for a few names
- a small failure-mode probe that shows why byte offsets and cell indices are not the
  same thing

The main point is that the dictionary head is just the latest payload offset, and each
entry stores the previous payload offset in the cell immediately before its payload.

## Pattern / Takeaway

Use a linked linear-memory chain when you want a cheap, append-friendly dictionary
shape with newest-first traversal.

Keep the link pointer and payload offset distinct. The pointer lives in the cell before
the payload; the payload start is what traversal and lookup should follow.

## Non-Obvious Failure Modes

The easiest mistake is to confuse a byte offset with a cell index. In this layout, the
stored links are byte offsets. If you treat them like cell numbers and multiply again,
you jump to the wrong place in memory.

Another common mistake is to read the previous link from the payload start instead of
the cell immediately before it. That lands on the packed header and name bytes, not the
link.

The third mistake is conceptual: this lab is a clean v1 shape, not the final runtime
dictionary policy. It demonstrates the memory layout and traversal mechanics, but it
does not settle redefinition behavior or compile-state semantics.

## Apply When

Use this pattern when:

- you need a simple linked dictionary or symbol table in linear memory
- newest entries should be found first
- you want the structure to be easy to append and easy to traverse

## Avoid When

Do not use this shape when random access, bulk deletion, or prefix search is the main
requirement. A linked chain is cheap to append, but not the best fit for indexing-heavy
workloads.

Do not treat this lab as the canonical final runtime dictionary design. It is the first
pass over the memory layout only.

## Next Questions

- How should hidden or immediate words be interpreted once compile-state semantics are
  brought back in?
- What is the cleanest way to add deletion or redefinition without breaking the linear
  chain?
- When does a linked dictionary stop being the right abstraction and become a lookup
  bottleneck?
