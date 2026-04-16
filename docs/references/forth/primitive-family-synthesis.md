# JonesForth And Moving Forth Primitive Family Synthesis

This document synthesizes:

- the concrete primitive inventory in
  [jonesforth/primitive-inventory.md](./jonesforth/primitive-inventory.md)
- the architectural reading in
  [moving-forth-implementation-report.md](./moving-forth-implementation-report.md)
- the project-level interpretation in
  [forth-implementation-alignment-report.md](./forth-implementation-alignment-report.md)

The goal is narrower than the full alignment report. This document asks:

- what do the JonesForth primitives actually cluster into?
- how does Moving Forth explain those clusters?
- what family model should `fythvm` adopt from that?

## Executive Summary

JonesForth and Moving Forth point to the same core result:

- one common dictionary contract
- a small number of **shared behavior families**
- family-specific interpretation of payload after the fixed prefix

They do **not** primarily suggest multiple unrelated word layouts.

The strongest shared family set is:

1. **payload-empty primitive**
2. **payload-bearing primitive**
3. **colon-thread**
4. **shared field-interpreter family**
5. **defining-word-produced family**

For `fythvm`, the first practical implementation cut is probably:

1. `primitive-empty`
2. `primitive-inline-operand`
3. `colon-thread`

with the last two generalized families kept explicit in the design, but allowed to land
after the simpler three-family core is stable.

## What JonesForth Gives Us Directly

JonesForth gives us the most concrete primitive inventory:

- 75 `defcode` words
- a clear split between assembly-defined primitive words and higher-level `defword`
  definitions
- direct examples of:
  - payload-empty primitives
  - payload-bearing primitives
  - colon definitions using a shared `DOCOL` behavior

From [jonesforth/primitive-inventory.md](./jonesforth/primitive-inventory.md), the
important concrete clusters are:

### Payload-empty primitive words

Examples:

- stack: `DROP`, `DUP`, `SWAP`, `OVER`
- arithmetic: `+`, `-`, `*`, `/MOD`
- comparison: `=`, `<`, `0=`
- memory: `!`, `@`, `C!`, `C@`, `CMOVE`
- dictionary/compiler: `FIND`, `CREATE`, `IMMEDIATE`, `HIDDEN`, `'`
- host bridge: `SYSCALL0` ... `SYSCALL3`

Pattern:

- the codeword selects a primitive behavior
- the word usually does **not** interpret a payload region after `DFA`

### Payload-bearing primitive words

Examples:

- `LIT`
- `BRANCH`
- `0BRANCH`
- `LITSTRING`

Pattern:

- still primitive-dispatch words
- but the primitive consumes inline operands from the threaded stream or payload region

This is the clearest direct source support for a distinct
**payload-bearing primitive** family.

### Colon/thread words

JonesForth does not define colon words as primitives. Instead:

- colon definitions are normal dictionary words
- their codeword points to `DOCOL`
- the body is a thread of xts plus inline operands

That is the concrete source for the `colon-thread` family.

## What Moving Forth Adds Conceptually

Moving Forth contributes less of a flat primitive inventory and more of a theory for why
those clusters exist.

The key parts are already captured in
[moving-forth-implementation-report.md](./moving-forth-implementation-report.md):

- [Section 4](./moving-forth-implementation-report.md#4-next-enter-and-exit-define-the-core-runtime):
  the benchmarkable kernel subset
- [Section 8](./moving-forth-implementation-report.md#8-part-3-the-most-important-conceptual-shift-is-the-code-field-contract):
  code field + parameter field as the core abstraction
- [Section 9](./moving-forth-implementation-report.md#9-docon-dovar-and-enter-are-really-shared-field-interpreters):
  shared field-interpreter families
- [Section 10](./moving-forth-implementation-report.md#10-does-matters-because-it-makes-new-classes-of-words-possible):
  defining words create new classes of words
- [Section 11](./moving-forth-implementation-report.md#11-code-words-are-the-exception-that-proves-the-rule):
  not every family is a neat field-interpreter case

Moving Forth sharpens the family model in three important ways.

### 1. Families are really “shared code-field actions”

Rodriguez’s core point is:

- every word has a code field and parameter field
- the code field selects a shared action
- the parameter field is interpreted according to that action

That is exactly what turns a flat “primitive list” into a real family model.

### 2. Some families are shared field interpreters

Moving Forth makes families like these explicit:

- `ENTER` / `DOCOL`
- `DOVAR`
- `DOCON`
- `LIT`

These are not just isolated words. They are:

- a shared action
- plus per-word or per-instance payload interpretation

That expands the JonesForth view. JonesForth clearly shows `DOCOL` and payload-bearing
control/literal primitives, but Moving is what makes the broader pattern explicit.

### 3. Defining words matter because they create new word classes

Moving Forth also makes a crucial architectural point:

- `CREATE`
- `DOES>`
- `;CODE`

are not merely compiler tricks. They are how the system manufactures new classes of words
with shared behavior and chosen payload semantics.

That gives us a real reason to keep “defining-word-produced family” explicit in `fythvm`,
even if we implement it later.

## Where JonesForth And Moving Forth Align

The two sources align strongly on these points.

### One common dictionary contract

Both sources assume:

- one linked dictionary structure
- one fixed word boundary concept
- behavior selected from the fixed entry
- family semantics layered on top of that common structure

That is consistent with our current
[dictionary contract](/Users/manny/fythvm/docs/dictionary-contract.md:1).

### A small kernel of shared behaviors

Both sources center a small shared kernel:

- `NEXT`
- `EXIT`
- `EXECUTE`
- `DOCOL` / `ENTER`
- `LIT`
- core stack/memory/arithmetic words

JonesForth shows this concretely in the primitive list; Moving Forth turns it into a
design principle.

### Payload is interpreted by family

Both sources support:

- some words have empty payload
- some words interpret payload as inline operands
- colon definitions interpret payload as a thread

That is the central reason to introduce families in `fythvm`.

## Where Moving Forth Extends JonesForth

Moving Forth goes further than JonesForth in two areas.

### Shared field-interpreter families beyond colon words

JonesForth gives us:

- payload-empty primitives
- payload-bearing primitives
- `DOCOL`

Moving Forth makes it clearer that there is a larger family pattern:

- `DOCON`
- `DOVAR`
- `ENTER`
- `LIT`

This suggests that `fythvm` should not stop with just “primitive vs colon.”

### Defining-word-produced classes

JonesForth shows real compiler/dictionary words like `CREATE`, `IMMEDIATE`, and `HIDDEN`,
but Moving Forth is the source that really explains why new word classes exist at all.

That is the strongest reason to keep a separate “defining-word-produced” family concept in
the design docs, even if runtime support arrives later.

## Where JonesForth Is Still The Better Grounding

On the other hand, JonesForth is still the better grounding for several practical choices.

### Payload-bearing primitive words are not hypothetical

JonesForth shows real kernel words doing this:

- `LIT`
- `BRANCH`
- `0BRANCH`
- `LITSTRING`

So the `primitive-inline-operand` family is not just theory. It is directly represented in a
finished working system.

### Dictionary/compiler control can stay inside the primitive family

JonesForth does **not** invent a separate word-entry category for:

- `IMMEDIATE`
- `HIDDEN`
- `[`
- `]`
- `'`
- `CREATE`
- `,`

It treats them as ordinary primitive words whose behavior affects compiler state or
dictionary metadata.

That is a useful constraint for `fythvm`: do not over-split the family model just because
some primitives affect the compiler or dictionary.

## Suggested `fythvm` Family Model

Putting both sources together, the best current family model looks like this.

### Phase 1: the minimal implementable set

1. **primitive-empty**
   - primitive-dispatch word
   - no meaningful payload after `DFA`

2. **primitive-inline-operand**
   - primitive-dispatch word
   - payload interpreted according to the primitive
   - examples: `LIT`, `BRANCH`, `0BRANCH`, `LITSTRING`

3. **colon-thread**
   - shared `DOCOL`-like behavior
   - payload is a thread of xts and inline operands

This is enough to capture what JonesForth proves concretely.

### Phase 2: the generalized family layer

4. **shared field-interpreter**
   - shared behavior routine
   - payload interpreted as instance-specific data
   - Moving Forth examples: `DOCON`, `DOVAR`, `ENTER`, `LIT`

5. **defining-word-produced**
   - words produced by defining words with a chosen shared behavior and payload shape
   - Moving Forth examples center on `CREATE`, `DOES>`, `;CODE`

This is where the model becomes expressive enough to cover more advanced Forth growth.

## What This Means For `instruction`

This synthesis supports the current `fythvm` direction:

- `instruction` is a primitive/shared-behavior selector
- it does **not** by itself define the whole word schema
- the meaning of `DFA` depends on the family selected by that instruction

That is exactly the sort of separation
[docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1)
is trying to pin down.

## Practical Takeaway

If we compress the synthesis down to one sentence:

> JonesForth gives the concrete primitive clusters; Moving Forth explains that those
> clusters are really shared behavior families over one common dictionary contract.

So the next useful move in `fythvm` is not “invent more layouts.” It is:

- make the first family set explicit in package code
- attach payload interpretation to those families
- keep the common dictionary contract fixed underneath

That is the point where the current workstream can turn from reference-backed design into
real implementation.
