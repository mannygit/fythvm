# HandlerRequirements-driven Python loop

## Question

Can the current package metadata drive a tiny Python interpreter loop strongly enough
to make the runtime shape of `LIT`, `LITSTRING`, `+`, `DOCOL`, and `EXIT` visible,
while also supporting a tiny compile-time path for `S"` and `IF`/`THEN`, without
committing to a final runtime ABI or lowering pipeline?

## Setup

This lab stays deliberately small:

- one thread represented as raw cells
- one Python `LoopState` with `ip`, `current_xt`, and a data stack
- one linear decompiler over the same raw thread cells
- one tiny compile step for:
  - `S"`
  - `IF`
  - `THEN`
- one tiny compiler-word lookup path driven by
  [src/fythvm/dictionary/compiler_words.py](/Users/manny/fythvm/src/fythvm/dictionary/compiler_words.py:1)
- a tiny scenario-local word registry so named threaded words can be introduced
- handlers for:
  - `LIT`
  - `LITSTRING`
  - `+`
  - `BRANCH`
  - `0BRANCH`
  - `DOCOL`
  - `EXIT`
- one dispatcher that consults package metadata from
  [src/fythvm/dictionary/instructions.py](/Users/manny/fythvm/src/fythvm/dictionary/instructions.py:1)

The lab uses the current package concepts directly:

- `InstructionDescriptor.family`
- `InstructionDescriptor.associated_data_source`
- `HandlerRequirements`
- `CompilerWordDescriptor`

It treats those as guidance for preflight checks and resource injection:

- stack ingress and egress checks come from `HandlerRequirements`
- inline-thread access comes from `associated_data_source`
- thread-cursor and error-exit injection come from `HandlerRequirements`
- compile-time `S"` / `IF` / `THEN` lookup comes from the neighboring compiler-word
  registry
- compile-time parsing and emission go through `SourceCursor`, `ThreadEmitter`, and
  `PatchStack` instead of open-coded parser branches
- `DOCOL` gets an abstract `current_word_thread` capability instead of touching a raw
  `dfa` detail directly
- `+` lowers through a local `binary_reduce(...)` kernel instead of spelling out raw
  list mutation inline
- even the local kernel now goes through `stack_pop(...)`, `stack_push(...)`, and
  `stack_peek(...)` helpers so the lab does not teach Python list methods as the
  execution contract

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
- one counted inline string: `LITSTRING "hi" EXIT`
- one compiled string emitter: `S" hi" EXIT`
- one compiled long string emitter: `S" hello" EXIT`
- one failing thread: `LIT 2 + EXIT`
- one unconditional branch skip: `LIT 7 BRANCH 2 LIT 999 EXIT`
- one conditional branch skip: `LIT 0 0BRANCH 2 LIT 999 EXIT`
- one compiled branch emitter: `LIT 0 IF LIT 999 THEN EXIT`
- three compile-time failure cases:
  - unterminated `S"`
  - `THEN` without `IF`
  - `IF` without `THEN`
- one threaded call: `SUM23 EXIT` with `SUM23 := LIT 2 LIT 3 + EXIT`

Each scenario now carries explicit expected outcomes:

- expected compiled thread cells when a compile source is present
- expected decompiled thread rows
- expected final stack
- expected halted/error status
- expected final `ip`
- expected executed word trace

For each step the lab shows:

- the compile source and emitted thread when the scenario starts from source text
- the linear decompiled thread
- any custom threaded word bodies
- the current `ip`
- the current word
- the word family
- the associated-data source
- the selected kernel id
- the stack before and after the step
- the concrete injected resources used for that handler call

It also asserts the decompile result and the final execution result before printing
the trace, so the lab is not relying on manual eyeballing alone anymore.

That makes the current metadata story visible in one place:

- `LIT` is `primitive-inline-operand` and gets `data_stack`, `thread_cursor`, and
  `err`
- `LITSTRING` is `primitive-inline-operand` and uses the same cursor abstraction, but
  now consumes a variable-width counted payload
- `+` is `primitive-empty` and gets `data_stack` and `err`
- `S"` is not a runtime handler here; it is a tiny compile-time emitter that lays
  down `LITSTRING`, a count cell, and packed payload cells through a compiler-word
  descriptor and a thread emitter
- `IF` and `THEN` are also compile-time emitters here; they patch `0BRANCH` offsets
  into the emitted thread through a patch stack instead of participating in runtime
  dispatch directly
- `BRANCH` is `primitive-inline-operand` and gets `thread_cursor`, `thread_jump`,
  and `err`
- `0BRANCH` is `primitive-inline-operand` and gets `data_stack`, `thread_cursor`,
  `thread_jump`, and `err`
- `SUM23` is a `colon-thread` word and gets `current_word_thread`, `control`, and
  `err`
- `EXIT` is `primitive-empty` and gets `control` plus `err`

## Pattern / Takeaway

This lab is the semantic/reference half of the current pair of interpreter labs.
It establishes the metadata-driven execution shape before any llvmlite lowering
enters the picture.

The current package metadata is already strong enough to drive a very small
interpreter loop if we treat it as:

- semantic family metadata
- associated-data-source metadata
- declarative per-handler requirements

And a very small compile-time layer is already enough to close the loop back into
that runtime shape if we keep it narrow:

- parse-time words consume source text
- compiler/meta words live in a neighboring compiler-word registry instead of the
  runtime instruction registry
- compile-time emitters lay down runtime thread cells
- the existing decompiler and executor then validate the emitted shape

That is enough to make the shape of a future lowering pipeline feel concrete without
claiming that the runtime is settled.

The key boundary is still the same:

- metadata explains what a handler needs
- the loop/dispatcher owns control flow
- the handler body owns only the local effect
- reusable stack-shape kernels sit between handler meaning and storage details
- the decompiler owns linear thread reading and inline-operand rendering over the same
  thread representation
- one scenario spec plus one structured result object gives us a reusable validation
  harness for future ctypes or lowered backends

Concretely, this lab proves:

- metadata-driven injection from `HandlerRequirements`
- the cursor/jump split for inline-thread words
- the neighboring compiler-word registry shape
- semantic stack-kernel factoring without committing to a concrete lowered storage
  path

It stops short of real IR lowering on purpose. The follow-on lab for that next seam is
[lowered-handler-python-loop-seam](/Users/manny/fythvm/explorations/lab/lowered-handler-python-loop-seam/README.md:1).

## Non-Obvious Failure Modes

One easy mistake is to assume `associated_data_source` and `HandlerRequirements` are
competing ways to say the same thing. In this lab they are not. `associated_data_source`
still names the runtime data source, while `HandlerRequirements` now explicitly asks
for `thread_cursor` and `thread_jump` capabilities where needed.

Another easy mistake is to read `min_data_stack_out_space` as the exact net stack
effect. It is better understood here as a conservative preflight requirement for the
current helper shape, not as a full algebra of stack deltas. That distinction matters
once words both consume and produce values.

It is also easy to let `current_xt -> DFA` leak all the way into handler code just
because the underlying threaded-word representation is known. This lab deliberately
keeps `DOCOL` on a higher-level `current_word_thread` capability so the handler only
depends on "enter this word's thread" rather than on one exposed storage detail.

It is also easy to write a decompiler that follows runtime control flow instead of
rendering the linear thread layout. This lab keeps those separate on purpose:
execution traces show which words actually ran, while the decompiler shows what is
stored in the thread, including words that may be skipped by a branch.

It is also easy to leave the lab in a misleading state by writing handlers directly as
`pop/pop/push` against a Python list. That works, but it teaches the wrong lesson.
This lab keeps `+` routed through a local `binary_reduce(...)` kernel so the visible
shape stays "binary reducer over an abstract stack surface" rather than "Python list
is the contract."

This lab also exposed that a raw `needs_ip` flag is too coarse. `LIT` wants a
thread-local cursor capability. `BRANCH` and `0BRANCH` want both a cursor and a jump
capability. That is a better fit than pretending every inline-thread word just wants
the same raw `ip` integer.

`LITSTRING` adds the next pressure point: cursor access is not only about one inline
cell. Some words consume a variable-width counted payload, and the handler surface is
cleaner if that remains a cursor operation instead of open-coded `ip` arithmetic in
the handler.

This lab now keeps that abstraction explicitly above C-string territory: compile-time
parsing and runtime inline-string recovery both traffic in a counted payload view, not
in a NUL-terminated host string model.

It is also easy to blur runtime words with compile-time emitters once the same lab
contains both. This lab keeps that boundary explicit: `S"` and `IF`/`THEN` operate on
source text and emitted cells, while `LITSTRING` and `0BRANCH` operate on the stored
thread at runtime.

It is also easy to overread the result and assume this means the final package runtime
should just become a Python dispatch loop. That is not the point. The point is to
practice the execution shape in a visibility-friendly form so the later lowering work
has a clearer target.

## Apply When

Use this pattern when:

- you want to pressure-test the metadata model before building real lowering
- you want to inspect injected resources and preflight checks in a human-readable way
- you want a tiny compile-to-thread path that can be checked against the same
  decompiler and executor harness
- you need a tiny execution-shaped artifact to discuss `LIT` versus `+` versus
  `EXIT`, fixed-width versus variable-width inline-thread words, or primitive
  inline-thread words versus `DOCOL`
- you want to see cursor-style and jump-style thread capabilities in the same loop
- you want a safe place to iterate on handler surfaces before committing to llvmlite

## Avoid When

Do not use this as the final package runtime or as proof that the lowering path is
done.

It is also the wrong shape if the real question is about:

- llvmlite CFG structure
- `musttail` continuation threading
- optimization of stack access or frame layout
- richer decompiler formatting than "linear stored thread plus named child bodies"
- a complete outer interpreter or standard Forth compiler

Those need separate labs.

## Next Questions

- Should `associated_data_source` become first-class enough that the injection layer
  never has to inspect family metadata?
- What is the smallest useful next extension after `LITSTRING`:
  - richer pointer-like stack values for inline strings and other thread payloads
  - compile-time words that create named threaded words instead of just entry threads
- Should `associated_data_source` remain purely semantic, or should some injections
  continue to be inferred from it alongside explicit requirement flags?
- At what point does this Python shape want a second variant that mirrors future
  lowering helpers more directly?
