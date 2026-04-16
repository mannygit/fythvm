# Execution Invariants

This document starts the Step 4 workstream from
[Forth Implementation Alignment Report](/Users/manny/fythvm/docs/references/forth/forth-implementation-alignment-report.md:1):
specify execution invariants before choosing execution form.

It is intentionally an initial state/invariants artifact, not a final execution-model
decision.

This doc does **not** choose:

- indirect threading vs loop-and-switch
- tail-call dispatch vs central dispatch loop
- exact host/runtime lowering strategy

It does record the core execution state that any later execution strategy will need to
preserve.

## Working Direction

The current working direction is:

- execution uses one uniform logical handler surface over one machine state
- runtime differences are primarily about:
  - what state a handler reads or writes
  - where its associated data comes from
  - how it continues dispatch
- dispatch form is a separate concern from handler ABI

So this document treats:

- handler ABI as uniform
- machine state as the core execution substrate
- runtime metadata as a supporting layer around that substrate

## Relationship To Neighboring Docs

- [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
  settles the structure of dictionary entries and the meaning of `xt`, `CFA`, and `DFA`
- [docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
  settles the runtime-family layer selected by `CodeField.handler_id`
- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)
  settles the neighboring compile-time layer around `STATE`, `immediate`, and
  compiler/meta legality

This document is about the control/state substrate that connects those layers during
execution and interpretation.

## Uniform Handler Surface

The current recommended lens is that runtime handlers should share one uniform logical
signature over machine state.

That means:

- execution should not be designed around family-specific handler ABIs
- runtime families do not justify different primitive/runtime signatures
- the executor should be able to dispatch any handler through the same basic surface

What varies is not the call shape but:

- which parts of machine state a handler reads
- which parts of machine state a handler updates
- where the handler recovers associated data
- how the handler continues into the next dispatch step

This matches the direction already visible in `~/fyth` and the backlog dispatch labs:

- uniform builtin/handler shape
- dispatch strategy varied independently
- CFG rewriting, `musttail`, and loop dispatch were continuation mechanics, not family
  ABI definitions

## Core Execution State

The current best zoomed-out model is:

- `LATEST`
  - head pointer for the linked dictionary
- `HERE`
  - current write cursor into dictionary memory
- `STATE`
  - interpreter/compiler mode
- `DATA_STACK_PTR`
  - current data-stack pointer
- `RETURN_STACK_PTR`
  - current return/control-stack pointer
- input source and parse cursor
  - the current input buffer/source plus where token parsing is up to
- `current_xt`
  - the word currently being dispatched
- `ip`
  - the current position in the active thread

This is not necessarily the exact final storage layout, but it is the current best
execution-state model.

## Associated Data Sources

The current working runtime split is:

- `NONE`
  - the handler needs no associated runtime data beyond machine state
- `WORD_LOCAL_DFA`
  - the handler recovers associated data from `current_xt -> DFA`
- `INLINE_THREAD`
  - the handler recovers associated data from `ip` in the active thread

Examples:

- `primitive-empty`
  - `NONE`
- `colon-thread`
  - `WORD_LOCAL_DFA`
- `LIT`, `BRANCH`, `0BRANCH`, `LITSTRING`
  - `INLINE_THREAD`

This is the clearest current replacement for the older vague idea of "payload" as one
bucket.

## Parse-Time Input Is Separate

Parse-time/token data is not one of the runtime associated-data sources above.

It belongs to interpreter/compiler input state:

- current input source/buffer
- parse cursor / current offset

This matters because:

- compiler/meta words consume parse-time input state
- runtime inline-operand words consume thread state
- those are different data sources and should not be conflated

## First Discipline: Keep `STATE` Narrow

`STATE` should mean only:

- interpret mode
- compile mode

It should **not** become a catch-all bucket for:

- overflow state
- last exception state
- generic fault status
- unrelated executor bookkeeping

If fault or exception state needs to be tracked later, it should get a separate
representation.

This keeps the compiler-mode story aligned with:

- JonesForth's `STATE`
- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)

## Dictionary Pointers

### `LATEST`

`LATEST` is the head of the dictionary chain.

Execution and interpretation need it because:

- name lookup starts from the newest visible word
- shadowing depends on newest-first traversal
- defining words and compiler/meta words need access to the current dictionary head

This is already a real part of the runtime package state:

- [schema.py](/Users/manny/fythvm/src/fythvm/dictionary/schema.py:22)

### `HERE`

`HERE` is the current write cursor into dictionary memory.

Good current intuition:

- `HERE` points at writable dictionary space
- the region at and after `HERE` is scratch/build space until `HERE` is advanced

Execution and compilation need it because:

- `,` and related builders append into dictionary memory
- word construction advances it
- defining/compiler words rely on it as the build frontier

This is also already real in package/runtime state:

- [schema.py](/Users/manny/fythvm/src/fythvm/dictionary/schema.py:22)
- [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:71)

## Stack Pointers

The current core state model assumes two distinct stack pointers:

- `DATA_STACK_PTR`
- `RETURN_STACK_PTR`

The exact pointer/index convention is still an implementation detail, but the semantic
distinction is already important:

- the data stack is for ordinary Forth data flow
- the return/control stack is for threaded control/execution structure

This aligns with both JonesForth and Moving Forth and should be treated as an execution
invariant even before the final executor shape is chosen.

Current package schema already has stack-pointer state:

- `sp`
- `rsp`
- [schema.py](/Users/manny/fythvm/src/fythvm/dictionary/schema.py:27)

## Input And Parsing State

The system also needs input/parsing state.

This is better modeled as:

- current input source/buffer
- parse cursor / current offset

than as just "the current token."

Why:

- parsing words consume more than their own names
- `WORD`, `'`, `[COMPILE]`, `[']`, `CREATE`, `S"`, and similar words all depend on the
  current parse position
- token interpretation and compile-time behavior both depend on this layer

This state is conceptually required even though it is not yet first-class in the
current package schema.

## `current_xt` Versus `ip`

These are related, but they should not be collapsed.

### `current_xt`

`current_xt` is:

- the word currently being dispatched/interpreted/executed

This is the natural bridge to the family model:

- `current_xt` identifies the current word
- `handler_id` explains the shared runtime behavior associated with that word

### `ip`

`ip` is:

- the current position in the active thread

This is the state that matters when execution is walking a thread of words and inline
operands.

So:

- `current_xt` is current-word identity
- `ip` is current-thread position

These often move together, but they are not the same thing.

That matters because:

- interpret mode may have a meaningful `current_xt` without a meaningful thread `ip`
- threaded execution may need both
- inline-operand words like `LIT`, `BRANCH`, `0BRANCH`, and `LITSTRING` depend on `ip`
  or an equivalent current-thread pointer

## What Already Exists Versus What Is Still Implicit

Already explicit in current package/runtime state:

- `LATEST`
- `HERE`
- `STATE`
- data-stack pointer (`sp`)
- return-stack pointer (`rsp`)

Still mostly implicit / not yet first-class package state:

- input source and parse cursor
- `current_xt`
- `ip`
- fault / exception channel distinct from `STATE`

That is fine for now. This doc is meant to make the missing pieces explicit before
later execution work bakes in accidental assumptions.

## Minimal Invariant Set

Any future execution strategy should preserve these invariants:

1. `LATEST` remains the head of the newest-first dictionary chain.
2. `HERE` remains the write frontier for dictionary/build memory.
3. `STATE` remains a narrow interpret/compile mode signal.
4. Data-stack and return/control-stack roles remain distinct.
5. `current_xt` remains distinguishable from `ip`.
6. Inline operands are recovered relative to the current thread position, not by
   pretending they are word-local `DFA` payload.
7. Input/parsing state remains distinct from runtime thread position.
8. Dispatch strategy may vary without forcing a different handler ABI.

## What This Document Still Leaves Open

This document does not yet decide:

- the exact representation of `current_xt`
- the exact representation of `ip`
- whether `ip` lives in explicit runtime state or in executor-local state
- how input source/cursor should be stored
- how fault/exception state should be represented
- exact stack-pointer growth conventions
- exact uniform handler signature shape in package/runtime code
- exact `EXECUTE` lowering

Those are the next layer of Step 4 work.

## Immediate Next Questions

The next useful questions for this workstream are:

1. Where should `current_xt` and `ip` live in package/runtime design?
2. What exact input-source / parse-cursor model do we want?
3. What fault/exception state, if any, should exist separately from `STATE`?
4. What exact invariants must `EXECUTE` preserve across handlers and associated-data
   sources?
5. How much associated-data-source metadata should live in family descriptors versus a
   richer handler registry?

This should be answered before any final execution form is chosen.
