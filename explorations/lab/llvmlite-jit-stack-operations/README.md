# llvmlite JIT stack operations

## Question

What is the smallest useful JITed stack pattern worth preserving from the older
`~/fyth` runtime experiments, and what does a Pythonic wrapper improve without hiding
the stack layout?

## Setup

This lab is a clean-room reinterpretation of the downward-growing stack pattern from
`~/fyth`'s `stack.py` and `test_stack.py`.

It now has two implementations:

- a raw version that keeps the stack globals and slot arithmetic explicit
- a Pythonic version that uses a small local `StackLayout` helper to reduce repeated
  load/store/GEP boilerplate while keeping the memory layout visible

The JIT module owns:

- a fixed-size stack array
- a stack pointer global
- exported operations: `reset_stack`, `push`, `pop`, `dup`, `swap`, `over`, and
  `get_sp`

The host reads both the stack pointer and the backing array through global addresses so
the memory model stays visible alongside the logical stack view.

The raw version is the source of truth. The Pythonic version is only a readability
layer; it should still be obvious how the physical stack is laid out and how each
operation mutates it.

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

- the generated IR for the raw and Pythonic stack globals and operations
- the stack pointer value after each operation for both variants
- the logical stack contents derived from the backing array for both variants

That makes the runtime discipline visible instead of hiding it behind a convenience API.

## Pattern / Takeaway

If you want to preserve a low-level stack model in JITed code, keep two views visible
at the same time:

1. the physical memory discipline
2. the logical stack contents

That combination makes operations like `dup`, `swap`, and `over` much easier to reason
about than a purely abstract stack interface.

The Pythonic layer is useful when the helper only removes repeated slot arithmetic and
sp-pointer bookkeeping. Once the helper starts obscuring the array layout, it has gone
too far.

## Non-Obvious Failure Modes

A downward-growing stack is easy to misunderstand from host-side memory reads. The
logical top-of-stack order and the backing array order are not the same thing.

That is the trap this lab makes explicit. If the host reads the raw array naively, the
values look reversed or "wrong" even when the stack logic is correct. The stack pointer
and the host-side rendering rule are part of the contract.

Another subtle issue is shared mutable state: these exported JIT functions mutate live
global storage across calls. If a scenario needs a clean baseline, the host must reset
the stack explicitly rather than assuming each call is isolated.

The other failure mode is over-helpful abstraction. If the helper hides where the
stack pointer lives or how `slot_ptr` addresses are formed, it stops being a readable
wrapper and becomes a second runtime model.

## Apply When

Use this pattern when:

- you want a small JITed runtime structure with explicit stack semantics
- you need to reason about classic stack operations at the IR level
- you want to preserve both memory layout and logical behavior in one demo
- you want a thin helper that makes repeated stack pointer and slot logic easier to
  read without making the runtime opaque

## Avoid When

Do not use this as a full runtime design. It is a focused lab, not a complete VM stack
implementation with bounds checks, error handling, or multiple stack segments.

Avoid abstracting away the array and stack-pointer details if the point of the work is
to reason about the underlying runtime behavior.

Do not let the Pythonic version become the only version. The raw version is what keeps
the model honest.

## Next Questions

- Which safety checks are worth adding without obscuring the underlying stack shape?
- How should return-stack or mixed-stack patterns be modeled cleanly?
- When does a stack abstraction become too indirect to remain useful for exploration?
- Which tiny stack helpers are worth reusing in other labs?
