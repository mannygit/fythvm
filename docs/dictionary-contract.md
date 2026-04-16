# Dictionary Contract

This document is the canonical dictionary-structure contract for `fythvm`.

It defines:

- common word-entry structure
- lookup and visibility semantics
- `xt` / `CFA` / `DFA` meaning
- name storage and alignment rules

It does **not** define:

- runtime family semantics
- compile-mode behavior
- execution form

For those, see:

- [docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
- [docs/compiler-mode-contract.md](/Users/manny/fythvm/docs/compiler-mode-contract.md:1)
- [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)

## Core Contract

### One Dictionary Shape

Native words and later-defined words share the same dictionary contract.

What can differ is:

- runtime family
- associated-data source
- compile-time behavior

What does **not** differ is the basic entry shape.

### Physical Layout

The current contract is:

```text
[ name bytes + padding ][ previous link ][ CodeField ][ data... ]
                                ^              ^           ^
                              link           xt/CFA       DFA
```

The fixed prefix is exactly:

- `previous link`
- `CodeField`

There is no separate physical name-header byte in the layout.

### Fixed Prefix

The fixed prefix is the first stable cell-aligned structural record of a word.

Current rule:

- the fixed prefix stays `[link][CodeField]`
- `CodeField` stays one 32-bit cell
- if future families need more payload, that belongs after `DFA`, not in a larger
  fixed prefix

### `CodeField`

`CodeField` is the single canonical metadata cell for the word prefix.

Current contents:

- `handler_id`
- `hidden`
- `immediate`
- `name_length`
- reserved / unused bits

Current direction:

- `handler_id` is runtime behavior selection metadata
- `hidden` is lookup visibility metadata
- `immediate` is compile-mode dispatch metadata
- unused bits remain unused until there is a compelling reason to assign them meaning

## Address Semantics

The dictionary contract exposes the classic code/data boundary meanings.

- `xt` is the address of the `CodeField`
- `CFA` is the same address as `xt`
- `DFA` is the address immediately after the fixed prefix

This means:

- code/data boundaries are explicit
- callers should not recompute offsets ad hoc
- runtime and IR helpers should continue to expose these boundaries directly

## Lookup And Visibility

### Ordering

`latest` is the head of the dictionary chain.

Traversal is newest-first by following links through the full chain.

Consequences:

- redefining a word shadows older definitions naturally
- lookup order is a property of the link chain itself
- historical order remains preserved in the chain

### Hidden Words

Hidden words remain physically present in the chain.

Normal dictionary lookup must skip them.

Consequences:

- visibility is applied by lookup, not by rewriting links
- hidden words may still be reachable by direct reference or explicit traversal
- hidden/native and hidden/later-defined words behave the same way

## Names And Alignment

### Name Storage

The word name is a variable-length byte region before the fixed prefix.

Encoding:

- raw name bytes
- zero padding to cell alignment
- metadata about that region lives in `CodeField`, not in a separate physical header

### Alignment Rule

The name region is aligned to cell size before the fixed prefix starts.

Rules:

- the fixed prefix always begins at a cell-aligned boundary
- alignment math stays centralized
- future runtime/execution code should use the same helper logic rather than duplicating
  offset math

## Runtime Meaning Of This Contract

This contract deliberately prefers the general dictionary model over the older
"small-xt-dispatch-only" intuition.

That older intuition can still be useful:

- as a subset
- as a bootstrap layer
- as an optimization

But the full dictionary contract is:

- linked
- metadata-bearing
- name-bearing
- prefix-plus-data

That is the model later work should consume.

## Current Stable Decisions

These points should be treated as settled unless later execution work proves otherwise:

- one common dictionary shape for native and later-defined words
- newest-first link traversal
- hidden-word skipping in normal lookup
- aligned variable-length name blob before the fixed prefix
- fixed prefix is `[link][CodeField]`
- `xt == CFA == address of CodeField`
- `DFA == address immediately after the fixed prefix`

## Open Points

The remaining open points here are small compared to the neighboring docs.

- whether any currently unused `CodeField` bits ever deserve meaning
- the exact durable public helper surface for byte-oriented vs cell-oriented access
- how much of the current runtime/IR helper naming should be treated as long-term API

Those are maintenance-level open points, not structural uncertainty.
