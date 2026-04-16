# Word Family Contract

This document is the Step 3 workstream from
[Forth Implementation Alignment Report](/Users/manny/fythvm/docs/references/forth/forth-implementation-alignment-report.md:1):
define the word-family abstraction more explicitly.

The dictionary contract settled what a dictionary entry is structurally. This document
is about what a dictionary entry *is a member of* semantically.

In other words:

- `docs/dictionary-contract.md` decides the common entry shape
- `docs/word-family-contract.md` decides how different kinds of words share behavior
  and differ in payload interpretation

## Why This Is The Next Workstream

The repo is now past the stage where the main uncertainty is dictionary storage.

We already have:

- a settled dictionary contract
- schema as source of truth
- generated layout
- runtime dictionary behavior
- IR-side dictionary helpers

What is still underspecified is the next layer up:

- how `instruction` should be interpreted as shared behavior
- how payload interpretation attaches to that behavior
- how native/builtin words, colon-defined words, and later defining-word-like words
  should be modeled without becoming ad hoc special cases

This is exactly where JonesForth's concrete codeword behavior and Moving Forth's
code-field / parameter-field theory meet most productively.

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
- the remaining question is how to represent shared behavior and payload semantics
  above that shared structure

## Working Definition

A **word family** is the shared execution-and-payload interpretation attached to a
dictionary entry.

More concretely:

- a dictionary entry always has the common structure from
  [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
- the `CodeField` selects a shared behavior
- the data after `DFA` is interpreted according to that shared behavior

So a word family answers questions like:

- what does `instruction` mean for this word?
- what does the payload after `DFA` contain?
- what helper should construct this kind of word?
- what helper should execute or otherwise interpret this kind of word later?

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
- where the payload begins

Those are already settled by the dictionary contract.

## What Varies Across Families

What can vary is:

- which primitive instruction id is stored in `CodeField.instruction`
- what the payload after `DFA` contains
- what construction helper writes that payload
- what execution helper later interprets that payload

This is the actual family boundary.

## Current Minimal Model In `fythvm`

The current repo already implies a minimal family model:

- `CodeField.instruction` is a primitive Forth-system instruction id
- that id is intended to index a jump table / dispatch table later
- colon-defined words would use the primitive id for `DOCOL`

So the system already has one important semantic decision:

- `instruction` is a **shared behavior selector**

What is still missing is making that explicit in package design instead of leaving it
as an implicit reading of one field.

## Concrete `~/fyth` Direction

The older `~/fyth` work gives a sharper practical picture of what this family model was
trying to be.

The important remembered direction is:

- primitive Forth words were represented by integers
- those integers were indexes into a jump table
- most primitive words had no meaningful payload after `DFA`
- some special behaviors did use payload after `DFA`

The most important special cases were:

- `DOCOL`
  - the instruction id selected colon-definition behavior
  - the payload after `DFA` was the thread / sequence to execute
- `LIT`-style behavior
  - the instruction id selected literal-handling behavior
  - the payload after `DFA` carried the inline literal data
- a specific primitive for invoking non-primitives
  - the primitive selected "call this other thing" behavior
  - the payload after `DFA` was the thing to invoke

So the practical model was not:

- every word has a large family-specific payload

It was closer to:

- most primitive/native words are just behavior selectors
- only some families need payload after `DFA`
- colon/threaded behavior and literal-bearing behavior are the canonical examples

That is useful because it makes the family model less abstract. It suggests a very
reasonable first package-level split:

- payload-empty primitive families
- payload-bearing primitive families
- colon/thread families

It also sharpens one important design constraint:

- the word-family abstraction should not assume that every family has meaningful
  payload after `DFA`
- it should allow the common case to be:
  - selector only
  - no payload interpretation needed

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
- switch on the primitive instruction id
- dispatch behavior from there

This is a different execution form, but it uses the same family selector in
`CodeField.instruction`.

### Why That Matters Here

These two directions differ in execution form, but they agree on the family contract:

- `instruction` selects shared behavior
- some behaviors need no payload
- some behaviors interpret data after `DFA`

That is exactly why this workstream should stop at the family boundary and not choose
the execution mechanism yet.

## Initial Family Candidates

These are the first meaningful families the repo should reason about.

### 1. Primitive / Native Family

Meaning:

- `instruction` selects a primitive behavior implemented directly by the execution
  substrate

Payload:

- usually empty
- sometimes small family-specific metadata when needed

Examples:

- arithmetic primitives
- stack operators
- memory primitives
- host/runtime bridge primitives

This is now the clearest default family in the model.

### 2. Colon-Defined Family

Meaning:

- `instruction` selects `DOCOL`-style behavior

Payload:

- a sequence / thread of word references and inline operands after `DFA`

This is the first family that turns the dictionary from a symbol table into a proper
threaded language substrate.

This is also the clearest example of a payload-bearing family.

### 3. Payload-Bearing Primitive Families

Meaning:

- `instruction` still selects a primitive/shared behavior
- but that behavior interprets data after `DFA`

Examples:

- `LIT`-style behavior
- a primitive that invokes some non-primitive target
- later special control/data-bearing primitives

This matters because it prevents the model from collapsing into a false dichotomy of:

- primitives have no payload
- non-primitives have payload

The old `~/fyth` direction suggests that some primitives do have meaningful payload,
just not most of them.

### 4. Defining-Word-Produced Families

Meaning:

- `instruction` selects a shared action for a family produced by some defining word

Payload:

- family-specific data after `DFA`

Examples in classic Forth terms:

- constants
- variables
- values
- `DOES>`-like products

This is the family layer JonesForth and Moving Forth both argue is fundamental.

## Immediate Design Questions

These are the concrete questions this workstream needs to settle.

### A. How Should Family Identity Be Represented In Package Code?

Options include:

- keep family meaning implicit in raw `instruction` ids only
- define named package-level family descriptors
- define a registry mapping `instruction` ids to family descriptors

Current recommendation:

- move toward named package-level family descriptors
- keep the raw integer id as the stored `CodeField` representation
- avoid leaving family meaning as comments and gut feel only
- the first useful named grouping probably looks like:
  - payload-empty primitive
  - payload-bearing primitive
  - colon/thread
  - defining-word-produced

### B. Where Should Payload Interpretation Live?

It should not live:

- in ad hoc callers
- in scattered runtime conditionals
- or only in future executor code

Current recommendation:

- family-specific helpers should own payload interpretation
- the package should make it explicit which helper interprets the payload for a given
  family
- it should be valid for a family helper to say:
  - this family has no payload after `DFA`

### C. How Should Construction Work?

The runtime and IR layers should not have to know every family's details inline.

Current recommendation:

- common dictionary creation mechanics remain shared
- family-specific construction should be layered on top of that shared machinery
- the family abstraction should say what gets written after `DFA`
- many primitive families should not need to write anything after `DFA`

### D. How Should Observability Work?

The repo has consistently favored:

- explicit Python observability
- explicit IR/codegen projections

Current recommendation:

- each family should have readable runtime/IR helper surfaces
- payload interpretation should be inspectable in both Python and IR terms
- family behavior should not become opaque just because execution is deferred

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

- treat `instruction` as the stored selector for a word family
- make word families explicit in package design
- keep construction and payload interpretation attached to families, not scattered
- do not force execution-form decisions into this workstream
- let the default case be a payload-empty primitive family
- treat `DOCOL` and `LIT`-style behaviors as the first clear payload-bearing cases

That gives us a cleaner bridge from:

- dictionary structure

to:

- later execution

without conflating the two.

## Decision Checklist

This is the order this workstream should walk through.

1. Confirm that `instruction` is the stored family selector.
2. Decide the first named family set the package should recognize.
3. Decide how family descriptors are represented in package code.
4. Decide how family-specific payload interpretation is attached.
5. Decide how family-specific construction helpers should layer on top of the shared
   dictionary machinery.
6. Only after that, write the execution-invariants document that any future engine
   must satisfy.

## Recommended Next Concrete Work

If we continue immediately from this document, the next most useful work is:

1. define the first package-level family descriptors
2. map current known `instruction` meanings onto those descriptors
3. add readable runtime/IR helpers for family-specific payload interpretation
4. then write `docs/execution-invariants.md`

The current notes suggest the first concrete descriptor set should probably be:

1. payload-empty primitive family
2. payload-bearing primitive family
3. `DOCOL` / colon-thread family
4. defining-word-produced family

That should give `fythvm` a clean bridge from:

- common dictionary structure

to:

- future execution work

without forcing a premature choice of execution mechanism.
