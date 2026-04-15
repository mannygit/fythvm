# Context Struct Stack Storage

## Question

How do you factor stack operations into one abstract layer while letting concrete
emitters decide how to derive the relevant IR pointers for stack storage?

## Setup

This lab is a follow-on to
[llvmlite-jit-stack-operations](/Users/manny/fythvm/explorations/lab/llvmlite-jit-stack-operations/README.md:1).
That earlier lab separated stack operations from stack storage ownership with a
composition-style storage object. This lab makes the next refactor explicit: a base
stack-emitter layer owns the stack operations themselves, and concrete subclasses
only define how to reach:

- the stack base pointer
- the stack-pointer cell

The lab shows four runnable variants:

- a raw context-struct-backed source-of-truth version with all field GEPs spelled out
- a Pythonic module-global emitter subclass
- a Pythonic pointer-global emitter subclass
- a Pythonic context-struct emitter subclass

The context-backed shape is the main point. It mirrors the older `~/fyth` direction
where stacks were derived from fields inside a larger runtime layout instead of being
owned as isolated globals.

## How to Run

```bash
uv run python explorations/lab/context-struct-stack-storage/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/context-struct-stack-storage/run.py
```

## What It Shows

The output prints:

- the raw context-struct IR where every context load and field GEP is explicit
- the Pythonic module-global, pointer-global, and context-struct IR variants
- stack traces for all four variants on the same push/pop/dup/swap/over scenario
- a parity check proving the abstract stack-op layer emits the same behavior across
  all three storage strategies

That makes the refactor boundary visible. The reusable thing is not the backing
layout itself. It is the stack-op layer that only asks for "where is the stack base?"
and "where is the stack pointer?"

## Pattern / Takeaway

If stack semantics stay the same while runtime layout changes, make the stack
operations the abstract layer and push pointer derivation into concrete emitters.

That gives one reusable layer for:

- module-global storage
- pointer-global storage
- context-struct field storage

The raw context-struct variant is the source of truth because it keeps the field
derivation fully explicit. The Pythonic variants earn their keep by showing that the
same stack-op methods can survive multiple layout strategies without duplicating
`push`, `pop`, `dup`, `swap`, and `over`.

## Non-Obvious Failure Modes

The easiest mistake is to abstract the wrong thing. If the base layer starts hiding
how the concrete storage is reached, it stops being a useful refactor and becomes a
new runtime model to debug.

Another easy mistake is to think "context-backed" means the stack ops became generic
automatically. They did not. The concrete subclass still has to derive the correct IR
field pointers for the stack array and stack-pointer cell.

A subtler trap is letting one concrete provider leak assumptions into the abstract
layer. If the base methods accidentally assume globals, explicit bind functions, or a
specific struct layout, the refactor is not really abstract.

## Apply When

Use this pattern when:

- stack semantics are stable but storage layout is evolving
- you want one reusable stack-op emitter across several runtime layouts
- the interesting variation is pointer derivation, not stack behavior
- you need the same low-level stack operations to work over a larger runtime context

## Avoid When

Do not use this shape if the stack behavior itself changes between layouts. In that
case, forcing everything through one abstract base will hide real semantic
differences.

Avoid pushing the abstraction so far that the emitted pointer derivation disappears.
The point of the lab is to make that boundary explicit, not to invent a mini
framework.

## Next Questions

- Should a future lab make the context struct closer to `~/fyth`'s full runtime
  layout with multiple stacks and registers?
- When is inheritance the right shape here versus a separate storage object as in the
  earlier stack lab?
- Which other runtime helpers besides stacks want the same "abstract ops, concrete
  pointer derivation" split?
