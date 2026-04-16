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

## Design Context

One important piece of project history needs to be stated explicitly, because it
explains some of the noise in both `~/fyth` and the newer `fythvm` code.

The system did **not** start from a top-down Forth dictionary design.

It started from a much simpler phase:

- implement words
- make them operate on a stack
- do arithmetic
- keep moving

There was no full dictionary plan at the beginning. The early direction was closer to:

- "get useful stack words working"
- "get execution-shaped pieces moving"
- "code on feel"

Only later did the stricter Forth problem become unavoidable:

- some words can be represented as simple low-memory execution tokens looked up through
  a small dispatch table
- but that only covers a narrow case
- a real general Forth needs words to be more than opcodes

The general case requires:

- word metadata
- linked dictionary structure
- names and visibility rules
- fixed prefix plus payload
- sequences of words / threads
- code/data boundary helpers
- later, defining-word-like construction and execution interpretation

So the repo contains some historical layering:

- an early "small xt dispatch" intuition
- then a later realization that the general case is dictionary-structured and
  metadata-driven

That means some older design traces may look inconsistent for a reason:

- they may reflect a transition from "stack word execution" thinking
- toward "full word record with metadata and payload" thinking

This document should therefore prefer the general dictionary model when the two are in
tension.

The simpler low-memory/lookup-table xt model can still be useful:

- as an optimization
- as a subset
- as a bootstrap layer

But it should not be mistaken for the full dictionary contract.

## Native Words vs Later-Defined Words

One of the main remaining "gut feel" questions is whether built-in/native words and
later-defined words should be treated as fundamentally different at the dictionary
level.

The answer this document recommends is:

- **different execution families**
- **same dictionary contract**

That is, the distinction is real, but it belongs in word-family interpretation, not in
the basic meaning of what a dictionary entry is.

### Why The Feeling Exists

The feeling comes from a real historical difference:

- early built-ins can look like simple execution tokens, opcodes, or low-memory table
  entries
- later-defined words look like "real Forth words" with names, metadata, and threads

That can make it seem like these are two different dictionary species.

But both classic references argue otherwise:

- JonesForth stores built-ins and colon definitions in one linked dictionary, even
  though their codeword targets differ
- Moving Forth explicitly explains that different word classes share the same broader
  code-field / parameter-field idea, while differing in how the code field is
  interpreted

So the stronger model is:

- a dictionary entry always names a word-family instance
- what varies is the family-specific interpretation of the payload

### What Should Be The Same

Built-in/native words and later-defined words should both participate in the same
dictionary-level structure:

- link ordering
- visibility rules
- name encoding
- fixed prefix anchor
- code/data boundary helpers
- lookup and shadowing semantics

That means:

- redefining a native word should shadow it the same way as redefining any later word
- hidden/native and hidden/later-defined words should behave the same in lookup
- iteration over the dictionary should not need separate mechanisms for "primitive"
  versus "defined" words

### What Can Differ

What can differ is the word-family interpretation:

- native word:
  - payload may effectively be a handler id, builtin handler id, or native entry
    reference
- colon-like defined word:
  - payload may be a thread / sequence / word stream
- defining-word-produced family:
  - payload may be family-specific data interpreted by shared behavior

So this distinction belongs under:

- code-field meaning
- word family
- execution interpretation

not under:

- basic dictionary shape

### Contract Decision

For purposes of `docs/dictionary-contract.md`, the working decision should be:

- **the dictionary does not distinguish "builtin/native" versus "later-defined" as two
  different structural kinds of entry**
- it distinguishes only:
  - common dictionary structure
  - family-specific payload interpretation

### What This Means For Open Questions

This reduces a few ambiguities:

- `handler_id` should be understood as
  family/behavior-selection metadata, not proof that "this is a totally different kind
  of word"
- future thread-bearing words should still fit under the same dictionary contract
- simple builtin dispatch tables can exist, but they should be treated as one execution
  family inside the dictionary model, not as the whole model

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
- IR helpers:
  - [src/fythvm/dictionary/ir.py](/Users/manny/fythvm/src/fythvm/dictionary/ir.py:1)
- generated IR layout:
  - [src/fythvm/dictionary/layout.py](/Users/manny/fythvm/src/fythvm/dictionary/layout.py:1)

Current dictionary entry shape in runtime terms:

1. A word name is stored as:
   - raw name bytes
   - zero padding to cell alignment
2. The fixed word prefix starts immediately after that aligned name blob.
3. The fixed prefix currently contains:
   - `link`
   - `code_field`
   - zero-length `data_start`
4. The data area begins immediately after the fixed prefix.

## Implementation Status

Current `fythvm` runtime is aligned with the desired contract.

Desired target contract:

```text
[ name bytes + padding ][ previous link ][ CodeField ][ data... ]
```

with `CodeField` as the canonical storage for:

- execution handler selector (`handler_id`)
- hidden
- immediate
- name length
- reserved flags

and **no separate physical `NameHeader` byte**.

Address interpretation under this contract:

- `xt` is the address of the `CodeField`
- `CFA` is the same thing as `xt`
- `DFA` is the address immediately after the fixed prefix

So visually:

```text
[ name bytes + padding ][ previous link ][ CodeField ][ data... ]
                                ^              ^           ^
                              link           xt/CFA       DFA
```

So, to be explicit:

- runtime storage is:
  - raw name bytes
  - zero padding
  - `link`
  - canonical `CodeField`
  - data
- `CodeField` is the only physical metadata cell
- Python/runtime accessors read metadata from `CodeField`
- byte-oriented helpers exist for name bytes and alignment, not for a physical header
  byte

Current code points:

- aligned name size helper:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:20)
- word creation:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:159)
- IR word creation:
  - [ir.py](/Users/manny/fythvm/src/fythvm/dictionary/ir.py:219)
- newest-first traversal:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:195)
- hidden-word skipping:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:203)
- IR hidden-word skipping and newest-first lookup:
  - [ir.py](/Users/manny/fythvm/src/fythvm/dictionary/ir.py:145)
- CFA/DFA helpers:
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:140)

Concrete inspector:

- [scripts/inspect_dictionary_word_layout.py](/Users/manny/fythvm/scripts/inspect_dictionary_word_layout.py:1)
  - runnable dump of one sample word showing:
    - name bytes region
    - fixed prefix bytes
    - `CodeField` cell bytes and bits
    - the actual canonical storage layout

## Reference Alignment

The older `~/fyth` code and the classic Forth references align on the important shape:

- name bytes before the fixed prefix
- explicit link field
- explicit code/data boundary helpers
- minimal fixed prefix
- metadata and execution-family selection carried by the fixed prefix rather than by a
  separate external index

Relevant files:

- [~/fyth/src/fyth/words.py](/Users/manny/fyth/src/fyth/words.py:1)
- [~/fyth/src/fyth/core/layout.py](/Users/manny/fyth/src/fyth/core/layout.py:1)
- [~/fyth/src/fyth/tests/test_layout.py](/Users/manny/fyth/src/fyth/tests/test_layout.py:1)

## Proposed Contract

This section is the current recommended contract for `fythvm`.

### 1. Dictionary Ordering

`latest` is the head of the dictionary chain.

Each word prefix stores a link to the previous word in creation order.
Traversal is newest-first by following that full chain.

This means:

- redefining a word shadows older definitions naturally
- lookup order is a property of the link chain, not of any auxiliary index
- historical order is preserved in the chain itself
- hidden words remain in the chain; visibility is applied by lookup, not by link
  rewriting

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
- `code_field: CodeField`
- `data_start: i32 * 0`

This is a good current shape because it makes three things explicit:

- chain linkage
- code/metadata flags
- data starts here

Recommended rule:

- the fixed prefix should remain the canonical anchor for code/data boundary
  calculations
- the fixed prefix stays exactly:
  - `previous link`
  - `CodeField`
- `CodeField` stays one 32-bit cell
- the currently unused bits in `CodeField` remain unused unless there is a compelling
  future reason to assign them meaning
- there is no plan to extend the fixed prefix beyond `[link][CodeField]`
- if future word families need more payload, that belongs after `DFA`, not in a larger
  fixed prefix

### 4. Code/Data Boundary Helpers

The dictionary contract should expose explicit helpers equivalent in spirit to classic
`>CFA` and `>DFA`, even if the naming stays more Pythonic.

Current helpers:

- cell-index helpers:
  - `cfa_index`
  - `dfa_index`

([runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:180))

Recommended rule:

- `xt` and `CFA` mean the address of the `CodeField`
- `DFA` means the address immediately after the fixed prefix
- `cfa_index` and `dfa_index` are the cell-index view of those same boundaries in the
  Python runtime
- code/data boundary helpers are part of the public dictionary contract
- callers should not be expected to recompute offsets ad hoc
- code/data boundary derivation should remain explicit in both byte and cell terms when
  needed

### 5. Name Encoding

The word name is a variable-length byte region before the fixed prefix, not a normal
struct field.

Desired encoding:

- raw name bytes
- then zero padding to cell alignment
- with length/visibility/behavior flags owned by `CodeField`

Recommended rule:

- name bytes remain a dedicated variable-length protocol region
- it should not be forced into the fixed prefix just for convenience
- the prefix should carry the metadata needed to interpret that region

### 6. Alignment Rule

The name bytes region is aligned to cell size before the fixed prefix starts.

Current helper:

- `aligned_name_region_size(...)`
  - [runtime.py](/Users/manny/fythvm/src/fythvm/dictionary/runtime.py:18)

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

### A. Exact `CodeField` Contents

Current `CodeField` contains:

- `handler_id`
- `hidden`
- `name_length`
- `immediate`
- `unused`

This is now mostly settled:

- `CodeField` is the single canonical metadata cell
- `handler_id`, `hidden`, `name_length`, and `immediate` belong there
- `handler_id` is:
  - a primitive Forth-system handler id in the current model
  - used to index a jump table / dispatch table
  - selecting the execution behavior for the word
  - with colon-defined words using the primitive id for `DOCOL`
- only metadata that is actually needed should live in `CodeField`
- the currently unused bits remain unused until there is a compelling reason to assign
  them meaning

The only meaningful remaining question here is:

- what later execution metadata, if any, would justify consuming some of the currently
  unused bits?

### B. Cell vs Byte APIs

Current runtime uses both:

- byte-level name region access
- cell-level memory indexing

Settled direction:

- keep dual helper sets
- byte APIs should own:
  - name bytes
  - aligned name region length
- cell APIs should own:
  - word indices
  - link traversal
  - CFA/DFA/data-cell indexing
- suitable abstractions should exist for these fields and helpers so that:
  - IR-generating code is easier to read
  - Python/runtime inspection is easier to read
  - both views stay consistent

### C. Lookup Surface

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
4. Lock down the byte-oriented helper surface.
5. Lock down the cell-oriented helper surface.
6. Only after that, harden more package APIs around this contract.

## Recommended Next Concrete Work

If we continue immediately from this document, the next most useful work is:

1. add explicit field/helper abstractions for both IR/codegen and Python observability
2. documentation/tests that assert the contract directly
3. refine the lookup/traversal public surface if needed

That would finish most of Step 1 without dragging execution decisions in too early.
