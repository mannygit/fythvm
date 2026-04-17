# Compiler Mode Contract

This document is the canonical compile-mode contract for `fythvm`.

It defines:

- `STATE` as interpreter/compiler mode
- `immediate` as compile-mode dispatch behavior
- compile-only / compiler-meta legality as a compiler-layer concern
- the distinction between compiler/meta words and runtime handlers

It does **not** define:

- runtime family semantics
- dictionary entry structure
- final execution form

For those, see:

- [docs/dictionary-contract.md](/Users/manny/fythvm/docs/dictionary-contract.md:1)
- [docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
- [docs/execution-invariants.md](/Users/manny/fythvm/docs/execution-invariants.md:1)
- [docs/handler-requirements.md](/Users/manny/fythvm/docs/handler-requirements.md:1)

## Core Contract

### `STATE`

`STATE` means only:

- interpret mode
- compile mode

It should not become a catch-all bucket for:

- fault state
- exception state
- generic executor bookkeeping

### `immediate`

Current definition:

- when the system is in compile mode, an `immediate` word executes now instead of being
  compiled as an ordinary word reference

`immediate` does **not** mean:

- a different runtime family
- a different dictionary shape
- necessarily compile-only

### No `compiling` Bit

Current direction is explicit:

- there is no `compiling` bit in `CodeField`
- compile-only / compiler-meta legality belongs to the compiler layer, not the
  dictionary metadata cell

Why:

- JonesForth reaches a self-hosting compiler layer without a separate `compiling` bit
- `STATE` already covers interpreter/compiler mode
- `immediate` already covers compile-mode dispatch override
- explicit compiler/meta words cover much of the remaining surface

## Runtime Handlers Versus Compiler/Meta Words

The key distinction is:

- runtime handlers are what `CodeField.handler_id` selects
- compiler/meta words refer to handlers, compile them, or manipulate the current
  definition

The old `~/fyth` `DOCOL` / `[DOCOL]` split is still a good reminder:

- runtime handlers and compiler/meta references to them are related
- but they should not be collapsed into one undifferentiated concept

This does **not** require different dictionary entry shapes.

## Parse-Time Input Versus Runtime Thread State

This is the canonical place to keep one important distinction explicit:

- compiler/meta words consume input/parse state
- runtime inline-operand words consume thread state

Those are different data sources and should not be conflated.

The neighboring helper/lowering consequence is:

- compiler/meta words may still declare needs like input source, dictionary access,
  `HERE`, source cursors, thread emitters, or error-exit facilities
- but those belong to a `HandlerRequirements`-style layer, not to runtime
  associated-data-source metadata

The current package direction is to let compiler/meta words live in a neighboring
compiler-word registry rather than forcing them into the runtime instruction registry.
That neighboring registry already exists in package code in
`src/fythvm/dictionary/compiler_words.py`.

## Strong JonesForth Signals

JonesForth is especially useful here because it builds a large part of the compiler in
Forth itself.

The strongest signals are:

- `LITERAL` is `IMMEDIATE` and compiles `LIT <value>`
- `[` and `]` switch between interpret and compile mode
- `[COMPILE]` is `IMMEDIATE` and forces a word to be compiled instead of executed now
- control words like `IF`, `THEN`, `ELSE`, `BEGIN`, `UNTIL`, `WHILE`, and `REPEAT` are
  `IMMEDIATE`
- `S"`, `."`, `TO`, and `+TO` branch on `STATE @`
- defining words like `CONSTANT`, `VARIABLE`, and `VALUE` build new words by compiling
  `DOCOL`, `LIT`, payload cells, and `EXIT`

The broad lesson is:

- compile-time behavior is real
- it is not runtime family behavior
- it is handled by mode plus word behavior, not by splitting dictionary structure

## Canonical Examples

### `LITERAL`

`LITERAL` is a compiler/meta word.

It is `IMMEDIATE`, and it compiles:

- `LIT`
- the current value

That does not make `LITERAL` a distinct runtime family.

### `S"` and `."`

These show the dual-mode pattern clearly:

- same word
- one behavior in interpret mode
- another behavior in compile mode

For the current package pass, only the compile-time `S"` behavior is modeled:

- `S"` is treated as a compiler/meta word in a neighboring compiler-word registry
- it parses source text and emits `LITSTRING`, one length cell, and packed payload
  cells into the current definition
- immediate-mode temporary storage behavior is deliberately left out for now
- `IF` and `THEN` are also current compiler-word registry examples for compile-time
  branch emission and patching

### `TO`

`TO` is useful because it combines:

- `IMMEDIATE`
- `STATE` inspection
- different behavior in compile mode versus interpret mode

### `[COMPILE]`

`[COMPILE]` is the canonical “immediate escape” example:

- an immediate word would normally execute now while compiling
- `[COMPILE] word` forces that word to be emitted into the compile stream instead

## Open Points

### 1. Where Should Compile Mode Live In Package Design?

The concept is settled. The remaining question is representation:

- runtime state
- compiler-layer state
- or some future execution/compiler contract object

### 2. How Explicit Should Runtime-Handler References Be In Compiler Vocabulary?

The remaining open question is not whether the distinction exists, but how explicitly
to represent it in package code.

### 3. Which Words Need Dual Interpret/Compile Behavior?

JonesForth says this pattern is real.

Open question:

- how much of that duality should be modeled explicitly in package metadata versus left
  to later compiler/lowering code

### 4. Which Words Should Be Considered Compile-Only?

The current direction is:

- compile-only behavior should be modeled as compiler-layer legality or wrong-mode
  policy

The remaining question is:

- how explicit that notion should become in package/compiler code
