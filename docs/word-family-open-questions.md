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
- some primitive families can still be payload-bearing
  - `LIT`-style behavior
  - a primitive that invokes some non-primitive target
- the approved initial family set is:
  - payload-empty primitive
  - payload-bearing primitive
  - colon-thread

So the current workstream is no longer trying to answer whether word families exist.
It is trying to make them more useful and actionable in package code without blurring
them together with neighboring concerns.

One thing is now explicitly *not* open:

- instruction categories such as stack/arithmetic/memory are not a second family system
- they are organizational metadata on concrete instructions

## Current Open Questions

### 1. What Exactly Belongs To The Family Layer?

The package now has:

- named family descriptors
- a registry mapping handler ids to those descriptors
- raw `handler_id` values still stored in `CodeField`

So the first remaining question is no longer the base package shape. It is the
boundary between:

- family semantics
- operand-location semantics
- compile-time behavior

`LIT` is the clearest sign this matters:

- it is runtime behavior selected by a handler
- it consumes inline execution-stream data
- that is not the same as word-local data after the `LIT` word's own `DFA`

So the first open question is:

- what belongs to the family layer versus adjacent layers?

## 2. How Should Operand Location Be Modeled?

Once the family boundary is cleaner, the next question is whether operand location
becomes:

- a second explicit model axis
- or something attached to families in a more constrained way

The important distinctions are:

- no additional associated data
- word-local data after the word's own `DFA`
- inline operands in the active execution stream

## 3. Where Should Family-Owned Helper APIs Live?

Only after the first two questions are clarified does the earlier "payload
interpretation API" question become well-scoped.

At that point the real question becomes:

- how should family/operand helpers be exposed in Python and IR?

## 4. How Should Family-Specific Construction Layer On Top Of Shared Dictionary Creation?

We already have:

- shared dictionary creation mechanics
- canonical fixed prefix
- canonical `CodeField`
- `DFA` boundary helpers

What is still open is how family-aware constructors should sit on top of that:

- one constructor per family?
- one registry-driven builder?
- some smaller set of shared helper patterns?

This question should be answered only after the family/operand split is clearer.

## 5. How Far Should The Broader Family Layer Be Made Explicit Now?

The approved core set is settled, but the broader conceptual layer is still a timing
question.

The important follow-on families are:

- shared field-interpreter families
- defining-word-produced families

What is still open is:

- whether to represent those explicitly in package code now
- or first land the approved three-family core and return to the broader layer after that

## 6. What Exact Handoff Should This Workstream Make To Execution Invariants?

This workstream should not choose execution form.

But it does need to hand off a clear family model to the next workstream so the later
execution doc can answer:

- what `EXECUTE` must preserve
- how current-word identity is maintained
- how payload boundaries are recovered
- how data-stack and return/control-stack roles interact with family behavior

So one open question is really about sequencing:

- what is the minimal family model that must be explicit before
  `docs/execution-invariants.md` can be written cleanly?

## Short Version

The current Step 3 workstream is mainly about:

- defining the family boundary cleanly
- deciding how operand location is modeled
- then attaching family/operand helper APIs
- family-aware constructors
- how explicit the broader family layer should become right now
- clean handoff to execution invariants

## Suggested Review Order

If reviewing this away from the codebase, the most useful order is:

1. define the boundary between family semantics, operand location, and compile-time behavior
2. decide how operand location is modeled
3. decide how family/operand helper APIs should work
4. decide how family-aware construction works
5. decide how much of the broader family layer to model now
6. then write the execution-invariants document
