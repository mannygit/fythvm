# Dictionary Contract

This document is the Step 1 workstream from
[Forth Implementation Alignment Report](/Users/manny/fythvm/docs/references/forth/forth-implementation-alignment-report.md:1):
lock down dictionary invariants.

The name `Dictionary Contract` is intentional.

`Invariant` is close, but too passive. What we actually need is a contract between:

- schema and generated layout
- runtime construction and lookup
- future codegen/execution work
- future self-hosted or defining-word-like growth

This document is the place to decide what a dictionary entry *means* in `fythvm`, not
just how it is currently stored.

## Scope

This document focuses on these Step 1 decisions:

- newest-first link semantics
- hidden-word lookup behavior
- fixed prefix fields
- code/data boundary helpers
- name encoding and alignment rules

It does **not** decide:

- final execution/threading model
- full compile/interpret machinery
- defining-word execution semantics
- self-hosted growth strategy

Those later decisions should consume this contract, not redefine it.

## Why This Matters

Both major Forth references in this repo make dictionary structure central:

- JonesForth gives a concrete linked dictionary with flags, aligned names, and explicit
  code/data boundary helpers
  ([JonesForth report](/Users/manny/fythvm/docs/references/forth/jonesforth/implementation-report.md:1))
- Moving Forth explains the deeper code-field / parameter-field contract and why word
  families matter
  ([Moving Forth report](/Users/manny/fythvm/docs/references/forth/moving-forth-implementation-report.md:1))

If this contract stays fuzzy, later execution work will either:

- force rewrites in the dictionary runtime
- or quietly calcify accidental choices as architecture

## Current Implementation Snapshot

Current package code:

- schema:
  - [src/fythvm/dictionary/schema.py](/Users/manny/fythvm/src/fythvm/dictionary/schema.py:1)
- runtime:
  - [src/fythvm/dictionary/runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:1)
- generated IR layout:
  - [src/fythvm/dictionary/layout.py](/Users/manny/fythvm/src/fythvm/dictionary/layout.py:1)

Current dictionary entry shape in runtime terms:

1. A word name is encoded as:
   - one packed header byte
   - raw name bytes
   - zero padding to cell alignment
2. The fixed word prefix starts immediately after that aligned name blob.
3. The fixed prefix currently contains:
   - `link`
   - `code`
   - zero-length `data_start`
4. The data area begins immediately after the fixed prefix.

Current code points:

- `NameHeader.encode(...)`
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:47)
- aligned name size:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:52)
- word creation:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:196)
- newest-first traversal:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:235)
- hidden-word skipping:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:248)
- CFA/DFA helpers:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:180)

## Proposed Contract

This section is the current recommended contract for `fythvm`.

### 1. Dictionary Ordering

`latest` is the head of the dictionary chain.

Each word prefix stores a link to the previous visible history point in creation order.
Traversal is newest-first by following `link`.

This means:

- redefining a word shadows older definitions naturally
- lookup order is a property of the link chain, not of any auxiliary index
- historical order is preserved in the chain itself

### 2. Visibility Rule

`hidden` is a structural lookup flag, not only metadata.

If `hidden` is set on a word, normal dictionary lookup must skip that word.

This means:

- `find_word(...)` and equivalent lookup helpers are required to ignore hidden words
- hidden words may still be reachable by direct reference or explicit traversal
- visibility is part of the word contract, not UI sugar

This is already how the current runtime behaves
([runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:248)).

### 3. Fixed Prefix

The fixed prefix is the first stable cell-aligned structural record of a word.

Current prefix:

- `link: i32`
- `code: CodeField`
- `data_start: i32 * 0`

This is a good current shape because it makes three things explicit:

- chain linkage
- code/metadata flags
- data starts here

Recommended rule:

- the fixed prefix should remain the canonical anchor for code/data boundary
  calculations
- future additions to the prefix must be justified as stable word-family metadata, not
  transient runtime state

### 4. Code/Data Boundary Helpers

The dictionary contract should expose explicit helpers equivalent in spirit to classic
`>CFA` and `>DFA`, even if the naming stays more Pythonic.

Current helpers:

- `cfa_index`
- `dfa_index`

([runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:180))

Recommended rule:

- code/data boundary helpers are part of the public dictionary contract
- callers should not be expected to recompute offsets ad hoc
- code/data boundary derivation should remain explicit in both byte and cell terms when
  needed

### 5. Name Encoding

The word name is a byte protocol, not a normal struct field.

Current encoding:

- first byte packs:
  - `name_length`
  - `hidden`
  - `immediate`
- then raw name bytes
- then zero padding to cell alignment

([runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:20))

Recommended rule:

- name encoding remains a dedicated protocol layer
- it should not be forced into the fixed prefix just for convenience
- name semantics should remain recoverable from the prefix plus preceding byte blob

### 6. Alignment Rule

The name blob is aligned to cell size before the fixed prefix starts.

Current helper:

- `NameHeader.aligned_size(...)`
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:52)

Recommended rule:

- the fixed prefix must always begin at a cell-aligned boundary
- alignment math should stay centralized
- future execution code should rely on the same alignment helper, not duplicate logic

## Alignment With References

### Where This Aligns With JonesForth

- newest-first linked dictionary
- hidden-word skipping during lookup
- explicit name blob plus alignment
- explicit code/data boundary helpers

### Where This Aligns With Moving Forth

- words have a stable shared prefix plus payload interpretation
- code/data distinction is structural
- word families need a clear anchor point for shared behavior

### Where It Deviates

The biggest deviations from classic Forth layouts are:

- current fixed prefix is more explicit and schema-driven than hand-built assembly
  layouts
- code/data boundary is represented with Python/runtime helpers instead of raw threaded
  execution primitives
- name bytes currently sit *before* the fixed prefix, which is closer to the older
  `~/fyth` model and JonesForth than to a naive struct-only design

These deviations are acceptable as long as the contract remains explicit.

## Decisions That Look Stable Now

These can be treated as durable unless strong evidence appears otherwise:

- newest-first linked traversal
- hidden-word skipping in normal lookup
- aligned variable-length name blob before fixed prefix
- explicit fixed prefix anchor
- explicit code/data boundary helpers

## Decisions Still Open

These need real choices before we should call the contract finished.

### A. Exact `CodeField` Meaning

Current `CodeField` contains:

- `instruction`
- `hidden`
- `name_length`
- `immediate`
- `compiling`
- `unused`

Open questions:

- is `instruction` the right long-term name?
- should `name_length` stay duplicated in both name header and code field?
- is `compiling` truly word metadata, or should it move elsewhere later?
- what later execution metadata, if any, belongs here?

### B. Cell vs Byte APIs

Current runtime uses both:

- byte-level name protocol
- cell-level memory indexing

Open questions:

- which helpers should be public in byte terms?
- which helpers should be public in cell terms?
- do we want dual helper sets or one canonical internal form plus adapters?

### C. Prefix Growth Policy

Open question:

- what qualifies as fixed word-prefix metadata vs later derived/runtime state?

Without a policy, the prefix can become a junk drawer.

### D. Lookup Surface

Current lookup is:

- direct name equality
- newest-first
- skip hidden

Open questions:

- should lookup tracing become part of the durable API?
- should we formalize visible-only iteration vs raw iteration more strongly?
- do we eventually need separate "dictionary traversal" and "name resolution" layers?

## Decision Checklist

This is the checklist we should walk through next, in order.

1. Confirm that newest-first link semantics are final.
2. Confirm that hidden-word skipping is final.
3. Confirm that the variable-length name blob stays before the fixed prefix.
4. Decide whether `CodeField.name_length` duplication stays or goes.
5. Decide whether `instruction` should be renamed before more code depends on it.
6. Decide whether `compiling` belongs in `CodeField`.
7. Decide which byte-oriented helpers are part of the contract.
8. Decide which cell-oriented helpers are part of the contract.
9. Write the fixed-prefix growth policy explicitly.
10. Only after that, harden more package APIs around this contract.

## Recommended Next Concrete Work

If we continue immediately from this document, the next most useful work is:

1. a focused cleanup of `CodeField` naming and field meaning
2. explicit public helper naming for code/data boundary and name access
3. documentation/tests that assert the contract directly

That would finish most of Step 1 without dragging execution decisions in too early.
