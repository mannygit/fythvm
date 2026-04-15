# ctypes Composite Runtime Layout

## Question

How do the fixed runtime records from `~/fyth` map into nested `ctypes` structs,
arrays, pointer fields, and promoted llvmlite struct views?

## Setup

This lab uses the promoted `StructHandle` / `BoundStructView` layer from
`src/fythvm/codegen/structs.py` against the real package-level ctypes records in
[dictionary.py](/Users/manny/fythvm/src/fythvm/dictionary.py:1):

- `Registers`
- `StackBounds`
- `DictionaryMemory`
- `InterpreterRuntimeData`

The raw anchor is `raw_read_here`, which uses explicit nested GEPs. The Pythonic
paths bind promoted struct views and keep the same nested layout visible with named
field access.

## How to Run

```bash
uv run python explorations/lab/ctypes-composite-runtime-layout/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/ctypes-composite-runtime-layout/run.py
```

## What It Shows

The run prints:

- concrete `ctypes` sizes and field offsets for the fixed runtime records
- emitted IR for:
  - a raw nested-field read
  - a Pythonic nested-field read
  - an array-field sum
  - a pointer-field span calculation
- live calls against real `ctypes` instances to prove the layout is not hypothetical

## Pattern / Takeaway

The fixed-record half of the old runtime is a good fit for promoted struct helpers.
Nested structs, arrays, and pointer fields all still lower to ordinary struct GEPs.
The Pythonic layer earns its keep by naming the fields, not by changing the memory
model.

## Non-Obvious Failure Modes

One easy mistake is thinking that once a field is an array or pointer, it stops being
"just a struct field." It does not. The struct access step still gets you a pointer to
the array field or pointer field, and then you continue with normal array GEP or
pointer arithmetic from there.

Another easy mistake is thinking this solves the full dictionary shape. It only solves
the fixed-record part. The actual word-entry protocol still has variable-size name
bytes before the fixed word prefix.

## Apply When

- you want a fixed runtime context with nested structs and arrays
- you already have stable `ctypes` records for the host-visible layout
- you want promoted named field access in llvmlite without hiding the real GEP shape

## Avoid When

- the layout is variable-sized rather than fixed-record
- the interesting protocol lives in raw byte regions before or after the fixed struct
- you need unions, recursive structs, or more ambitious ABI inference than this lab

## Next Questions

- What is the cleanest way to combine these fixed records with the variable word-entry
  protocol?
- Which parts of the old runtime should stay as `ctypes` records and which should stay
  raw-byte protocols?
- When do nested structs stop helping and a byte-oriented view become the better model?
