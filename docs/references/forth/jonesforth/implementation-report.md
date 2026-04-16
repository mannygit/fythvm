# JonesForth Implementation Report

This report explains how the particular JonesForth implementation in this folder is
built and what is most relevant to `fythvm`.

Files referenced here:

- assembly kernel: [Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1)
- self-hosted Forth layer: [Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:1)

## Executive Summary

JonesForth is a Linux/i386 indirect-threaded Forth with a tiny assembly kernel and a
much larger self-hosted Forth layer.

Its implementation is organized around a few core ideas:

- dictionary entries are linked records with a packed length/flag byte and aligned name
  storage
- execution is indirect-threaded, centered on the `NEXT` macro and the `DOCOL`
  interpreter
- the assembly kernel provides the runtime substrate:
  - stacks
  - primitive words
  - dictionary search
  - parsing
  - compile/execute mode machinery
  - `CREATE`, `,`, `:`, `;`, `INTERPRET`, `QUIT`
- after that substrate exists, the language grows itself in Forth:
  - control structures
  - string words
  - variables, values, and mutation syntax
  - introspection and decompilation
  - anonymous words and execution tokens
  - exceptions
  - an inline assembler story

This makes JonesForth valuable not because it is "the" right Forth design, but because
it is unusually explicit about where the machine substrate stops and where the
self-hosted language begins.

## 1. Overall Structure

JonesForth is split cleanly into two stages:

- `Jonesforth.S.txt`
  - establishes the machine-level runtime
  - boots directly into a high-level Forth loop
- `Jonesforth.f.txt`
  - assumes the system is already self-hosting
  - extends the language in Forth itself

This split is visible right at the top of the Forth file: it says the system is now
"running and self-hosting" and that further words can be written in Forth
([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:32)).

That split is one of the strongest reasons this code is useful here. It makes the
bootstrap boundary visible.

## 2. Dictionary Layout

The dictionary is a linked list of entries
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:174)).

The header shape is:

- 4-byte link pointer
- 1-byte length/flags field
- word name bytes
- zero padding up to a 4-byte boundary
- definition/code area

The length/flags byte is especially important:

- low 5 bits are name length
- top bits are flags
- in this implementation the notable flags are:
  - `F_IMMED = 0x80`
  - `F_HIDDEN = 0x20`
  - `F_LENMASK = 0x1f`
  ([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:623))

`LATEST` points at the most recently defined dictionary entry
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:191),
[Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1122)).

The key behavioral consequences are:

- lookup runs newest-first through link pointers
- redefining a word shadows earlier definitions
- hidden words are made invisible to `FIND`

This aligns strongly with the direction of `fythvm.dictionary.runtime`, where `latest`
is the head of the chain and lookup walks newest-first.

## 3. Threading Model

The heart of the implementation is indirect threaded code.

The `NEXT` macro is:

```asm
lodsl
jmp *(%eax)
```

([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:305))

Conceptually:

- `%esi` is the instruction pointer over the thread
- `lodsl` fetches the next cell from the thread
- that cell points to a codeword slot
- the indirect jump lands on the code pointer stored in that codeword slot

JonesForth spends a lot of prose distinguishing:

- direct threaded code
- indirect threaded code

and then commits to indirect threading so both:

- assembly primitives
- high-level Forth words

can share the same execution model
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:333)).

This is important for `fythvm` because it is a fully worked example of a system where
the execution model is not ordinary call/return semantics but an explicit threaded
continuation model.

## 4. `DOCOL` and the Return Stack

High-level Forth words use `DOCOL` as their codeword target
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:487)).

`DOCOL`:

- pushes the old `%esi` on the return stack
- advances `%eax` past the codeword slot
- makes `%esi` point at the first threaded item in the definition
- executes `NEXT`

Implementation:

```asm
DOCOL:
    PUSHRSP %esi
    addl $4,%eax
    movl %eax,%esi
    NEXT
```

([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:498))

The return stack is built on `%ebp`, while the data stack uses `%esp`
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:473)).

This means JonesForth has:

- one explicit stack for user parameters
- one explicit stack for threaded control-flow return state

That is directly relevant to any future `fythvm` execution work. It is also a reminder
that the return stack is not an incidental feature in a traditional Forth; it is part
of the execution model.

## 5. Built-In Words and Header Macros

JonesForth uses macros to define the built-in dictionary entries:

- `defword`
  - creates a standard Forth word header and uses `DOCOL` as codeword
  - threaded items follow
- `defcode`
  - creates a dictionary header whose codeword points at assembly code

([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:629),
[Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:675))

This is a useful pattern because it separates:

- dictionary metadata shape
- codeword target
- implementation style

The repo’s current generated-layout and wrapper work is not the same thing, but the
spirit is similar: make the mechanical structural shape explicit and reusable.

## 6. Built-In Variables and Constants

The assembly kernel exposes important global machine/runtime state as ordinary Forth
words via `defvar` and `defconst`:

- `STATE`
- `HERE`
- `LATEST`
- `S0`
- `BASE`
- `DOCOL`
- `F_IMMED`
- `F_HIDDEN`
- `F_LENMASK`

([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1109),
[Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1156))

This is noteworthy because it reflects a design preference:

- internal interpreter state is not hidden behind a private API
- it is surfaced as ordinary words that the system itself can manipulate

This is not always a design to copy directly, but it is very much in the same family as
`~/fyth`: make machine state explicit and available to the language.

## 7. Input Parsing and Number Parsing

The assembly kernel includes:

- `WORD`
  - token parsing into a static buffer
  ([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1364))
- `NUMBER`
  - base-sensitive numeric parsing
  ([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1422))
- `FIND`
  - dictionary lookup by header walk
  ([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1507))
- `>CFA` / `>DFA`
  - transforms between dictionary entry pointers and code/data field pointers
  ([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1554),
  [Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1601))

`FIND` is especially important because it bakes the hidden-word rule into lookup:

- hidden words appear as mismatched length due to masking logic
- newest-first traversal is simply the link walk from `LATEST`

That is a concrete dictionary lookup strategy worth keeping in mind when considering
future package/runtime changes.

## 8. `INTERPRET`, `CREATE`, `:`, and `;`

The key compiler/execution transition happens in the assembly kernel.

`INTERPRET`:

- reads a token with `WORD`
- tries `FIND`
- falls back to `NUMBER`
- behaves differently based on `STATE`
  - execute immediately in immediate mode
  - append codewords in compile mode
- handles immediate words by executing them even in compile mode

([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:2090))

`CREATE` builds just the dictionary header
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1776)).

Then `:` is defined in threaded Forth on top of `WORD`, `CREATE`, `DOCOL`, `HIDDEN`,
and `]`
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1869)).

`;` is an immediate word that:

- appends `EXIT`
- toggles hidden off
- returns to immediate mode

([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:1881))

This is one of the clearest examples in the codebase of the "tiny substrate, then the
compiler grows itself" pattern.

## 9. High-Level Compiler Growth in Forth

Once the kernel is up, the Forth layer extends the language in Forth itself.

Representative examples:

- `LITERAL`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:72))
- `[COMPILE]`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:99))
- `RECURSE`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:112))
- control structures:
  - `IF`, `THEN`, `ELSE`
  - `BEGIN`, `UNTIL`, `AGAIN`, `WHILE`, `REPEAT`
  - `UNLESS`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:138))

The notable design pattern is:

- compile-time control structures are just immediate words
- they emit `BRANCH` / `0BRANCH` and backfill offsets

This is exactly the sort of thing that makes Forth powerful and strange: syntax-like
control words are not compiler magic in some separate phase; they are ordinary words
with compile-time behavior.

## 10. Strings and Alignment

The Forth layer also handles:

- `ALIGN`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:437))
- `S"` and `."`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:465),
  [Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:514))

This is relevant because it shows the same byte/word/alignment concerns we have already
seen matter in `fythvm`:

- strings are emitted into the compiled image
- lengths are backfilled
- the resulting data is aligned to the machine cell boundary

The connection to this repo is strong: `variable-word-entry-layout` and the dictionary
runtime both depend on explicit byte-to-cell transitions.

## 11. Constants, Variables, and Values

The Forth layer builds richer data-definition words on top of `CREATE` and ordinary
threaded code:

- `CONSTANT`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:588))
- `VARIABLE`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:637))
- `VALUE`, `TO`, `+TO`
  ([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:697))

Two implementation details matter:

- `VARIABLE` allocates backing storage out of `HERE` and then creates a word that
  returns the address of that storage
- `VALUE` compiles a word whose body literally contains the current value, and `TO`
  compiles direct mutation of that embedded cell by address

Jones explicitly calls out that `VALUE` uses a kind of self-modifying code shape
([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:692)).

That is useful reference for thinking about dictionary entries as mixed metadata/code
records rather than as "just structs."

## 12. Introspection and Decompilation

JonesForth includes quite a bit of runtime reflection:

- `ID.`
- `?HIDDEN`
- `?IMMEDIATE`
- `WORDS`
- `FORGET`
- `DUMP`
- `CFA>`
- `SEE`

([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:741),
[Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:779),
[Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:990),
[Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:1022))

Two especially relevant design lessons:

- `CFA>` has to search backward through the dictionary because there is no reverse
  pointer from codeword to header
- `SEE` works by understanding meta-words such as `LIT`, `LITSTRING`, `BRANCH`,
  `0BRANCH`, and `EXIT`

This makes JonesForth a good reminder that tooling and visibility are not optional
luxuries in a reflective Forth system. They are part of how the system remains
understandable.

## 13. Execution Tokens, Anonymous Words, and Exceptions

The later Forth layer adds:

- `:NONAME`
- `[']`
- `CATCH`
- `THROW`
- `ABORT`
- `PRINT-STACK-TRACE`

([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:1181),
[Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:1288))

Notable implementation ideas:

- anonymous words are still created as dictionary entries, just unnamed
- execution tokens are first-class enough to support `EXECUTE`
- exceptions are implemented in Forth by placing exception frames on the return stack

This is not the most immediate priority for `fythvm`, but it is a strong example of how
far a small substrate can be pushed before needing more machine-level support.

## 14. Inline Assembler and `;CODE`

JonesForth also supports an inline assembler and assembler-defined words from within the
Forth layer:

- `NEXT` macro word
- `;CODE`
- register words
- inline instruction emitters
- `INLINE`

([Jonesforth.f.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.f.txt:1650))

This is one of the most striking pieces of the system because it shows the boundary
between:

- threaded high-level word definitions
- raw machine code emission

being reopened from inside the language itself.

The crucial implementation step in `;CODE` is:

- finish the current definition
- unhide it
- rewrite its codeword to point into its own DFA/data area, which now contains assembled
  machine code

This is a very Forth way of blurring the compiler/runtime boundary.

## 15. Boot Process and Host Dependence

This JonesForth is not bare metal. It is hosted on Linux/i386.

The assembly file:

- enters at `_start`
- stores the initial parameter stack pointer
- sets up a separate return stack
- allocates and initializes a data segment
- jumps into high-level `QUIT`

([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:563),
[Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:2272))

It also exposes Linux syscalls as primitive words
([Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:2191)).

So this is not a "pure abstract Forth." It is a hosted Forth with an intentionally tiny
host interface.

## 16. What Is Most Relevant To `fythvm`

The most relevant parts for this repo are:

### Dictionary shape

JonesForth reinforces that the real Forth dictionary is a linear-memory protocol:

- link
- packed flags/length
- name bytes
- alignment
- definition payload

That matches the direction already taken in:

- `variable-word-entry-layout`
- `ctypes-dictionary-runtime`
- `fythvm.dictionary.runtime`

### Bootstrap boundary

JonesForth is a strong example of where the bootstrap boundary sits:

- assembly substrate first
- self-hosted language growth second

This is useful as a reference when thinking about how much `fythvm` should try to
generate directly in low-level IR versus what should be built in a higher-level runtime
or DSL layer.

### Visibility and tooling

JonesForth spends real effort on:

- dictionary printing
- dumping
- decompilation
- stack traces

That validates the repo’s recent emphasis on:

- pure Python + `ctypes` reference runtimes
- readable generated layouts
- wrapper conventions
- debug-visible runtime structure

### Execution model reference

Even though direct execution work is not the immediate priority in `fythvm`, this code
is one of the clearest references for:

- threaded execution
- `NEXT`
- `DOCOL`
- return-stack discipline
- `EXECUTE`

When the repo eventually turns back toward execution, this folder should be treated as a
primary reference.

## 17. Limits Of This Reference

JonesForth is a good reference, but not a drop-in model.

Differences that matter:

- it is tightly tied to Linux/i386
- it is literal threaded Forth, not an LLVM/llvmlite system
- it uses direct machine stacks and machine code emission, not a JIT module model
- some of its reflective and self-modifying tricks are easier in its environment than
  they would be in a safer generated-IR architecture

So the right use of JonesForth here is:

- as a conceptual and structural reference
- not as a blueprint to transliterate mechanically

## Final Take

JonesForth is valuable in this repo because it makes several things unusually explicit:

- what a traditional dictionary record really looks like
- how the compiler grows out of a small substrate
- how threaded execution actually works
- how much of Forth can be implemented in Forth once the substrate exists

For `fythvm`, its biggest contribution is not any one trick. It is the reminder that a
good Forth implementation has to keep these three layers legible at the same time:

- memory layout
- execution model
- self-hosted language growth

This repo is already doing good work on the first and third layers. JonesForth is
especially useful as a reference when we eventually reconnect them to the second.
