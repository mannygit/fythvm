# Word Family Contract

This document is the canonical runtime-family contract for `fythvm`.

It defines:

- what a runtime family is
- what belongs to family semantics versus neighboring layers
- the approved core family set
- the main remaining family-layer open points

It does **not** define:

- common dictionary entry structure
- compile-mode behavior
- final execution form

For those, see:

- [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)
- [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)
- [docs/handler-requirements.md](/Users/manny/fythvm/docs/handler-requirements.md:1)

## Core Contract

### Working Definition

A **word family** is the shared runtime behavior selected by a word’s
`CodeField.handler_id`.

A family answers questions like:

- what runtime behavior does this word share with other words?
- what kind of handler semantics does `handler_id` select?
- what kind of runtime interpretation should later helpers/executors apply?

A family does **not** by itself answer:

- where associated runtime data comes from
- how compile-time behavior works
- what runtime ABI shape handlers should have

### Families Do Not Define ABI

Runtime families are metadata, not handler-ABI categories.

Current direction:

- runtime handlers share one uniform logical surface over one machine state
- families do not justify different primitive/runtime signatures
- dispatch form is separate from family semantics

So the family layer is useful for:

- shared runtime semantics
- semantic grouping
- construction/inspection metadata
- registries, debugging, and documentation

It is **not** the reason to vary:

- handler ABI
- executor entry shape
- dispatch calling convention

That canonical statement lives at a higher level in:

- [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)

## Boundary With Neighboring Layers

The family boundary is easiest to keep clear by separating three axes.

### 1. Runtime Family

This is the family layer proper:

- what shared runtime behavior does `handler_id` select?

### 2. Associated-Data Source

This is separate from family:

- `NONE`
- `WORD_LOCAL_DFA`
- `INLINE_THREAD`

Examples:

- `DOCOL`
  - family behavior is colon-thread
  - associated-data source is `WORD_LOCAL_DFA`
- `LIT`
  - family behavior is primitive-inline-operand
  - associated-data source is `INLINE_THREAD`

This is why “payload after `DFA`” is too blunt as a general explanation.

### 3. Compile-Time Behavior

This is also separate from family:

- `STATE`
- `immediate`
- compile-only legality
- compiler/meta behavior

That canonical statement lives in:

- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)

## Approved Core Family Set

The approved initial family set is:

1. `primitive-empty`
2. `primitive-inline-operand`
3. `colon-thread`

These should be understood as a behavior-level split over a uniform handler surface.

### `primitive-empty`

Meaning:

- `handler_id` selects a primitive/shared runtime behavior
- associated-data source is normally `NONE`

Examples:

- arithmetic primitives
- stack operators
- memory primitives
- many runtime bridge/control primitives

### `primitive-inline-operand`

Meaning:

- `handler_id` still selects a primitive/shared runtime behavior
- that behavior consumes operand data inline from the current thread
- associated-data source is `INLINE_THREAD`

Examples:

- `LIT`
- `BRANCH`
- `0BRANCH`
- `LITSTRING`

### `colon-thread`

Meaning:

- `handler_id` selects `DOCOL`-style behavior
- associated-data source is `WORD_LOCAL_DFA`
- the word’s own `DFA` begins the thread for that word

## Why JonesForth Still Matters Here

JonesForth’s minimal self-hosting surface is useful because it shows what distinctions
already have to exist before the self-hosted layer grows.

The key takeaways are:

- runtime handlers like `DOCOL`, `LIT`, `BRANCH`, `0BRANCH`, and `LITSTRING` are real
- compile-mode dispatch via `STATE` and `IMMEDIATE` is already separate
- compiler/meta words build definitions on top of that substrate

So runtime family should stay narrow.

The fuller JonesForth-specific bootstrap breakdown lives in:

- [docs/references/forth/jonesforth/implementation-report.md](/Users/manny/fythvm/docs/references/forth/jonesforth/implementation-report.md:60)

## Relationship To `~/fyth`

The older `~/fyth` direction still usefully constrains this model.

The important remembered shape is:

- primitive words were behavior selectors
- most primitive/native words had no meaningful associated data beyond the selector
- some behaviors used word-local data
- some behaviors consumed inline thread operands

That direction supports:

- `primitive-empty`
- `primitive-inline-operand`
- `colon-thread`

It also supports the decision to keep family semantics separate from execution-shape
mechanics like tail-call dispatch versus loop-and-switch dispatch.

## Open Points

The remaining open questions for this layer are now fairly focused.

### 1. Should Associated-Data Source Become First-Class Package Metadata?

The current leading direction is yes, or at least “explicit metadata around handlers”
rather than something implied only by family labels.

The unresolved choice is:

- put it directly on family descriptors
- or put it in richer per-handler metadata layered over families

### 2. How Much Metadata Belongs On Families Versus A Richer Handler Registry?

Current direction:

- family descriptors should stay fairly small
- richer per-handler metadata should likely carry:
  - associated-data source
  - helper/lowering requirements
  - optional kernel identity

### 3. How Should `HandlerRequirements` Sit Next To Families?

Families and `HandlerRequirements` should remain separate.

The family doc owns:

- runtime semantic grouping

The requirements doc owns:

- stack ingress/egress requirements
- injected resources like `ip`, `current_xt`, input source, error exit, dictionary,
  and `HERE`
- kernel lookup role

That neighboring contract lives in:

- [docs/handler-requirements.md](/Users/manny/fythvm/docs/handler-requirements.md:1)

### 4. How Much Of The Broader Family Layer Should Be Made Explicit Now?

The next conceptual families still worth keeping in view are:

- shared field-interpreter families
- defining-word-produced families

But the current direction is:

- keep the approved core set explicit now
- do not broaden package-level family taxonomy until the handler metadata story is
  clearer

## Next Constraint From This Doc

The next family-adjacent step should be:

1. keep the approved core family set
2. make associated-data source explicit in package metadata or handler metadata
3. layer `HandlerRequirements` beside families, not inside them
4. only then deepen execution/lowering surfaces
