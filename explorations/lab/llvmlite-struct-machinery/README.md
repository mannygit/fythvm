# llvmlite Struct Machinery

## Question

How do llvmlite struct types actually work, and what changes when you choose a
literal struct, an identified struct, or a packed struct?

## Setup

This lab focuses on the struct machinery itself rather than on a larger runtime that
happens to use structs.

It builds one small live JIT module with:

- a raw anchor function that reads a field from a literal struct global using an
  explicit GEP
- a thin Pythonic `StructHandle` plus a builder-bound struct view, so the rest of
  the demo can read like `pair.second.load()` instead of manually threading both
  `builder` and `struct_ptr`
- four struct forms:
  - an unpacked literal struct
  - an unpacked identified struct whose body is set explicitly
  - a packed literal struct
  - an identified struct with mixed-width integer fields, including `i1`

The lab then proves the result in two ways:

- emitted IR and target-data layout summaries
- live `ctypes` reads and JIT calls against real addresses

This is a follow-on to
[llvmlite-ir-to-ctypes-bridge](/Users/manny/fythvm/explorations/lab/llvmlite-ir-to-ctypes-bridge/README.md:1)
and
[context-struct-stack-storage](/Users/manny/fythvm/explorations/lab/context-struct-stack-storage/README.md:1),
but the point here is the struct machinery itself rather than a specific runtime
consumer.

## How to Run

```bash
uv run python explorations/lab/llvmlite-struct-machinery/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/llvmlite-struct-machinery/run.py
```

## What It Shows

The output prints:

- the generated IR, including:
  - one literal struct global
  - one identified struct definition
  - one packed literal struct global
  - one mixed-width identified struct definition with `i1`, `i8`, `i16`, and `i64`
  - one raw field reader and several helper-built functions
- concrete ABI layout summaries for each struct form:
  - size
  - alignment
  - per-field byte offsets
- `ctypes` layout summaries for the same structs
- live host-visible proof that:
  - the raw literal field reader returns the expected value
  - a JIT function can read through an identified struct pointer
  - host-side mutation through `ctypes` is visible to JIT code
  - packed layout really changes offsets and size
  - mixed-width fields make padding visible
  - an `i1` field can be loaded, stored, and bridged, but still has to be treated as
    part of a real ABI layout rather than as an abstract “bit”

The raw function is the source-of-truth anchor. The helper-backed parts earn their
keep by making repeated struct field access and global definition easier to read
without hiding the underlying rules. The bound view is intentionally thin: the field
properties still lower to ordinary `[0, field_index]` GEPs.

## Pattern / Takeaway

The key split is:

- use **literal structs** when you want an inline anonymous shape quickly
- use **identified structs** when the named type matters and you want to set the body
  explicitly
- use **packed structs** only when the packed layout itself is intentional and you are
  prepared to carry that ABI consequence through the host bridge
- treat **mixed-width structs** as a layout question first; tiny integer widths still
  participate in ABI size, alignment, and padding rules

Field access in llvmlite still follows the same rule regardless of naming:

- if you have a pointer to a struct, field GEP uses `[0, field_index]`

The helper layer is useful only if it keeps those layout and GEP rules visible.
Binding the builder and struct pointer once can help a lot with readability, but the
helper should still feel like a labeled view over normal GEPs rather than a new
struct system.

## Non-Obvious Failure Modes

One easy mistake is thinking that identified structs are just “named literals” with
all the same constructor options. In this environment, `IdentifiedStructType.set_body`
does **not** accept `packed=True`, so packed structs are effectively a literal-struct
path here.

Another easy mistake is forgetting why struct GEP starts with zero. The first index
steps through the pointer-to-struct itself; the second index selects the field.
Dropping the leading zero is not a harmless shorthand.

Literal versus identified structs can also be misread as an ABI distinction. If the
field bodies match and the packedness matches, the layout is the same; the main
difference is naming, forward declaration behavior, and how the IR reads.

The host bridge can also lie to you if the `ctypes` side does not preserve packedness.
A packed LLVM struct needs a packed `ctypes.Structure` as well, or the host layout
silently drifts from the JIT layout.

`i1` fields are another easy place to fool yourself. A 1-bit integer in LLVM IR does
not mean “this will obviously behave like a Python or C bitfield object.” In a struct,
it still lives inside a concrete ABI layout with offsets, alignment, and surrounding
padding. The host bridge has to model the storage reality, not the mental shorthand.

A bound view with field properties can also become misleading if it stops feeling like
GEP and load/store sugar. In this lab the raw anchor stays explicit on purpose so the
property form never gets to pretend structs are magical objects at IR time.

## Apply When

Use this pattern when:

- you need to understand struct layout before building a larger runtime on top of it
- you want to choose deliberately between literal and identified struct forms
- you need to bridge a struct through `ctypes` and want to validate the ABI directly
- you are debugging field offsets, struct naming, packed layout consequences, or
  mixed-width field behavior

## Avoid When

Do not use this lab as a full treatment of recursive or self-referential structs.
That is a separate problem and belongs in a different exploration.

Avoid adding a large helper framework on top of llvmlite structs before you are clear
on the underlying GEP and layout rules. If the helper makes field access look magical,
it is hiding the thing this lab is trying to teach.

## Next Questions

- What is the cleanest follow-on lab for recursive identified structs and self-pointers?
- When should a runtime use packed structs at all instead of accepting normal ABI padding?
- When does an `i1` field justify a packed struct or a different representation entirely?
- Should a future lab compare struct field access through direct GEP versus helper
  wrappers more aggressively?
