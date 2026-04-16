# Word Family Contract

This document is the Step 3 workstream from
[Forth Implementation Alignment Report](/Users/manny/fythvm/docs/references/forth/forth-implementation-alignment-report.md:1):
define the word-family abstraction more explicitly.

The dictionary contract settled what a dictionary entry is structurally. This document
is about what a dictionary entry *is a member of* semantically.

In other words:

- `docs/dictionary-contract.md` decides the common entry shape
- `docs/word-family-contract.md` decides how different kinds of words share runtime
  behavior without collapsing neighboring concerns into the same model

## Why This Is The Next Workstream

The repo is now past the stage where the main uncertainty is dictionary storage.

We already have:

- a settled dictionary contract
- schema as source of truth
- generated layout
- runtime dictionary behavior
- IR-side dictionary helpers
- package-level family descriptors and an instruction-to-family registry

What is still underspecified is the next layer up:

- how far the package should go beyond the initial family descriptors
- how family behavior relates to associated-data source and compile-time behavior
- how native/builtin words, colon-defined words, and later defining-word-like words
  should be modeled without becoming ad hoc special cases

The current working direction for that layer is now sharper:

- runtime execution should be understood as a uniform handler surface over one machine
  state
- runtime families remain useful, but as metadata and semantic grouping around that
  surface
- family categories should not be treated as executor call-shape categories

This is exactly where JonesForth's concrete codeword behavior and Moving Forth's
code-field / parameter-field theory meet most productively.

The compile-time side of that discussion now has its own neighboring artifact:

- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)

The declarative helper/lowering side of that discussion now also has its own
neighboring artifact:

- [docs/handler-requirements.md](/Users/manny/fythvm/docs/handler-requirements.md:1)

## Relationship To The Dictionary Contract

The dictionary contract already settled these points:

- one linked newest-first dictionary
- one common fixed prefix
- `CodeField` as the canonical metadata cell
- `xt == CFA == address of CodeField`
- `DFA == address immediately after the fixed prefix`
- same dictionary contract for native and later-defined words

So this document starts from a stronger base:

- the dictionary does not need to be split into different structural entry kinds
- the remaining question is how to represent shared runtime behavior and its relation
  to adjacent semantics
  above that shared structure

## Working Definition

A **word family** is the shared runtime behavior selected by a dictionary entry's
`CodeField.handler_id`.

More concretely:

- a dictionary entry always has the common structure from
  [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
- the `CodeField` selects a shared behavior
- that shared behavior is not, by itself, the full explanation of:
  - where associated data lives
  - how compile-time behavior works

So a word family answers questions like:

- what does `handler_id` mean for this word?
- what runtime behavior does this word share with other words?
- what helper should eventually execute or otherwise interpret this kind of word later?

It does **not** automatically answer:

- whether relevant data lives after the word's own `DFA`
- whether relevant data is an inline operand in the active thread
- whether the word has immediate or compile-affecting behavior

JonesForth's minimum self-hosting substrate makes this boundary clearer. The words that
must already exist in order for the self-hosted layer to grow include:

- `NEXT`, `DOCOL`, `EXIT`, `EXECUTE`
- `WORD`, `FIND`, `INTERPRET`
- `STATE`, `IMMEDIATE`, `[`, `]`
- `CREATE`, `,`, `:`, `;`
- `LIT`, `BRANCH`, `0BRANCH`, `LITSTRING`
- plus the ordinary primitive base:
  - stack words
  - arithmetic/comparison/bitwise words
  - memory words
  - return/data stack access
  - basic I/O
  - `LATEST`, `HERE`, `>CFA`
  - `CHAR`

The fuller JonesForth-specific breakdown now lives in:

- [docs/references/forth/jonesforth/implementation-report.md](/Users/manny/fythvm/docs/references/forth/jonesforth/implementation-report.md:55)

That minimum set is useful because it shows which distinctions are already required just
to bootstrap:

- runtime handlers like `DOCOL`, `LIT`, `BRANCH`, `0BRANCH`, and `LITSTRING`
- compile-mode dispatch via `STATE` and `IMMEDIATE`
- compiler/meta words that build definitions

This strongly suggests that runtime family should stay narrow and should not try to
absorb compile-time behavior.

## Families Do Not Define Handler ABI

The current recommended direction is:

- runtime handlers should share one uniform logical signature over machine state
- families do not justify different primitive/runtime signatures
- execution design should not start from family-specific ABI assumptions

So the family layer is useful for:

- shared runtime semantics
- associated-data-source expectations
- construction and inspection helpers
- declaring the semantic grouping that richer handler metadata can build on
- registries, debugging, and documentation

It is **not** the reason to vary:

- handler ABI
- executor entry shape
- dispatch calling convention

This matches the direction already visible in `~/fyth`:

- one uniform builtin/handler shape
- dispatch strategy varied independently
- CFG rewriting, `musttail`, and loop dispatch were continuation mechanics, not family
  ABI definitions

## What Is Common Across Families

All word families should share:

- newest-first linked dictionary membership
- the same visibility rules
- the same name/prefix/payload boundary rules
- `xt` / `CFA` / `DFA` semantics
- lookup and shadowing semantics

This means the family abstraction should not re-decide:

- how names are stored
- where the link lives
- where `CodeField` lives
- where the word's own `DFA` begins

Those are already settled by the dictionary contract.

## What Varies Across Families

What can vary is:

- which execution handler id is stored in `CodeField.handler_id`
- what shared runtime behavior that handler selects
- what helper eventually executes or otherwise interprets that behavior

What does **not** yet belong solely to the family layer is:

- whether associated data is word-local after the word's own `DFA`
- whether associated data is an inline operand in the active thread
- whether the word has compile-time / immediate behavior

Those are adjacent axes that still need to be modeled cleanly.

## Three Separate Axes

The current underspecification is that three different concerns are easy to blur if we
only say "family" and "payload."

### 1. Runtime Family

This is the family layer proper:

- what shared runtime behavior does `handler_id` select?
- examples:
  - primitive-empty behavior
  - primitive behavior that consumes inline thread operands
  - `DOCOL` / colon-thread behavior

Given the JonesForth substrate above, the strongest current runtime split is:

- `primitive-empty`
- `primitive-inline-operand`
- `colon-thread`

`primitive-payload` was a useful transitional name, but the more precise pressure from
JonesForth is specifically around inline operands in the current thread:

- `LIT`
- `BRANCH`
- `0BRANCH`
- `LITSTRING`

### 2. Data Location And Interpretation

This is separate from family and still needs clearer modeling:

- no extra associated data
- word-local data after the word's own `DFA`
- inline operands in the active thread

The stronger execution-oriented phrasing is:

- `NONE`
- `WORD_LOCAL_DFA`
- `INLINE_THREAD`

`DOCOL` is the clearest word-local case:

- the handler selects `DOCOL`-style behavior
- the word's own `DFA` begins the thread for that word

`LIT` is the clearest inline-operand case:

- the handler selects `LIT` behavior
- the literal is not stored in the `LIT` word's own dictionary entry
- the literal is the next inline cell in the active thread

So `LIT` is exactly why "payload after `DFA`" is too blunt as a general explanation.

This also lines up with the execution-state model:

- `WORD_LOCAL_DFA` is recovered via `current_xt -> DFA`
- `INLINE_THREAD` is recovered via `ip`

### 3. Compile-Time Behavior

This is also separate from family:

- immediate behavior
- compile-affecting behavior
- dictionary/compiler-state behavior

Examples:

- `IMMEDIATE`
- `[`
- `]`
- `CREATE`

JonesForth strongly supports keeping this separate:

- these are still ordinary words
- they do not require a different dictionary entry shape
- they should not automatically be treated as a separate runtime family just because
  they affect compilation

This is the actual family boundary.

For the compile-time side of the boundary, see:

- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)

## Instruction Categories Are Separate

The package may also carry **instruction categories** such as:

- stack
- arithmetic
- comparison/bitwise
- memory
- return/data stack control
- parser/I/O
- dictionary/compiler
- host bridge

These are **not** families.

They are organizational metadata for concrete instructions:

- useful for browsing
- useful for grouping implementations
- useful for inventory/reporting

But they do not answer the family questions:

- does this word share a runtime handler family?
- is this a primitive-empty, primitive-inline-operand, or colon-thread word?

So the rule is:

- **family** = semantic/runtime concern
- **instruction category** = organizational/package metadata

## Current Minimal Model In `fythvm`

The current repo already implies a minimal family model:

- `CodeField.handler_id` is the stored execution handler selector
- that id is intended to index a jump table / dispatch table later
- colon-defined words would use the primitive id for `DOCOL`

So the system already has one important semantic decision:

- `handler_id` is a **shared behavior selector**

That is now explicit in package design at the descriptor/registry level. What remains is
to decide how much more meaning should be attached there versus modeled on neighboring
axes.

The minimum JonesForth substrate makes one additional constraint especially clear:

- `STATE` and `IMMEDIATE` are already enough to explain a large part of compile-time
  behavior

So runtime families should not grow a compile-time taxonomy just because compile-
sensitive words exist.

The next strong refinement is:

- family metadata should support a uniform handler ABI
- associated-data source is the clearest next explicit axis
- richer handler registries may matter more than deeper family taxonomies

## Concrete `~/fyth` Direction

The older `~/fyth` work gives a sharper practical picture of what this family model was
trying to be.

The important remembered direction is:

- primitive Forth words were represented by integers
- those integers were indexes into a jump table
- most primitive words had no meaningful associated data beyond the behavior selector
- some special behaviors did use additional data, but not always in the same place

The most important special cases were:

- `DOCOL`
  - the handler id selected colon-definition behavior
  - the word's own `DFA` began the thread / sequence to execute
- `LIT`-style behavior
  - the handler id selected literal-handling behavior
  - the current thread carried the literal data inline
- a specific primitive for invoking non-primitives
  - the primitive selected "call this other thing" behavior
  - the associated operand/data location was still a separate question

So the practical model was not:

- every word has a large family-specific payload

It was closer to:

- most primitive/native words are just behavior selectors
- some behaviors use word-local data
- some behaviors use inline thread operands
- colon/threaded behavior and literal-bearing behavior are the canonical contrasting examples

That is useful because it makes the family model less abstract. It suggests a very
reasonable first package-level split:

- primitive-empty
- primitive-inline-operand
- colon-thread

It also sharpens one important design constraint:

- the word-family abstraction should not assume that every family has meaningful
  word-local payload after `DFA`
- it should allow the common case to be:
  - selector only
  - no payload interpretation needed
- and it should leave room for operand-location rules that are not the same as
  word-local `DFA` interpretation

## Execution-Shape Experiments Already Suggested By `~/fyth`

The old work also suggests two distinct execution directions that this family model
must eventually support.

### Tail-Called Primitive Dispatch

One direction was:

- each primitive ends in a tail call
- the execution substrate advances by chaining primitive calls directly

This is the direction behind the `musttail` / continuation work already noted in the
backlog and reference docs.

### Loop + Switch Primitive Dispatch

Another experimented direction was:

- return to a central loop
- switch on the primitive handler id
- dispatch behavior from there

This is a different execution form, but it uses the same family selector in
`CodeField.handler_id`.

### Why That Matters Here

These two directions differ in execution form, but they agree on the family contract:

- `handler_id` selects shared behavior
- some behaviors need no additional data
- some behaviors use word-local data
- some behaviors consume inline operands in the active thread

That is exactly why this workstream should stop at the family boundary and not choose
the execution mechanism yet.

## Approved Core Family Breakdown

The current core family breakdown is now considered approved.

The approved initial family set is:

1. **primitive-empty**
2. **primitive-inline-operand**
3. **colon-thread**

These are the first families the package should reason about explicitly.
They should be understood as a **behavior-level metadata split** over a uniform handler
surface, not a complete explanation of operand location, compile-time semantics, or
executor call shape.

### 1. Primitive-Empty

Meaning:

- `handler_id` selects a primitive behavior implemented directly by the execution
  substrate
- associated-data source is `NONE`

Payload:

- empty in the normal case

Examples:

- arithmetic primitives
- stack operators
- memory primitives
- host/runtime bridge primitives
- dictionary/compiler-control primitives like `IMMEDIATE`, `HIDDEN`, `[`, `]`, `'`

This is the default family in the model.

### 2. Primitive-Inline-Operand

Meaning:

- `handler_id` still selects a primitive/shared behavior
- but that behavior consumes operand data inline from the current thread
- associated-data source is `INLINE_THREAD`

Status:

- this is now the preferred name for the JonesForth cases like `LIT`, `BRANCH`,
  `0BRANCH`, and `LITSTRING`
- older `primitive-payload` / "payload-bearing primitive" wording should be understood
  as transitional phrasing, not the preferred contract vocabulary

Examples:

- `LIT`
- `BRANCH`
- `0BRANCH`
- `LITSTRING`
- possibly a primitive that invokes some non-primitive target later

This matters because it prevents the model from collapsing into a false dichotomy of:

- primitives have no associated operands
- non-primitives have associated operands

The older `~/fyth` direction and the JonesForth/Moving references all support this
behavior-level bucket as real and important, even though broader operand-location
questions still remain for later families.

### 3. Colon-Thread

Meaning:

- `handler_id` selects `DOCOL`-style behavior
- associated-data source is `WORD_LOCAL_DFA`

Payload:

- the word's own `DFA` begins a sequence / thread of word references and inline operands

This is the first family that turns the dictionary from a symbol table into a proper
threaded language substrate.

### 4. Generalized Families To Keep In View

The following are still important, but they are the next layer rather than the approved
minimal core.

#### Shared Field-Interpreter Families

Meaning:

- a shared behavior routine interprets per-word payload after `DFA`

Moving Forth examples:

- `DOCON`
- `DOVAR`
- `ENTER`
- `LIT`

These are better thought of as a broader conceptual family layer that may emerge once
the first three core families are explicit in package code. They are useful here as
reference pressure, not as proof that the current package model should collapse all of
their distinctions immediately.

#### Defining-Word-Produced Families

Meaning:

- `handler_id` selects a shared action for a family produced by some defining word

Payload:

- family-specific data after `DFA`

Examples in classic Forth terms:

- constants
- variables
- values
- `DOES>`-like products

This is the family layer JonesForth and Moving Forth both argue is fundamental, but it
does not need to be the first package-level implementation step.

## Immediate Design Questions

These are the concrete questions this workstream needs to settle.

### A. What Exactly Belongs To The Family Layer?

This is now the first unresolved question.

The docs and package code already have a useful family representation, but `LIT`
showed that we still need to separate:

- runtime family semantics
- operand/data-location semantics
- compile-time behavior

What remains open is the exact boundary between those layers.

### B. How Should Family Identity Be Represented In Package Code?

Options include:

- keep family meaning implicit in raw `handler_id` values only
- define named package-level family descriptors
- define a registry mapping `handler_id` values to family descriptors

Current status:

- named package-level family descriptors now exist
- the raw integer id remains the stored `CodeField` representation
- an instruction-to-family registry exists at the package level

What remains open is how much richer that representation should become before the
instruction set is nailed down.

### C. How Should Operand Location Be Modeled?

The current family descriptors are still useful, but they do not yet explain whether
associated data is:

- absent
- word-local after the word's own `DFA`
- inline in the active thread

What is still open is whether this becomes:

- a second explicit model axis
- or something attached to families in a narrower, more constrained way

### D. Where Should Handler Requirements And Helper APIs Live?

This question is now better stated as:

- where should concrete handler requirements and helper APIs live relative to family
  metadata?

It should not live:

- in ad hoc callers
- in scattered runtime conditionals
- or only in future executor code

Current recommendation:

- family-specific semantics should remain explicit
- operand-location rules should be explicit rather than implied
- concrete handler/lowering requirements should be modeled per handler, not implied
  only by family labels
- that neighboring layer should be recorded as:
  - [docs/handler-requirements.md](/Users/manny/fythvm/docs/handler-requirements.md:1)
- it should be valid for a requirements entry to say:
  - this handler needs no associated runtime data beyond machine state
  - this handler needs `current_xt -> DFA`
  - this handler needs `ip`
  - this handler needs parse-time input state
  - this handler needs error-exit, dictionary, or `HERE` access

### E. How Should Construction Work?

The runtime and IR layers should not have to know every family's details inline.

Current recommendation:

- common dictionary creation mechanics remain shared
- family-specific construction should be layered on top of that shared machinery
- construction should not assume every interesting case writes data after the word's
  own `DFA`
- many primitive families should not need to write anything after the word's own `DFA`

### F. How Should Observability Work?

The repo has consistently favored:

- explicit Python observability
- explicit IR/codegen projections

Current recommendation:

- each family should have readable runtime/IR helper surfaces
- operand-location rules should be inspectable in both Python and IR terms
- family behavior should not become opaque just because execution is deferred
- richer per-handler observability should flow through a requirements layer rather than
  through family labels alone

## What This Document Does Not Decide

This workstream does **not** decide:

- the final execution model
- the exact jump table shape
- return-stack mechanics
- compile/interpret loop behavior
- final `EXECUTE` lowering

Those belong to the later execution-invariants and execution-shape workstreams.

## Current Recommendation

The strongest current recommendation is:

- treat `handler_id` as the stored selector for a word family
- make word families explicit in package design as supporting metadata
- keep runtime family semantics explicit in package design without treating them as
  handler ABI categories
- do not force operand-location semantics or compile-time behavior into the family
  layer prematurely
- do not force execution-form decisions into this workstream
- let the default case be `primitive-empty`
- treat `primitive-inline-operand` and `DOCOL` / `colon-thread` as the first concrete
  special cases
- make associated-data source the clearest next explicit axis:
  - `NONE`
  - `WORD_LOCAL_DFA`
  - `INLINE_THREAD`
- make `HandlerRequirements` the clearest next helper/lowering axis:
  - stack ingress/egress requirements
  - injected resources like `ip`, `current_xt`, parse-time input, error exit,
    dictionary, and `HERE`
  - optional kernel lookup for shared lowering shapes
- treat the three approved core families as settled:
  - primitive-empty
  - primitive-inline-operand
  - colon-thread

That gives us a cleaner bridge from:

- dictionary structure

to:

- later execution

without conflating the two.

## Decision Checklist

This is the order this workstream should walk through.

1. Confirm that `handler_id` is the stored family selector.
2. Record the approved first family set in the package/docs.
3. Define the boundary between:
   - family semantics
   - associated-data-source semantics
   - compile-time behavior
4. Decide how associated-data source should be modeled:
   - `NONE`
   - `WORD_LOCAL_DFA`
   - `INLINE_THREAD`
   - and how much of that lives on family descriptors versus richer handler metadata
5. Define the neighboring `HandlerRequirements` layer:
   - stack ingress/egress requirements
   - injected machine-state resources
   - parse-time input requirements
   - optional kernel identity
6. Only after that, define family-aware construction helpers.
7. Only after that, deepen the execution-invariants document that any future engine
   must satisfy.

## Recommended Next Concrete Work

If we continue immediately from this document, the next most useful work is:

1. keep the current family descriptors, but make their current limits explicit
2. define the boundary between family semantics, associated-data source, and
   compile-time behavior
3. decide how associated-data source should be modeled
4. define the neighboring `HandlerRequirements` layer for concrete handlers/lowerings
5. then add readable runtime/IR helpers for the resulting family/metadata model
6. then deepen `docs/execution-invariants.md`

The current notes suggest the first concrete descriptor set should probably be:

1. `primitive-empty`
2. `primitive-inline-operand`
3. `DOCOL` / `colon-thread`

That initial set is now approved at the document level.

That should give `fythvm` a clean bridge from:

- common dictionary structure

to:

- future execution work

without forcing a premature choice of execution mechanism.
