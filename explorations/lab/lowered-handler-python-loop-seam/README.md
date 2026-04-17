# Lowered handler Python loop seam

## Question

What is the smallest useful seam between a Python dispatch loop and one lowered
handler, if we want to start lowering slowly without giving up the visibility of the
host-side loop?

## Setup

This lab keeps almost everything in Python:

- the thread is a tuple of raw cells
- the dispatch loop is Python
- `LIT`, `ADD`, `BRANCH`, `0BRANCH`, `DOCOL`, and `HALT` are lowered through wrapper functions in this pass
- the host-visible machine state is a tiny `ctypes.Structure`
- the lowered wrapper reifies that `ctypes` layout through the promoted
  `StructHandle.from_ctypes(...)` helper in package code
- the bound state view is now generated from the `ctypes` layout too, so we are not
  hand-maintaining physical struct indexes after reification
- the state now uses promoted stack-view naming and shape (`stack` + downward-growing
  `sp`) so lowered handlers can use `StructViewStackAccess` directly
- the state also carries current-thread storage (`thread_cells` + `thread_length`) so a
  promoted `ThreadCursorIR` can wrap `ip` without inventing a separate thread-state
  axis
- the state also carries current-word thread storage plus a small return-frame area so
  `DOCOL` can enter a child thread without collapsing the whole interpreter into a
  native dispatch loop

This lab is the direct lowering follow-on to
[handler-requirements-python-loop](/Users/manny/fythvm/explorations/lab/handler-requirements-python-loop/README.md:1).
It reuses promoted learnings from that semantic/reference lab rather than inventing a
parallel model.

The lab is split by concern inside its directory:

- `seam_state.py`
  - host-visible ctypes state and generated promoted struct view
- `seam_lowering.py`
  - lowered op bodies, injected IR surfaces, and wrapper generation
- `seam_runtime.py`
  - Python-side dispatch, preflight, and execution
- `seam_thread.py`
  - ctypes thread-buffer helpers
- `seam_return.py`
  - lab-local return-frame storage helpers over shared state
- `seam_report.py`
  - labeled output for scenarios
- `run.py`
  - the small orchestrating entrypoint

`HALT`, `LIT`, `ADD`, `BRANCH`, `0BRANCH`, and `DOCOL` are now lowered. Their generated wrapper functions take a pointer to
that shared state and return normally to Python.

The important wiring detail is that `HandlerRequirements` is used for injected
surfaces, not backend policy:

- `HALT` declares `needs_execution_control=True`
- the lowered op body is shaped like `op_halt_ir(builder, *, control, err)`
- `LIT` declares stack egress plus `needs_thread_cursor=True`
- the lowered op body is shaped like `op_lit_ir(builder, *, data_stack, thread_cursor, err)`
- `ADD` declares stack ingress/egress and lowers as a binary reducer over
  the promoted `BoundStackAccess.binary_reduce(...)` helper
- `BRANCH` declares `needs_thread_cursor=True` and `needs_thread_jump=True`
- the lowered op body is shaped like `op_branch_ir(builder, *, thread_cursor, thread_jump, err)`
- `0BRANCH` declares stack ingress plus `needs_thread_cursor=True` and
  `needs_thread_jump=True`
- the lowered op body is shaped like `op_zbranch_ir(builder, *, data_stack, thread_cursor, thread_jump, err)`
- `DOCOL` declares `needs_current_xt=True`, `needs_return_stack=True`, and
  `needs_execution_control=True`
- the lowered op body is shaped like
  `op_docol_ir(builder, *, current_word_thread, return_stack, control, err)`
- the wrapper function injects `control` and `err` from the descriptor requirements
- the wrapper injects `StructViewStackAccess(state).bind(builder)` and `ThreadCursorIR`
  when the descriptor requirements ask for them
- the wrapper now also injects promoted `CurrentWordThreadIR` plus a lab-local
  `ReturnStackIR` when `DOCOL` asks for them
- the wrapper, not `op_halt_ir(...)`, adds the final `ret void`
- the host-visible state projection is generated from ctypes layout, including logical
  bitfield views for control state

The lab now also has the next seam surfaces ready for threaded entry:

- `thread_cursor` is treated as a capability wrapper around `ip` plus current-thread
  storage
- the concrete storage lives in the shared state as `thread_cells` and `thread_length`
- the lowered wrapper can inject `ThreadCursorIR` for handlers that declare
  `needs_thread_cursor=True`
- the lowered wrapper can inject `ThreadJumpIR` for handlers that declare
  `needs_thread_jump=True`
- the lowered wrapper can inject `CurrentWordThreadIR` for handlers that declare
  `needs_current_xt=True`

Backend choice stays lab-local, but most words in the current scenarios now route
through lowered wrappers while `EXIT` still runs in Python against the same shared
state.

That means the seam is intentionally narrow:

- Python still decides which handler to call
- the lowered handler only mutates shared state
- Python decides what the changed state means after the native call returns

## How to Run

```bash
uv run python explorations/lab/lowered-handler-python-loop-seam/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/lowered-handler-python-loop-seam/run.py
```

## What It Shows

The run prints:

- the generated LLVM IR for the lowered `LIT`, `ADD`, `BRANCH`, `0BRANCH`, `DOCOL`, and `HALT` handlers
- a `HALT`-only scenario
- a scenario where the JIT handles `LIT`, `ADD`, and `HALT`
- a scenario where the JIT handles `LIT`, `BRANCH`, and `HALT`
- a scenario where the JIT handles `LIT`, `0BRANCH`, and `HALT`
- a scenario where the JIT handles `DOCOL`, enters a child thread, and lets Python
  handle `EXIT` against the same shared return-frame state
- per-step traces with:
  - word
  - backend (`python` or `jit`)
  - stack before/after
  - state flags before/after

It also uses `HandlerRequirements` for two declarative pieces:

- data-stack ingress/egress preflight before each handler runs
- lowering-surface injection for the lowered op body

That now includes the promoted stack-access path:

- when a lowered handler declares stack ingress or egress requirements, the wrapper
  can inject `StructViewStackAccess(state).bind(builder)` without inventing a lab-only
  stack surface

The important visible behavior is:

- the lowered function ends with an ordinary `ret void`
- after the JIT call returns, Python sees `HALT_REQUESTED` set in shared state
- the Python loop stops because of that state bit, not because the lowered function
  somehow owns the whole dispatch loop

This lab explicitly demonstrates the first promoted lowering ingredients in one place:

- generated ctypes projections
- logical bitfield control fields
- promoted stack access
- promoted thread cursor/jump/current-word-thread access
- lowered `LIT`, `ADD`, `BRANCH`, `0BRANCH`, `DOCOL`, and `HALT` bodies with injected
  surfaces

## Pattern / Takeaway

If we want to start lowering very slowly, a good first seam is:

- keep dispatch in Python
- lower one handler at a time
- let lowered code mutate shared state
- let the Python loop interpret that state and remain in charge of control flow

This is especially clean for `HALT`, because the lowered handler can set a control bit
and return without forcing arithmetic lowering, thread-cursor lowering, or a full
native dispatch engine. It also keeps `EXIT` free to keep meaning return-stack
behavior later, instead of smuggling a temporary halt approximation into that word.

`LIT` proves the first real operand path: the op body reads one inline cell through a
thread cursor and pushes it through the promoted stack view without owning wrapper
termination or outer dispatch.

`ADD` is the next good lowered step because it proves the first binary stack kernel
shape over the same promoted stack view without introducing branch or return-stack
concerns.

`BRANCH` is the first lowered control step because it proves the thread-jump
surface without yet bringing in conditional control or return-stack semantics.

`0BRANCH` is the natural follow-on because it proves that the same lowered
thread-jump surface composes cleanly with a real stack input and a conditional
decision, while still staying far short of return-stack or `DOCOL` complexity.

`DOCOL` is the next big seam because it finally exercises the other major metadata
axis: `needs_current_xt` and `needs_return_stack`. The op body itself stays small, but
shared state now has to carry enough information to enter a child thread and later let
host-side `EXIT` restore the caller.

## Non-Obvious Failure Modes

One easy mistake is to think that because `HALT` is lowered, the lowered function
should also own the whole halt/return policy. That makes the seam too big too early.
In this lab, the lowered function only sets a bit; Python decides to stop.

Another easy mistake is to ignore metadata and route handlers through ad hoc opcode
checks. This lab keeps backend choice in a small explicit lab registry and uses
`HandlerRequirements` for what it was meant to do: declare the resources that the
local op body needs.

It is also easy to let `DOCOL` drag the whole model into an all-native return-stack
design too early. This pass deliberately keeps `EXIT` in Python so the question stays
about shared state and injected surfaces, not about committing the whole threaded
return path to native code at once.

It is also easy to let the local op body own wrapper termination. In this lab,
`op_halt_ir(...)` and `op_lit_ir(...)` only emit their local effects; the wrapper adds
`ret void` after the op body returns. That keeps the op bodies closer to the long-term
lowering shape.

It is also easy to lower too much state too soon. This lab keeps the state struct
small on purpose so the host/JIT boundary stays obvious.

## Apply When

- you want the first real host/JIT seam for interpreter work
- you want to lower one handler without committing to a native dispatch loop yet
- you want to prove that a shared state struct is enough for Python/native handoff
- you want a visibility-friendly starting point before lowering more kernels like
  `+`, thread jumps, or threaded entry

## Avoid When

- you already need native dispatch for most handlers
- the interesting question is about tail calls, `musttail`, or threaded continuation
- you need full native `EXIT` / return-stack semantics rather than a shared-state seam
- you need performance answers instead of seam-shape answers

## Next Questions

- When should `EXIT` move from host-side return-stack restoration into a lowered op?
- Should the promoted thread-access layer grow a reusable current-thread replacement
  helper once `DOCOL` and `EXIT` both want it?
- At what point does the Python loop stop being the right place for dispatch?
- Which next seam capabilities belong in `HandlerRequirements` after
  `needs_execution_control`?
