# llvmlite JIT stack operations

## Question

What is the smallest useful JITed stack pattern once stack operations are separated
from stack storage ownership, and what extra indirection is required to let the same
operations work on memory allocated outside the LLVM module?

## Setup

This lab is a clean-room reinterpretation of the downward-growing stack pattern from
`~/fyth`'s `stack.py`, `system.py`, and `test_stack.py`.

It now has four runnable variants:

- raw module-global-backed
- Pythonic module-global-backed
- raw external-backed
- Pythonic external-backed

The module-global-backed variants keep the original lab shape:

- a fixed-size stack array global
- a stack-pointer global
- exported operations: `reset_stack`, `push`, `pop`, `dup`, `swap`, `over`, and
  `get_sp`

The external-backed variants add the missing indirection layer:

- one global that holds the base pointer to host-owned stack cells
- one global that holds the pointer to a host-owned stack-pointer cell
- one binding function, `bind_external_stack`, that initializes those globals from
  host addresses

The stack operations themselves stay the same. What changes is where the base pointer
and stack-pointer pointer come from.

For the lower-level intrinsic side of explicit memory manipulation, see
[llvmlite-mem-intrinsics](/Users/manny/fythvm/explorations/lab/llvmlite-mem-intrinsics/README.md:1).

The raw versions are the source of truth. The Pythonic versions are only readability
layers; they should still make the physical stack layout and any required pointer
chasing obvious.

## How to Run

```bash
uv run python explorations/lab/llvmlite-jit-stack-operations/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/llvmlite-jit-stack-operations/run.py
```

## What It Shows

The output shows:

- the generated IR for all four variants
- the stack pointer value after each operation for module-global-backed and
  external-backed storage
- the logical stack contents derived from:
  - JIT-owned global memory in the first storage mode
  - host-owned `ctypes` memory in the second storage mode

That keeps the runtime discipline visible instead of hiding it behind a convenience
API.

## Pattern / Takeaway

If you want to preserve a low-level stack model in JITed code, keep two views visible
at the same time:

1. the physical memory discipline
2. the logical stack contents

That combination makes operations like `dup`, `swap`, and `over` much easier to reason
about than a purely abstract stack interface.

The reusable boundary is not the stack operations themselves. It is the storage
interface:

- where does the stack base pointer come from?
- where does the stack-pointer cell live?

Once those are indirected cleanly, the same stack ops can target either module-owned
globals or host-owned memory.

The Pythonic layer is useful when the helper only removes repeated storage access,
slot arithmetic, and operation boilerplate. Once the helper obscures the array layout
or the pointer chasing needed to reach external memory, it has gone too far.

## Non-Obvious Failure Modes

A downward-growing stack is easy to misunderstand from host-side memory reads. The
logical top-of-stack order and the backing array order are not the same thing.

That is the trap this lab makes explicit. If the host reads the raw array naively, the
values look reversed or "wrong" even when the stack logic is correct. The stack pointer
and the host-side rendering rule are part of the contract.

Another subtle issue is shared mutable state: these exported JIT functions mutate live
storage across calls. If a scenario needs a clean baseline, the host must reset the
stack explicitly rather than assuming each call is isolated.

The extra indirection needed for external storage is easy to trivialize mentally. The
stack ops do not suddenly become "generic" just because host memory exists. They still
need a base pointer and a stack-pointer cell, and now there is one more load step
before any real stack access can happen.

The other failure mode is over-helpful abstraction. If the helper hides where the
stack pointer lives, how `slot_ptr` addresses are formed, or when the code is loading
through pointer globals before touching host memory, it stops being a readable wrapper
and becomes a second runtime model.

## Apply When

Use this pattern when:

- you want a small JITed runtime structure with explicit stack semantics
- you need to reason about classic stack operations at the IR level
- you want to preserve both memory layout and logical behavior in one demo
- you want the same stack ops to work over either JIT-owned globals or host-owned
  memory
- you want a thin helper that makes repeated storage access and slot logic easier to
  read without making the runtime opaque

## Avoid When

Do not use this as a full runtime design. It is a focused lab, not a complete VM stack
implementation with bounds checks, error handling, or multiple stack segments.

Avoid abstracting away the array, stack-pointer, and pointer-indirection details if
the point of the work is to reason about the underlying runtime behavior.

Do not let the Pythonic version become the only version. The raw version is what keeps
the model honest.

## Next Questions

- Which safety checks are worth adding without obscuring the underlying stack shape?
- When should stack storage come from pointer globals versus a passed context struct?
- How should return-stack or mixed-stack patterns be modeled cleanly once storage is
  externalized?
- Which tiny stack helpers are worth reusing in other labs?
