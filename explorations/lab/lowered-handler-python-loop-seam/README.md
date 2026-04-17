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
- the state now also carries a real `DictionaryMemory*`, so lowered handlers can read
  real dictionary layout through `DictionaryIR`
- the state also carries current-thread storage (`thread_cells` + `thread_length`) so a
  promoted `ThreadCursorIR` can wrap `ip` without inventing a separate thread-state
  axis
- the state still carries a current-word thread extent plus a small return-frame area
  so `DOCOL` can enter a child thread without collapsing the whole interpreter into a
  native dispatch loop

This lab is the direct lowering follow-on to
[handler-requirements-python-loop](/Users/manny/fythvm/explorations/lab/handler-requirements-python-loop/README.md:1).
It reuses promoted learnings from that semantic/reference lab rather than inventing a
parallel model.

It now also kicks the tires of the promoted dictionary runtime for custom words:

- scenario-local custom words are allocated through `DictionaryRuntime`
- their real `cfa_index` values are used as `xt`s in the entry thread
- their real `dfa_index` cells back the child thread that lowered `DOCOL` enters
- the seam no longer invents a fake custom-word `xt` plus a separate child-thread
  buffer just to make threaded entry work

And it now kicks the tires of the lowered dictionary too, but only for one narrow
thing:

- lowered `DOCOL` resolves the child thread pointer from `current_xt` through
  `DictionaryIR`
- Python no longer stuffs `current_word_thread_cells` into shared state before every
  threaded call
- the child-thread length remains seam-local for now, because the dictionary layout
  does not treat thread extent as first-class Forth metadata

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
  - small host-side return-stack depth helper
- `seam_report.py`
  - labeled output for scenarios
- `run.py`
  - the small orchestrating entrypoint

`HALT`, `LIT`, `ADD`, `BRANCH`, `0BRANCH`, `DOCOL`, and `EXIT` are now lowered. A
small lowered fetch function and a small lowered dispatcher now sit beside those
handler wrappers, and all of them take a pointer to that shared state and return
normally to Python.

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
- the wrapper now also injects dictionary-backed current-word thread access plus
  promoted `ReturnStackIR` when `DOCOL` asks for them
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
- the lowered wrapper can inject dictionary-backed current-word thread access for
  handlers that declare `needs_current_xt=True`

Backend choice stays lab-local, and the active threaded-control scenarios now route
through lowered wrappers all the way through `EXIT`.

Python no longer fetches the current cell or chooses the handler directly:

- lowered fetch reads `thread_cells[ip]` and stores `current_xt`
- lowered dispatch resolves custom-word CFAs through the dictionary first
- then it falls back to primitive handler ids and calls the already-lowered handler body

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

- the generated LLVM IR for the lowered `LIT`, `ADD`, `BRANCH`, `0BRANCH`, `DOCOL`, `EXIT`, and `HALT` handlers
- a `HALT`-only scenario
- a scenario where the JIT handles `LIT`, `ADD`, and `HALT`
- a scenario where the JIT handles `LIT`, `BRANCH`, and `HALT`
- a scenario where the JIT handles `LIT`, `0BRANCH`, and `HALT`
- a scenario where the JIT handles `DOCOL`, enters a child thread, restores the
  caller through lowered `EXIT`, and then halts
- per-step traces with:
  - word
  - backend
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
- the Python loop now applies fallthrough only when no lowered op requested an
  exact next `ip`
- `DOCOL`, `EXIT`, `BRANCH`, and taken `0BRANCH` now install exact destinations
  directly rather than relying on a host-side `ip += 1` convention

This lab explicitly demonstrates the first promoted lowering ingredients in one place:

- generated ctypes projections
- logical bitfield control fields
- promoted stack access
- promoted thread cursor/jump access plus lowered dictionary-backed current-word
  thread resolution
- lowered `LIT`, `ADD`, `BRANCH`, `0BRANCH`, `DOCOL`, `EXIT`, and `HALT` bodies with injected
  surfaces

## Pattern / Takeaway

If we want to start lowering very slowly, a good first seam is:

- keep dispatch in Python
- lower one handler at a time
- let lowered code mutate shared state
- let the Python loop interpret that state and remain in charge of fallthrough
  versus exact-next-`ip` continuation

This is especially clean for `HALT`, because the lowered handler can set a control bit
and return without forcing arithmetic lowering, thread-cursor lowering, or a full
native dispatch engine.

Lowered fetch and lowered dispatch are the next seam step after that: they take away
the host loop's direct knowledge of `thread_cells[ip]` and of "which lowered handler
does this `xt` mean right now?" without yet forcing full native loop ownership.

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
lowered `EXIT` restore the caller. With explicit exact-`ip` control in shared state,
those handlers no longer need a fake pre-increment sentinel like `ip = -1`.

## Non-Obvious Failure Modes

One easy mistake is to think that because `HALT` is lowered, the lowered function
should also own the whole halt/return policy. That makes the seam too big too early.
In this lab, the lowered function only sets a bit; Python decides to stop.

Another easy mistake is to ignore metadata and route handlers through ad hoc opcode
checks. This lab keeps backend choice in a small explicit lab registry and uses
`HandlerRequirements` for what it was meant to do: declare the resources that the
local op body needs.

It is also easy to let `DOCOL` and `EXIT` drag the whole model into a much larger
native-dispatch rewrite too early. This pass still keeps the question narrower than
that: shared state plus local op bodies, with Python continuing to own outer dispatch.

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
- you need a full native dispatch engine rather than a shared-state seam
- you need performance answers instead of seam-shape answers

## Next Questions

- Should the promoted thread-access layer grow a reusable current-thread replacement
  helper once `DOCOL` and `EXIT` both want it?
- At what point does the Python loop stop being the right place for dispatch?
- Which next seam capabilities belong in `HandlerRequirements` after
  `needs_execution_control`?
