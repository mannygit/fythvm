# Lowered handler Python loop seam

## Question

What is the smallest useful seam between a Python dispatch loop and one lowered
handler, if we want to start lowering slowly without giving up the visibility of the
host-side loop?

## Setup

This lab keeps almost everything in Python:

- the thread is a tuple of raw cells
- the dispatch loop is Python
- `LIT` is still a Python handler
- the host-visible machine state is a tiny `ctypes.Structure`
- the lowered wrapper reifies that `ctypes` layout through the promoted
  `StructHandle.from_ctypes(...)` helper in package code

The lab is split by concern inside its directory:

- `seam_state.py`
  - host-visible ctypes state and promoted struct view
- `seam_lowering.py`
  - lowered op bodies, injected IR surfaces, and wrapper generation
- `seam_runtime.py`
  - Python-side dispatch, preflight, and execution
- `seam_report.py`
  - labeled output for scenarios
- `run.py`
  - the small orchestrating entrypoint

Only `HALT` is lowered. The generated function takes a pointer to that shared state,
sets one `HALT_REQUESTED` bit in the state flags, and returns normally to Python.

The important wiring detail is that `HandlerRequirements` is used for injected
surfaces, not backend policy:

- `HALT` declares `needs_execution_control=True`
- the lowered op body is shaped like `op_halt_ir(builder, *, control, err)`
- the wrapper function injects `control` and `err` from the descriptor requirements
- the wrapper, not `op_halt_ir(...)`, adds the final `ret void`

Backend choice stays lab-local:

- `LIT` is still routed through a Python handler in this lab
- `HALT` is routed through a lowered wrapper in this lab

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

- the generated LLVM IR for the lowered `HALT` handler
- a `HALT`-only scenario
- a mixed scenario where Python handles `LIT` and the JIT handles `HALT`
- per-step traces with:
  - word
  - backend (`python` or `jit`)
  - stack before/after
  - state flags before/after

It also uses `HandlerRequirements` for two declarative pieces:

- data-stack ingress/egress preflight before each handler runs
- lowering-surface injection for the lowered op body

The important visible behavior is:

- the lowered function ends with an ordinary `ret void`
- after the JIT call returns, Python sees `HALT_REQUESTED` set in shared state
- the Python loop stops because of that state bit, not because the lowered function
  somehow owns the whole dispatch loop

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

## Non-Obvious Failure Modes

One easy mistake is to think that because `HALT` is lowered, the lowered function
should also own the whole halt/return policy. That makes the seam too big too early.
In this lab, the lowered function only sets a bit; Python decides to stop.

Another easy mistake is to ignore metadata and route handlers through ad hoc opcode
checks. This lab keeps backend choice in a small explicit lab registry and uses
`HandlerRequirements` for what it was meant to do: declare the resources that the
local op body needs.

It is also easy to let the local op body own wrapper termination. In this lab,
`op_halt_ir(...)` only emits the halt effect; the wrapper adds `ret void` after the
op body returns. That keeps the op body closer to the long-term lowering shape.

It is also easy to lower too much state too soon. This lab keeps the state struct
small on purpose so the host/JIT boundary stays obvious.

## Apply When

- you want the first real host/JIT seam for interpreter work
- you want to lower one handler without committing to a native dispatch loop yet
- you want to prove that a shared state struct is enough for Python/native handoff
- you want a visibility-friendly starting point before lowering more kernels like
  `LIT`, `+`, or
  return-stack behavior

## Avoid When

- you already need native dispatch for most handlers
- the interesting question is about tail calls, `musttail`, or threaded continuation
- you need full `DOCOL` / return-stack semantics rather than just a halt-request bit
- you need performance answers instead of seam-shape answers

## Next Questions

- Should the next lowered handler be `LIT` or `+`?
- When should the shared state grow from a `HALT_REQUESTED` bit into richer control
  state?
- At what point does the Python loop stop being the right place for dispatch?
- Which next seam capabilities belong in `HandlerRequirements` after
  `needs_execution_control`?
