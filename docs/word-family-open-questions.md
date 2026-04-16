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

So the current workstream is no longer trying to answer whether word families exist.
It is trying to make them explicit and usable in package code.

## Current Open Questions

### 1. What Are The First Named Family Descriptors?

The current leading candidate set is:

- payload-empty primitive
- payload-bearing primitive
- `DOCOL` / colon-thread
- defining-word-produced

This direction is strong, but it is not yet locked into package code.

## 2. How Should Family Identity Live In Package Code?

Options still include:

- raw `instruction` ids only
- named descriptors plus raw ids
- a registry mapping instruction ids to descriptors

Current direction:

- keep the raw integer id as the stored representation
- move toward named package-level family descriptors

What is still open is the exact package shape.

## 3. How Should Payload Interpretation Be Attached?

The important question is where the logic lives that says:

- this family has no payload after `DFA`
- this family has a thread after `DFA`
- this family has inline literal data after `DFA`
- this family interprets `DFA` some other way

Current direction:

- family-specific helpers should own payload interpretation

What is still open is the exact API boundary.

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

## 5. Which Primitive Families Are Actually Payload-Bearing?

The direction is now much narrower than before:

- most primitives are probably payload-empty
- the first payload-bearing cases likely include:
  - `DOCOL`
  - `LIT`-style behavior
  - a primitive that invokes some non-primitive target

What is still open is whether those should become the canonical initial list in code.

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

- first family descriptor set
- package representation / registry shape
- family-owned payload interpretation
- family-aware constructors
- exact list of payload-bearing primitive families
- clean handoff to execution invariants

## Suggested Review Order

If reviewing this away from the codebase, the most useful order is:

1. decide the first family descriptor set
2. decide how family descriptors should exist in package code
3. decide how payload interpretation is attached
4. decide how family-aware construction works
5. then write the execution-invariants document
