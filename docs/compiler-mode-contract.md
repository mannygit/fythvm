# Compiler Mode Contract

This document is the next adjacent workstream after
[docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1).

The dictionary contract settled word structure. The word-family contract narrowed what
`CodeField.handler_id` means at runtime. This document is about the neighboring layer
that those two docs intentionally do **not** settle:

- interpretation mode vs compile mode
- what `immediate` means
- how compile-only / compiler-meta legality should be modeled
- how compiler/meta words relate to runtime handlers

This is the right place to record uncertainty around those ideas instead of forcing
them into the family model.

## Why This Doc Exists

The current family work exposed a real gap.

We now know that these are different concerns:

- runtime family / shared handler behavior
- data location and interpretation
- compile-time behavior

The old `~/fyth` work was already reaching toward this split:

- `handler_id`-like behavior selection in the fixed prefix
- separate `immediate` / `compiling` flags
- runtime handlers like `[DOCOL]`
- compiler/meta words like `DOCOL`

At the same time, the old code never fully settled the model. That makes this the
right moment to write the contract we wanted, instead of reverse-engineering too much
from WIP details.

## Relationship To Neighboring Docs

- [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
  settles the common word-entry shape
- [docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
  settles the meaning of runtime family as the shared behavior selected by
  `CodeField.handler_id`
- this document asks what happens when words are encountered while the system is
  compiling, building definitions, or otherwise acting as a compiler

So the key rule is:

- **runtime family** is not the same thing as **compile-time behavior**

## Strong JonesForth Signals

JonesForth is useful here because it builds a large part of the compiler in Forth
itself.

The clearest patterns in
[Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:1)
are:

- `LITERAL` is `IMMEDIATE` and compiles `LIT <value>`
- `[` and `]` switch between immediate and compile mode
- `[COMPILE]` is `IMMEDIATE` and compiles a word even if that word would otherwise
  execute immediately while compiling
- control words like `IF`, `THEN`, `ELSE`, `BEGIN`, `UNTIL`, `WHILE`, `REPEAT` are
  `IMMEDIATE`
- `S"` and `."` branch on `STATE @` and do different things in compile mode versus
  immediate mode
- `TO` and `+TO` are `IMMEDIATE` and also branch on `STATE @`
- words like `CONSTANT`, `VARIABLE`, and `VALUE` build new words by compiling
  `DOCOL`, `LIT`, payload cells, and `EXIT`

The broad lesson is:

- JonesForth handles much of this layer with a **mode bit** (`STATE`) plus **word
  flags** (`IMMEDIATE`), not by inventing a separate dictionary entry structure

That strongly supports keeping compile-time behavior as its own axis in `fythvm`.

It also gives us an important negative constraint:

- JonesForth reaches a self-hosting compiler layer without any separate `compiling`
  flag

Current direction in `fythvm` follows that constraint:

- there is no `compiling` bit in `CodeField`
- compile-only or compiler-meta legality belongs at the compiler layer, not in the
  dictionary metadata cell

## Working Distinction: Runtime Handler vs Compiler/Meta Word

The older `~/fyth` code already hinted at a useful distinction:

- `[DOCOL]` was the actual runtime handler
- `DOCOL` was a word that pushed the id/address of `[DOCOL]`

That split is extremely relevant.

It suggests there are at least two different kinds of names in play:

1. **runtime handlers**
   - the things selected by `CodeField.handler_id`
   - examples in the old model: `[DOCOL]`, `[DOCON]`, `[DOVAR]`

2. **compiler/meta words**
   - words that refer to handlers, compile them, or otherwise manipulate the current
     definition
   - examples in the old model: `DOCOL`, `LITERAL`, `[COMPILE]`

This does **not** mean they need different dictionary entry shapes.

It does mean the package should not collapse:

- "what executes at runtime?"
- and "what helps the compiler build runtime words?"

into one undifferentiated notion.

## Working Definition Of `immediate`

Current best reading:

- `immediate` means that when the system is in compile mode, encountering this word
  causes the word to execute **now** instead of being compiled as an ordinary word
  reference

That matches JonesForth well:

- control words are `IMMEDIATE`
- `LITERAL` is `IMMEDIATE`
- `[COMPILE]` is `IMMEDIATE`
- `S"` and `."` are `IMMEDIATE`
- `TO` and `+TO` are `IMMEDIATE`

What `immediate` does **not** mean:

- a different runtime family
- a different dictionary shape
- necessarily "compile-only"

So the strongest current interpretation is:

- `immediate` is a compile-mode dispatch rule on ordinary words

## Current Direction: No `compiling` Bit

The old `compiling` flag was useful as a design pressure marker, but the current
direction is to remove it from `CodeField`.

Why:

- JonesForth-style self-hosting does not require it
- `STATE` already covers interpreter/compiler mode
- `immediate` already covers compile-mode dispatch override
- explicit compiler/meta words already cover much of the remaining surface

So the cleaner model is:

- `STATE`
  - interpreter/compiler mode
- `immediate`
  - execute-now while compiling instead of compiling a normal word reference
- compile-only / compiler-meta legality
  - a compiler-layer concern, not a dictionary-cell concern

This means the remaining pressure that originally motivated `compiling` is now framed
as a compiler-layer question:

- which words are only valid in compile mode?
- which words belong to the compiler/meta vocabulary?
- how should wrong-mode use fail?

## `STATE` Versus Word Flags

JonesForth strongly suggests we should think in terms of both:

- a **system mode**
  - are we interpreting now, or compiling a definition now?
- **per-word flags**
  - does this word execute immediately while compiling?
  - does this word need compile-layer legality or wrong-mode checks?

That suggests the eventual model in `fythvm` will probably need:

- something like a compile/interpreter mode bit or state value
- word metadata that changes how the current mode handles the word

This is exactly why `immediate` and compile-only legality should be discussed here, not
in the runtime family contract.

The minimum JonesForth substrate suggests a discipline:

- `STATE` should mean only interpreter/compiler mode
- `immediate` should mean only compile-mode dispatch override
- compile-only behavior should be enforced by compiler-layer checks, not by a
  `CodeField` bit

## Canonical Examples

### `LITERAL`

JonesForth:

- `LITERAL` is `IMMEDIATE`
- it compiles `LIT` and then the value currently on the stack

This makes `LITERAL` a compiler/meta word.

It does **not** mean `LITERAL` is itself a special runtime family.

### `S"` and `."`

These are especially useful because they branch on `STATE @`.

So they show a pattern we likely need to support explicitly:

- same word
- different behavior depending on compile mode vs immediate mode

That is a compile-time semantics issue, not a runtime family issue.

### `TO`

`TO` in JonesForth is `IMMEDIATE` and also inspects `STATE @`:

- in compile mode it compiles code that will update the value later
- in immediate mode it updates the value directly

Again, the important lesson is:

- compile-time behavior and runtime handler behavior are different layers

### `DOCOL` and `[DOCOL]`

The old `~/fyth` split is a good local reminder:

- runtime handlers and compiler/meta references to them are related
- but they are not the same thing

This is likely to matter again when we start defining the real handler table and the
compiler words that emit it.

## What Looks Settled

These points now look strong enough to rely on:

- `immediate` belongs to the compile-time axis, not the family axis
- `immediate` should not imply a different dictionary entry shape
- compile-time words can still be ordinary words in the dictionary
- runtime handlers and compiler/meta words that refer to them are related but distinct
- JonesForth mostly handles this layer with mode plus word flags, not with structural
  dictionary splits
- JonesForth-style self-hosting does not justify a separate `compiling` bit
- current `fythvm` direction removes that bit from `CodeField`
- compile-only behavior should instead be modeled as compiler-layer legality

## Current Open Questions

### 1. Do We Need A First-Class Compile Mode State In Package Design?

JonesForth strongly suggests yes.

The open question is not whether compile mode exists conceptually, but:

- where should it live in `fythvm` package design?
- as runtime state?
- as compiler-layer state?
- as part of the future execution/compiler contract?

### 2. How Should Runtime Handlers Be Referred To By Compiler Words?

This is where the old `DOCOL` / `[DOCOL]` distinction becomes useful.

Open questions:

- should runtime handlers and compiler/meta words be represented by different package
  types?
- or is the distinction purely at the documentation / helper layer?

### 3. Which Words Need Both Interpret-Mode And Compile-Mode Behavior?

JonesForth examples:

- `S"`
- `."`
- `TO`
- `+TO`

The open question is how explicitly to model that duality in package code.

### 4. Which Words Should Be Considered Compile-Only?

JonesForth notes that some control words only make sense while compiling.

So a real question for `fythvm` is:

- do we want an explicit compile-only notion?
- or do we want that to remain an error-policy / later compiler concern?

## Suggested Review Order

1. settle what `immediate` means in `fythvm`
2. decide whether compile mode state needs a first-class package representation
3. decide how compiler/meta words refer to runtime handlers
4. decide which words should be compile-only and how wrong-mode use fails
5. only then hand this layer off to execution/compiler invariants

## Short Version

This doc exists to keep us honest about something the family work exposed:

- not every important distinction belongs in runtime families

In particular:

- `handler_id` is about runtime behavior
- `immediate` is about compile-mode dispatch
- compile-only / compiler-meta legality belongs at the compiler layer, not in
  `CodeField`
- `DOCOL` versus `[DOCOL]` is a warning that compiler/meta words and runtime handlers
  should not be collapsed into one concept too early
