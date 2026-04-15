# ctypes Struct Reification

## Question

How do you start from a `ctypes.Structure` declaration and produce both the right
llvmlite struct shape and the right bound view for named field access, including real
ctypes bitfields?

## Setup

This lab treats the `ctypes.Structure` declaration as the source of truth.

It reifies each source struct into:

- a llvmlite literal struct that matches the host-visible layout
- explicit padding fields when the source layout has gaps
- grouped storage fields when multiple ctypes bitfields share one storage unit
- a generated bound view whose properties preserve the original ctypes field names
- printed Python class source for that generated view, so the dynamic shape is still
  readable as real class code

The raw anchor stays explicit on purpose:

- one function manually reads a bitfield from the grouped storage byte using GEP,
  shift, and mask operations

The Pythonic/generated path then uses the reified named view for the same shape:

- `header.mode.load()`
- `header.mode.store(...)`
- `packet.value.load()`

This is a follow-on to
[llvmlite-struct-machinery](/Users/manny/fythvm/explorations/lab/llvmlite-struct-machinery/README.md:1),
but the focus here is inversion: starting from ctypes declarations rather than from
handwritten llvmlite struct types.

## How to Run

```bash
uv run python explorations/lab/ctypes-struct-reification/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/ctypes-struct-reification/run.py
```

## What It Shows

The output prints:

- the original ctypes declarations
- the reified logical-to-physical mapping
- the generated Python view classes
- the generated IR
- LLVM target-data layout summaries
- ctypes layout summaries
- live JIT proof against actual ctypes instances and global addresses

The demo covers three source structs:

- an ordinary aligned struct with a padding gap
- a packed ctypes struct
- a bitfield-bearing ctypes struct with three logical fields sharing one byte and a
  later aligned scalar field

The bitfield case is the important one:

- the raw anchor manually reads `mode` from the shared storage byte
- the generated path reads and writes the same logical field through a named bound view
- host mutation of the ctypes bitfields is visible to JIT code
- generated JIT bitfield writes are visible back through the ctypes instance

## Pattern / Takeaway

The reusable pattern is:

- treat the ctypes declaration as the canonical layout contract
- reify physical storage first
- generate logical field access second

For ordinary fields, the logical field can point directly at one physical LLVM field.
For bitfields, the logical field must become a view over a shared storage unit, not a
naive tiny LLVM struct member.

The generated bound view earns its keep because it preserves the source names while
still lowering to ordinary GEP plus load/store or GEP plus shift/mask/update logic.
Printing the generated class source keeps that dynamic step inspectable instead of
leaving the view as an opaque `type(...)` artifact.

## Non-Obvious Failure Modes

The biggest trap is thinking a ctypes bitfield like `("mode", c_ubyte, 3)` should
reify to an LLVM struct field of type `i3`. That loses the actual shared storage
shape. The correct lowering is one storage byte plus logical views over bit ranges.

Another easy mistake is forcing every reified struct into one always-packed LLVM form.
That matches packed ctypes declarations, but it throws away natural aggregate
alignment for ordinary ctypes structs. In this lab, default ctypes structs reify as
ordinary literal structs with explicit padding, while `_pack_` sources reify as packed
literal structs.

It is also easy to forget that the generated bound view is only a source-level
convenience. The storage layout does not disappear just because the Python API now
reads like `header.mode.load()`.

The inverse mistake is hiding too much behind runtime metaprogramming. If the dynamic
view cannot be printed as ordinary Python class source, it becomes much harder to read,
debug, or explain why a field descriptor exists at all.

## Apply When

Use this pattern when:

- a host-side ctypes declaration already exists and should remain canonical
- you want llvmlite codegen to match host layout exactly instead of re-declaring the
  struct by hand
- you need named field access over a generated struct view
- you need to bridge real ctypes bitfields into JIT code without lying about storage

## Avoid When

Do not use this as a general-purpose struct schema system yet.

This first lab intentionally does not cover:

- nested structs
- arrays
- pointers
- unions

If the real problem is broader schema evolution or cross-language type generation,
this reifier is too narrow and too ctypes-specific.

## Next Questions

- What is the cleanest follow-on for nested ctypes structs and arrays?
- Should a reusable package-layer reifier keep ctypes as the only source of truth, or
  eventually grow a shared schema above ctypes and llvmlite?
- How should signed ctypes bitfields be surfaced in the generated view API when the
  caller wants a fully sign-extended result directly?
