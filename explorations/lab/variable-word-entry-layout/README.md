# Variable Word Entry Layout

## Question

How does a Forth-style word entry combine a variable-size encoded name blob with a
fixed word prefix and derived CFA/DFA offsets?

## Setup

This lab uses the package-level pure Python + `ctypes` dictionary runtime in
[runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:1), but it reconstructs
the offsets twice:

- a raw view that walks the byte/cell math explicitly
- a Pythonic view through `WordRecord`

The raw path is the source of truth here because the important part is the variable
layout protocol, not the wrapper class.

## How to Run

```bash
uv run python explorations/lab/variable-word-entry-layout/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/variable-word-entry-layout/run.py
```

## What It Shows

The run prints:

- the layout rules for the name blob and fixed prefix
- raw reconstructed offsets for several words
- the corresponding `WordRecord`-level view
- lookup traces that skip hidden words
- a failure probe showing why the name does not start at the fixed-prefix byte offset
- a memory snapshot in cells

## Pattern / Takeaway

The real dictionary word shape is a linear-memory protocol, not a plain fixed struct.
The fixed prefix is useful and can be modeled as a `ctypes` record, but the name blob
still lives before that prefix and determines where CFA and DFA land.

## Non-Obvious Failure Modes

One easy mistake is treating the fixed word prefix as if it owned the whole entry.
That loses the fact that the name bytes live before it and have a variable aligned
size.

Another easy mistake is mixing byte offsets and cell indices. `latest`, `link`,
`cfa`, and `dfa` are cell-index concepts here, but the name blob length starts as a
byte-sized protocol. The transitions between those units are where the bugs live.

## Apply When

- you need append-only newest-first dictionary entries in linear memory
- the name encoding is length-prefixed rather than NUL-terminated
- the fixed execution metadata starts after a variable-size name region

## Avoid When

- every entry is truly a fixed record
- you want to model the entire dictionary as a single static struct layout
- you need execution semantics rather than just dictionary memory behavior

## Next Questions

- What is the cleanest way to combine this variable-layout word protocol with the
  fixed runtime records in one integrated runtime?
- Should `immediate` remain metadata-only in the package prototype until a compiler
  layer exists, or is there a smaller behavior worth attaching sooner?
- When does this layout stop being a good debug-visible representation and want a more
  indexed lookup structure on top?
