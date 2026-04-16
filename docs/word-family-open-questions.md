# Word Family Open Questions

This document is a short companion to
[docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1).

The contract document captures the direction of the workstream. This file is the
smaller review artifact: what is still open right now, in plain terms, without the
extra framing.

## What Is Already Settled

These points are no longer the real questions:

- `handler_id` is the stored family selector
- native and later-defined words share one dictionary contract
- many primitive words likely have no additional associated data
- `DOCOL` is the clearest word-local `DFA` case
- some primitive families consume inline thread operands
  - `LIT`
  - `BRANCH`
  - `0BRANCH`
  - `LITSTRING`
- the approved initial family set is:
  - primitive-empty
  - primitive-inline-operand
  - colon-thread

JonesForth's minimum self-hosting substrate also gives us a stronger negative result:

- `STATE` plus `IMMEDIATE` plus explicit compiler/meta words are enough to bootstrap the
  self-hosted layer
- so a separate `compiling` bit is not justified just by the existence of compilation

So the current workstream is no longer trying to answer whether word families exist.
It is trying to make them more useful and actionable in package code without blurring
them together with neighboring concerns.

Directionally, the center of gravity has shifted again:

- the main execution abstraction is now a uniform handler surface over one machine
  state
- the family layer remains useful, but as metadata around that surface rather than as
  the main execution-shape abstraction

One thing is now explicitly *not* open:

- instruction categories such as stack/arithmetic/memory are not a second family system
- they are organizational metadata on concrete instructions

## Current Open Questions

### 1. What Metadata Do We Need Around A Uniform Handler Surface?

The package now has:

- named family descriptors
- a registry mapping handler ids to those descriptors
- raw `handler_id` values still stored in `CodeField`

So the first remaining question is no longer the base package shape. It is the
boundary between:

- family semantics
- associated-data-source semantics
- compile-time behavior

`LIT` is the clearest sign this matters:

- it is runtime behavior selected by a handler
- it consumes inline thread data
- that is not the same as word-local data after the `LIT` word's own `DFA`

So the first open question is:

- what metadata belongs on the uniform handler surface versus adjacent layers?

The compile-time side of that adjacent-layer question now has its own focused artifact:

- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)

Current stronger constraint:

- runtime family should stay narrow and explain runtime handler behavior only
- compile-time behavior should stay on the `STATE` / `IMMEDIATE` / compiler-meta side

## 2. Should Associated-Data Source Become A First-Class Package Type?

Once the family boundary is cleaner, the next question is whether associated-data
source becomes:

- a second explicit model axis
- or something attached to families in a more constrained way

The important distinctions are:

- `NONE`
- `WORD_LOCAL_DFA`
- `INLINE_THREAD`

The current leading candidate is:

- treat associated-data source as explicit metadata around uniform handlers, rather
  than as something implied only by family labels
- keep parse-time/token input source outside that runtime axis

## 3. How Much Of That Metadata Belongs On Families Versus A Richer Handler Registry?

The current docs already imply two layers:

- family descriptors
- concrete handler ids / handler registries

The open question is how much associated-data-source and helper metadata should live:

- directly on families
- or on a richer per-handler registry layered over families

## 4. What Should Helper APIs Expose?

Only after the first few questions are clarified does the earlier "payload
interpretation API" question become well-scoped.

At that point the real question becomes:

- how should handler/metadata helpers be exposed in Python and IR?

This likely now means helpers around:

- `current_xt -> DFA`
- `ip`
- parse-time input source

## 5. How Should Family-Specific Construction Layer On Top Of Shared Dictionary Creation?

We already have:

- shared dictionary creation mechanics
- canonical fixed prefix
- canonical `CodeField`
- `DFA` boundary helpers

What is still open is how family-aware constructors should sit on top of that:

- one constructor per family?
- one registry-driven builder?
- some smaller set of shared helper patterns?

This question should be answered only after the family/metadata split is clearer.

## 6. How Far Should The Broader Family Layer Be Made Explicit Now?

The approved core set is settled, but the broader conceptual layer is still a timing
question.

The important follow-on families are:

- shared field-interpreter families
- defining-word-produced families

What is still open is:

- whether to represent those explicitly in package code now
- or first land the approved three-family core and return to the broader layer after that

## 7. What Exact Minimal Metadata Is Needed Before The Execution Doc Can Be Deepened?

This workstream should not choose execution form.

But it does need to hand off a clear metadata model to the next workstream so the later
execution doc can answer:

- what `EXECUTE` must preserve
- how current-word identity is maintained
- how associated-data boundaries are recovered
- how data-stack and return/control-stack roles interact with family behavior

So one open question is really about sequencing:

- what is the minimal handler/metadata model that must be explicit before
  [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)
  can be deepened cleanly?

## Short Version

The current Step 3 workstream is mainly about:

- defining the boundary between family metadata and neighboring layers
- deciding how associated-data source is modeled
- keeping compile-time behavior out of the runtime family model
- then attaching handler/metadata helper APIs
- family-aware constructors
- how explicit the broader family layer should become right now
- clean handoff to execution invariants

Current handoff target:

- [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)

## Suggested Review Order

If reviewing this away from the codebase, the most useful order is:

1. define the boundary between family semantics, associated-data source, and compile-time behavior
2. decide how associated-data source is modeled
3. decide how much of that metadata belongs on families versus a richer handler registry
4. decide what handler/metadata helper APIs should expose
5. decide how family-aware construction works
6. decide how much of the broader family layer to model now
7. then deepen the execution-invariants document
