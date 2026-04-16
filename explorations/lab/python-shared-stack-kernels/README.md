# Python Shared Stack Kernels

## Question

Can the JonesForth-style primitive-empty words in
[primitive-stack-shape-synthesis.md](/Users/manny/fythvm/docs/references/forth/primitive-stack-shape-synthesis.md:1)
be demonstrated in pure Python with a readable split by requested operation type,
while still reusing a smaller set of shared implementation kernels underneath?

## Setup

This lab is intentionally pure Python. It does not JIT anything and it does not wire
into the package runtime. Instead it builds one small local machine model with:

- a downward-growing data stack
- a downward-growing return stack
- `dsp` and `rsp` pointer indices
- a `bytearray` memory region with 32-bit little-endian cell access

The source is split by the `Requested Operations` axis from the synthesis doc:

- [ops_stack.py](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/ops_stack.py:1)
- [ops_arithmetic.py](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/ops_arithmetic.py:1)
- [ops_compare_bitwise.py](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/ops_compare_bitwise.py:1)
- [ops_memory.py](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/ops_memory.py:1)
- [ops_return_stack.py](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/ops_return_stack.py:1)

The reusable implementation-shape helpers live in
[kernels.py](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/kernels.py:1).

Every operation exists twice:

- a raw implementation that spells out the behavior directly
- a kernelized implementation that routes through shared helpers

Every operation function is also tied back to the original Forth word two ways:

- the callable is registered through the no-op `@forth_op(...)` collector in
  [registry.py](/Users/manny/fythvm/explorations/lab/python-shared-stack-kernels/registry.py:1)
- the function docstring starts with the Forth word name and stack effect

## How to Run

```bash
uv run python explorations/lab/python-shared-stack-kernels/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/python-shared-stack-kernels/run.py
```

## What It Shows

The run output is grouped by requested operation type, not by kernel type.

For each group it prints:

- every requested Forth word in that section
- the raw Python function name
- the kernelized Python function name
- the recorded stack effect
- the shared kernel used by the kernelized variant

It then runs focused scenarios through both variants and proves they end with the same:

- `dsp`
- `rsp`
- raw data-stack array
- raw return-stack array
- memory bytes

The scenarios cover:

- stack shuffles, copies, drops, and `?DUP`
- unary and binary arithmetic, including signed `/MOD`
- unary predicates, binary comparisons, and bitwise operations
- cell and byte memory ops, `C@C!`, and `CMOVE`
- cross-stack transfers plus pointer snapshot/install words

## Pattern / Takeaway

The useful reuse boundary is smaller than the requested word list, but the readable
source split does not have to follow that boundary.

This lab keeps the code organized around the user-facing requested operation groups
while still showing that many words collapse into a smaller set of shared kernels:

- `permute`
- `dup_top`, `dup_segment`, `copy_from_depth`
- `unary_transform`
- `unary_predicate`
- `binary_reduce`
- `binary_multi_result`
- `memory_store`, `memory_fetch`, `memory_update`
- `copy_byte_and_advance`, `copy_block`
- stack-transfer and pointer-access helpers

That is the main lesson: preserve the Forth word surface for readability and tracing,
but lower repeated behavior through a smaller kernel layer.

## Non-Obvious Failure Modes

One easy mistake is to split the source by kernel family only. That does show reuse,
but it makes it harder to read the lab as "the requested operations from the document."
This lab keeps the source grouped by requested operation type on purpose.

Another trap is to make the kernelized wrappers so generic that the original Forth
word identity becomes blurry. The `@forth_op(...)` registry and docstring-first-line
rule are there to keep the trace back to the original word explicit.

It is also easy to compare only logical stacks and miss raw-state differences. For
example, pointer installs such as `DSP!` and `RSP!` can leave different raw backing
arrays even when the visible logical stack looks plausible. The parity check compares
the whole machine snapshot, not just the pretty rendering.

Signed division is another place where a Python mental model can drift from the Forth
source. Python's `//` and `%` follow floor-division rules, while JonesForth follows
x86 signed-division truncation toward zero. The lab uses an explicit `trunc_divmod`
helper so `/MOD` matches the intended semantics.

Finally, `DSP@` and `RSP@` are pointer-index snapshots in this lab, not host
addresses. That keeps the pure-Python model stable and readable, but it is a model of
the stack discipline, not a claim about final runtime ABI details.

## Apply When

Use this pattern when:

- you want to study Forth-like primitive behavior without bringing in llvmlite
- you want one visibility-friendly Python model that groups words the way a reader
  expects to find them
- you want to prove that many user-facing words can still lower through shared
  kernels
- you want decorator-collected metadata and docstrings to keep generated or wrapped
  behavior traceable back to original word names

## Avoid When

Do not use this as the final `fythvm` runtime design. It is a pure-Python exploration,
not a package API and not an execution engine.

Do not use this if the interesting question is physical runtime layout compatibility.
The package dictionary/runtime code and the stack/JIT labs are better references for
that.

Avoid treating the shared kernels as the only source structure worth keeping. The
point of this lab is that reader-facing grouping and implementation reuse are two
different axes, and both matter.

## Next Questions

- Which of these kernels are mature enough to promote into package-level helper ideas,
  if any?
- Should a follow-on lab add payload-bearing primitives such as `LIT`, `BRANCH`, and
  `0BRANCH` with the same raw-vs-kernelized pure-Python shape?
- Which parts of the pure-Python machine model should stay local to explorations, and
  which parts are useful debug-runtime patterns?
- When does the return-stack and pointer-install behavior want a separate visibility
  lab of its own?
