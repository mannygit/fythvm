# HandlerRequirements-driven Python loop

## Question

Can the current package metadata drive a tiny Python interpreter loop strongly enough
to make the `LIT`, `+`, and `EXIT` execution shape visible without committing to a
final runtime ABI or lowering pipeline?

## Setup

This lab stays deliberately small:

- one thread represented as raw cells
- one Python `LoopState` with `ip`, `current_xt`, and a data stack
- three wired handlers:
  - `LIT`
  - `+`
  - `EXIT`
- one dispatcher that consults package metadata from
  [src/fythvm/dictionary/instructions.py](/Users/manny/fythvm/src/fythvm/dictionary/instructions.py:1)

The lab uses the current package concepts directly:

- `InstructionDescriptor.family`
- `InstructionDescriptor.associated_data_source`
- `HandlerRequirements`

It treats those as guidance for preflight checks and resource injection:

- stack ingress and egress checks come from `HandlerRequirements`
- inline-thread access comes from `associated_data_source`
- thread-cursor and error-exit injection come from `HandlerRequirements`

This is a pure Python proof of shape. It does not try to be the package runtime and
it does not lower anything through llvmlite.

## How to Run

```bash
uv run python explorations/lab/handler-requirements-python-loop/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/handler-requirements-python-loop/run.py
```

## What It Shows

The output prints two scenarios:

- one successful thread: `LIT 2 LIT 3 + EXIT`
- one failing thread: `LIT 2 + EXIT`

For each step the lab shows:

- the current `ip`
- the current word
- the word family
- the associated-data source
- the selected kernel id
- the stack before and after the step
- the concrete injected resources used for that handler call

That makes the current metadata story visible in one place:

- `LIT` is `primitive-inline-operand` and gets `data_stack`, `thread_cursor`, and
  `err`
- `+` is `primitive-empty` and gets `data_stack` and `err`
- `EXIT` is `primitive-empty` and gets `control` plus `err`

## Pattern / Takeaway

The current package metadata is already strong enough to drive a very small
interpreter loop if we treat it as:

- semantic family metadata
- associated-data-source metadata
- declarative per-handler requirements

That is enough to make the shape of a future lowering pipeline feel concrete without
claiming that the runtime is settled.

The key boundary is still the same:

- metadata explains what a handler needs
- the loop/dispatcher owns control flow
- the handler body owns only the local effect

## Non-Obvious Failure Modes

One easy mistake is to assume `HandlerRequirements` alone explains every injected
resource. In this lab it does not. The thread cursor is injected because the word's
`associated_data_source` is `INLINE_THREAD`, not because `HandlerRequirements`
contains a separate `needs_thread_cursor` flag yet.

Another easy mistake is to read `min_data_stack_out_space` as the exact net stack
effect. It is better understood here as a conservative preflight requirement for the
current helper shape, not as a full algebra of stack deltas. That distinction matters
once words both consume and produce values.

This lab also exposed that a raw `needs_ip` flag is too coarse. `LIT` does not want
to return a new `ip`; it wants a thread-local cursor capability that can consume the
next inline cell while the loop still owns dispatch. That likely generalizes into a
future split between cursor-like and jump-like thread capabilities.

It is also easy to overread the result and assume this means the final package runtime
should just become a Python dispatch loop. That is not the point. The point is to
practice the execution shape in a visibility-friendly form so the later lowering work
has a clearer target.

## Apply When

Use this pattern when:

- you want to pressure-test the metadata model before building real lowering
- you want to inspect injected resources and preflight checks in a human-readable way
- you need a tiny execution-shaped artifact to discuss `LIT` versus `+` versus
  `EXIT`
- you want a safe place to iterate on handler surfaces before committing to llvmlite

## Avoid When

Do not use this as the final package runtime or as proof that the lowering path is
done.

It is also the wrong shape if the real question is about:

- llvmlite CFG structure
- `musttail` continuation threading
- return-stack threading through `DOCOL`
- optimization of stack access or frame layout

Those need separate labs.

## Next Questions

- Should `associated_data_source` become first-class enough that the injection layer
  never has to inspect family metadata?
- Does thread-position access deserve explicit requirement flags such as
  `needs_thread_cursor` and `needs_thread_jump`, or is the associated-data source the
  right place to infer some of that?
- What is the smallest useful next extension:
  - `BRANCH`
  - `0BRANCH`
  - `DOCOL`
- At what point does this Python shape want a second variant that mirrors future
  lowering helpers more directly?
