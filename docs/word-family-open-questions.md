# Word Family Open Questions

This document is a short companion to
[docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1).

The contract document captures the direction of the workstream. This file is the
smaller review artifact: what is still open right now, in plain terms, without the
extra framing.

## What Is Already Settled

These points are no longer the real questions:

- `instruction` is the stored family selector
- native and later-defined words share one dictionary contract
- many primitive words likely have empty `DFA`
- `DOCOL` is the clearest payload-bearing family example
- some primitive families can still be payload-bearing
  - `LIT`-style behavior
  - a primitive that invokes some non-primitive target
- the approved initial family set is:
  - payload-empty primitive
  - payload-bearing primitive
  - colon-thread

So the current workstream is no longer trying to answer whether word families exist.
It is trying to make them more useful and actionable in package code.

## Current Open Questions

### 1. How Should Payload Interpretation Be Attached?

The package now has:

- named family descriptors
- a registry mapping instruction ids to those descriptors
- raw `instruction` ids still stored in `CodeField`

So the remaining question is no longer the base package shape. It is what richer
meaning should hang off that shape.

The important question is where the logic lives that says:

- this family has no payload after `DFA`
- this family has a thread after `DFA`
- this family has inline literal data after `DFA`
- this family interprets `DFA` some other way

Current direction:

- family-specific helpers should own payload interpretation

What is still open is the exact API boundary.

## 2. How Should Family-Specific Construction Layer On Top Of Shared Dictionary Creation?

We already have:

- shared dictionary creation mechanics
- canonical fixed prefix
- canonical `CodeField`
- `DFA` boundary helpers

What is still open is how family-aware constructors should sit on top of that:

- one constructor per family?
- one registry-driven builder?
- some smaller set of shared helper patterns?

## 3. How Far Should The Broader Family Layer Be Made Explicit Now?

The approved core set is settled, but the broader conceptual layer is still a timing
question.

The important follow-on families are:

- shared field-interpreter families
- defining-word-produced families

What is still open is:

- whether to represent those explicitly in package code now
- or first land the approved three-family core and return to the broader layer after that

## 4. What Exact Handoff Should This Workstream Make To Execution Invariants?

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

- family-owned payload interpretation
- family-aware constructors
- how explicit the broader family layer should become right now
- clean handoff to execution invariants

## Suggested Review Order

If reviewing this away from the codebase, the most useful order is:

1. decide how payload interpretation is attached
2. decide how family-aware construction works
3. decide how much of the broader family layer to model now
4. then write the execution-invariants document
