# JonesForth Primitive Inventory

This document inventories the **assembly-defined primitive words** in
[Jonesforth.S.txt](./Jonesforth.S.txt), then narrows that list to the primitives most
relevant to `fythvm`, and finally maps those primitives onto the family thinking in
[docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1).

The `Category` column below is an **organizational grouping**, not a family. Families
remain the semantic/runtime split such as `payload-empty primitive`,
`payload-bearing primitive`, and `colon-thread`.

## Scope

For this inventory, a **primitive word** means a dictionary entry introduced by the
`defcode` macro in [Jonesforth.S.txt](./Jonesforth.S.txt). That gives us the assembly
kernel words, not:

- `defword` colon definitions such as `>DFA`, `QUIT`, `:`, `;`
- `defvar` variables such as `STATE`, `HERE`, `LATEST`
- `defconst` constants such as `DOCOL`, `F_IMMED`, `SYS_READ`
- internal implementation machinery such as `NEXT` and `DOCOL` themselves

That produces a set of **75** primitive words.

## Full Inventory

| Word | Line | Category | Suggested family |
| --- | ---: | --- | --- |
| `DROP` | 694 | stack manipulation | payload-empty primitive |
| `SWAP` | 698 | stack manipulation | payload-empty primitive |
| `DUP` | 705 | stack manipulation | payload-empty primitive |
| `OVER` | 710 | stack manipulation | payload-empty primitive |
| `ROT` | 715 | stack manipulation | payload-empty primitive |
| `-ROT` | 724 | stack manipulation | payload-empty primitive |
| `2DROP` | 733 | stack manipulation | payload-empty primitive |
| `2DUP` | 738 | stack manipulation | payload-empty primitive |
| `2SWAP` | 745 | stack manipulation | payload-empty primitive |
| `?DUP` | 756 | stack manipulation | payload-empty primitive |
| `1+` | 763 | arithmetic helper | payload-empty primitive |
| `1-` | 767 | arithmetic helper | payload-empty primitive |
| `4+` | 771 | arithmetic helper | payload-empty primitive |
| `4-` | 775 | arithmetic helper | payload-empty primitive |
| `+` | 779 | arithmetic | payload-empty primitive |
| `-` | 784 | arithmetic | payload-empty primitive |
| `*` | 789 | arithmetic | payload-empty primitive |
| `/MOD` | 802 | arithmetic | payload-empty primitive |
| `=` | 820 | comparison | payload-empty primitive |
| `<>` | 829 | comparison | payload-empty primitive |
| `<` | 838 | comparison | payload-empty primitive |
| `>` | 847 | comparison | payload-empty primitive |
| `<=` | 856 | comparison | payload-empty primitive |
| `>=` | 865 | comparison | payload-empty primitive |
| `0=` | 874 | comparison | payload-empty primitive |
| `0<>` | 882 | comparison | payload-empty primitive |
| `0<` | 890 | comparison | payload-empty primitive |
| `0>` | 898 | comparison | payload-empty primitive |
| `0<=` | 906 | comparison | payload-empty primitive |
| `0>=` | 914 | comparison | payload-empty primitive |
| `AND` | 922 | bitwise | payload-empty primitive |
| `OR` | 927 | bitwise | payload-empty primitive |
| `XOR` | 932 | bitwise | payload-empty primitive |
| `INVERT` | 937 | bitwise | payload-empty primitive |
| `EXIT` | 964 | control / threaded execution | payload-empty primitive |
| `LIT` | 1014 | inline operand handling | payload-bearing primitive |
| `!` | 1030 | memory | payload-empty primitive |
| `@` | 1036 | memory | payload-empty primitive |
| `+!` | 1042 | memory | payload-empty primitive |
| `-!` | 1048 | memory | payload-empty primitive |
| `C!` | 1061 | byte memory | payload-empty primitive |
| `C@` | 1067 | byte memory | payload-empty primitive |
| `C@C!` | 1075 | byte memory | payload-empty primitive |
| `CMOVE` | 1085 | byte memory | payload-empty primitive |
| `>R` | 1193 | return stack | payload-empty primitive |
| `R>` | 1198 | return stack | payload-empty primitive |
| `RSP@` | 1203 | return stack | payload-empty primitive |
| `RSP!` | 1207 | return stack | payload-empty primitive |
| `RDROP` | 1211 | return stack | payload-empty primitive |
| `DSP@` | 1222 | data stack | payload-empty primitive |
| `DSP!` | 1227 | data stack | payload-empty primitive |
| `KEY` | 1269 | I/O | payload-empty primitive |
| `EMIT` | 1314 | I/O | payload-empty primitive |
| `WORD` | 1364 | parser input | payload-empty primitive |
| `NUMBER` | 1422 | parser / conversion | payload-empty primitive |
| `FIND` | 1507 | dictionary lookup | payload-empty primitive |
| `>CFA` | 1584 | dictionary layout helper | payload-empty primitive |
| `CREATE` | 1776 | dictionary construction | payload-empty primitive |
| `,` | 1826 | compiler / memory append | payload-empty primitive |
| `[` | 1855 | compiler-state control | payload-empty primitive |
| `]` | 1860 | compiler-state control | payload-empty primitive |
| `IMMEDIATE` | 1915 | dictionary metadata | payload-empty primitive |
| `HIDDEN` | 1943 | dictionary metadata | payload-empty primitive |
| `'` | 1983 | xt lookup | payload-empty primitive |
| `BRANCH` | 2029 | inline control operand | payload-bearing primitive |
| `0BRANCH` | 2033 | inline control operand | payload-bearing primitive |
| `LITSTRING` | 2050 | inline string operand | payload-bearing primitive |
| `TELL` | 2059 | counted/string output | payload-empty primitive |
| `INTERPRET` | 2090 | outer interpreter core | payload-empty primitive |
| `CHAR` | 2200 | parser helper | payload-empty primitive |
| `EXECUTE` | 2207 | xt execution | payload-empty primitive |
| `SYSCALL3` | 2212 | host bridge | payload-empty primitive |
| `SYSCALL2` | 2221 | host bridge | payload-empty primitive |
| `SYSCALL1` | 2229 | host bridge | payload-empty primitive |
| `SYSCALL0` | 2236 | host bridge | payload-empty primitive |

## The `fythvm`-Relevant Slice

Not all JonesForth primitives matter equally for `fythvm` right now. If the goal is to
build the next stage of dictionary, family, and execution design, these are the ones that
carry the most design weight.

### Core execution shape

| Word | Why it matters |
| --- | --- |
| `EXIT` | Confirms that return from a colon/threaded word is itself a primitive behavior. |
| `EXECUTE` | Confirms that an `xt` is something execution can jump through directly. |
| `INTERPRET` | Shows the outer interpreter can itself be primitive kernel code. |

### Payload-bearing primitive behavior

| Word | Why it matters |
| --- | --- |
| `LIT` | Canonical example of a primitive whose behavior consumes inline payload after the current instruction. |
| `BRANCH` | Canonical example of payload-bearing control flow. |
| `0BRANCH` | Same, but conditional. |
| `LITSTRING` | Confirms inline payload is not limited to a single cell. |

### Dictionary and compiler primitives

| Word | Why it matters |
| --- | --- |
| `FIND` | Direct reference for newest-first linked dictionary lookup. |
| `>CFA` | Direct reference for code-field-address helpers. |
| `CREATE` | Direct reference for word construction at the dictionary level. |
| `,` | Direct reference for appending cells to the payload region. |
| `[` | Shows compile-state control as word metadata / compiler-state behavior, not a separate dictionary format. |
| `]` | Same. |
| `IMMEDIATE` | Confirms immediate is ordinary word metadata. |
| `HIDDEN` | Confirms hidden is ordinary word metadata used by lookup/compiler behavior. |
| `'` | Direct reference for xt lookup from dictionary names. |

### Parsing boundary

| Word | Why it matters |
| --- | --- |
| `WORD` | Shows that token acquisition is primitive enough to sit in the kernel. |
| `NUMBER` | Shows text-to-value interpretation as a distinct kernel concern. |
| `CHAR` | Another small but useful parser boundary marker. |

## What Families JonesForth Suggests

JonesForth strongly suggests that the important split is not “different dictionary entry
shapes first,” but rather “different **behavior families** over one common dictionary
contract.”

### 1. Payload-empty primitive family

This is the default primitive case:

- stack ops like `DUP`, `DROP`, `SWAP`
- arithmetic like `+`, `-`, `*`, `/MOD`
- comparisons like `=`, `<`, `0=`
- memory ops like `!`, `@`, `C!`, `C@`
- dictionary/compiler helpers like `FIND`, `CREATE`, `IMMEDIATE`, `HIDDEN`
- host bridge words like `SYSCALL0` … `SYSCALL3`

The pattern is:

- current `fythvm` would model the selector there as `handler_id`, selecting a
  primitive behavior
- `DFA` is usually empty for that word

That matches the direction already recorded in
[docs/word-family-contract.md](/Users/manny/fythvm/docs/word-family-contract.md:1).

### 2. Payload-bearing primitive family

JonesForth also clearly shows a second primitive family:

- `LIT`
- `BRANCH`
- `0BRANCH`
- `LITSTRING`

These are still primitive-dispatch words, but they interpret inline data after the current
instruction. That is the cleanest source support for keeping a distinct
**payload-bearing primitive** family in `fythvm`.

### 3. Colon / thread family

JonesForth does not define colon words with `defcode`; it uses:

- `DOCOL` as the shared behavior
- colon definitions as ordinary words whose codeword points to `DOCOL`

So JonesForth suggests a distinct family where:

- the shared behavior is `DOCOL`
- the payload after `DFA` is a thread of xts and inline operands

This is the direct reference for the `colon-thread` family in `fythvm`.

### 4. Dictionary-metadata and compiler-control primitives

JonesForth does not make these a separate dictionary shape. Instead, it keeps them inside
the primitive family:

- `IMMEDIATE`
- `HIDDEN`
- `[`
- `]`
- `'`
- `CREATE`
- `,`

That suggests `fythvm` should treat these as normal words whose behavior happens to affect
compiler state, dictionary metadata, or xt lookup, rather than inventing a new entry shape
for them.

## `fythvm` Takeaway

If we only ask “what families do the JonesForth primitives suggest?”, the answer is:

1. **payload-empty primitive**
2. **payload-bearing primitive**
3. **colon-thread**

Everything else in this source can be understood as:

- either members of the primitive family with different semantics
- or higher-level words built on top of those families

That is a good fit for the current `fythvm` workstream, because it keeps the family story
simple while still matching what the source actually does.
