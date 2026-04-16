# Execution Invariants

This document is the canonical execution-state and handler-ABI contract for `fythvm`.

It defines:

- the uniform-handler direction
- the core machine-state model
- runtime associated-data-source recovery
- the separation between handler ABI and dispatch form

It does **not** choose:

- indirect threading vs loop-and-switch
- tail-call dispatch vs central dispatch loop
- exact host/runtime lowering strategy

For neighboring contracts, see:

- [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
- [docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)
- [docs/handler-requirements.md](/Users/manny/fythvm/docs/handler-requirements.md:1)

## Uniform Handler Surface

Current direction:

- runtime handlers share one uniform logical surface over one machine state
- runtime differences are primarily about:
  - what state a handler reads or writes
  - where its associated data comes from
  - how it continues dispatch
- dispatch form is separate from handler ABI

Consequences:

- execution should not be designed around family-specific handler ABIs
- runtime families do not justify different primitive/runtime signatures
- handler-local lowering contracts may vary by declared requirements without changing
  handler ABI

This matches the practical direction already visible in `~/fyth` and the dispatch labs:

- uniform builtin/handler shape
- dispatch strategy varied independently
- CFG rewriting, `musttail`, and loop dispatch were continuation mechanics, not family
  ABI definitions

## Core Execution State

The current best machine-state model is:

- `LATEST`
  - head of the newest-first dictionary chain
- `HERE`
  - current write cursor into dictionary memory
- `STATE`
  - interpret/compile mode
- `DATA_STACK_PTR`
  - current data-stack pointer
- `RETURN_STACK_PTR`
  - current return/control-stack pointer
- input source and parse cursor
  - the current token source plus the current parse position
- `current_xt`
  - the word currently being dispatched
- `ip`
  - the current position in the active thread

This is a semantic model, not yet a final storage layout.

## Associated Data Sources

The current runtime split is:

- `NONE`
  - the handler needs no associated runtime data beyond machine state
- `WORD_LOCAL_DFA`
  - associated data is recovered via `current_xt -> DFA`
- `INLINE_THREAD`
  - associated data is recovered from `ip` in the active thread

Examples:

- `primitive-empty`
  - `NONE`
- `colon-thread`
  - `WORD_LOCAL_DFA`
- `LIT`, `BRANCH`, `0BRANCH`, `LITSTRING`
  - `INLINE_THREAD`

This is the canonical replacement for the older vague idea of “payload” as one bucket.

## Parse-Time Input Is Separate

Parse-time/token data is not one of the runtime associated-data sources above.

It belongs to interpreter/compiler input state:

- input source / buffer
- parse cursor / current offset

This distinction matters because:

- compiler/meta words consume parse-time input state
- runtime inline-operand words consume thread state

That boundary should stay explicit.

## `current_xt` Versus `ip`

These are related, but not interchangeable.

- `current_xt`
  - current-word identity
- `ip`
  - current-thread position

This matters because:

- interpret mode may have a meaningful `current_xt` without a meaningful thread `ip`
- threaded execution may need both
- inline-operand handlers depend on `ip`, not just on `current_xt`

## Handler Requirements Are Neighboring, Not Foundational

The neighboring `HandlerRequirements` layer exists to describe:

- stack ingress/egress requirements
- injected resources like `ip`, `current_xt`, input source, error exit, dictionary, and
  `HERE`
- optional shared kernel lookup

But it does **not** replace:

- machine state
- runtime families
- associated-data source

That neighboring contract lives in:

- [docs/handler-requirements.md](/Users/manny/fythvm/docs/handler-requirements.md:1)

## Stable Invariants

These points should be treated as the current stable execution invariants:

1. `LATEST` remains the head of the newest-first dictionary chain.
2. `HERE` remains the write frontier for dictionary/build memory.
3. `STATE` remains a narrow interpret/compile mode signal.
4. Data-stack and return/control-stack roles remain distinct.
5. `current_xt` remains distinguishable from `ip`.
6. Inline operands are recovered relative to the current thread position.
7. Parse-time input state remains distinct from runtime thread state.
8. Dispatch strategy may vary without forcing a different handler ABI.

## Open Points

### 1. Exact Representation Of `current_xt` And `ip`

The concepts are settled. The remaining question is their final package/runtime
representation.

### 2. Exact Input-Source / Parse-Cursor Model

The need is settled. The remaining question is concrete representation.

### 3. Separate Fault / Exception State

If fault state exists later, it should be represented separately from `STATE`.

The remaining question is:

- whether that needs to become explicit before real executor work starts

### 4. Exact `EXECUTE` Invariants

The broad direction is settled, but later work still has to specify exactly what
`EXECUTE` must preserve across:

- handlers
- associated-data sources
- dispatch strategies

### 5. What Metadata Needs To Be First-Class Before Real Lowering Work Starts?

The remaining sequencing question is:

- how much associated-data-source and `HandlerRequirements` metadata should become
  first-class before package/runtime code tries to lower handlers declaratively
