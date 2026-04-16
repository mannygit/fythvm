# JonesForth Primitive Stack-Shape Synthesis

This document focuses on the payload-empty primitives in JonesForth that are most
useful for `fythvm`'s next implementation pass. The goal is not just to restate the word
list, but to sort these words by:

- stack input/output shape
- the actual stack operation they perform
- the implementation skeleton they suggest

That should make it easier to spot where multiple words are really variants of the same
backend routine.

Primary source:

- [Jonesforth.S.txt](/Users/manny/fythvm/docs/references/forth/jonesforth/Jonesforth.S.txt:694)
- [primitive-inventory.md](/Users/manny/fythvm/docs/references/forth/jonesforth/primitive-inventory.md:1)

## Scope

Every word in this document is still an ordinary payload-empty primitive in the
JonesForth sense. Some of them manipulate memory or the return stack, but none of them
need a distinct family payload to explain their behavior.

Stack notation in this document follows normal Forth style:

- rightmost item is top of stack
- `x y -- y x` means `y` is the top item before execution
- return-stack effects are written separately when needed

## Requested Operations

### 1. Stack Manipulation

| Word | Stack effect | Core behavior | JonesForth implementation note |
| --- | --- | --- | --- |
| `DROP` | `( x -- )` | Remove top item. | Single pop and discard. |
| `SWAP` | `( x y -- y x )` | Exchange top two items. | Pop two, push back reversed. |
| `DUP` | `( x -- x x )` | Duplicate top item. | Read top without popping, push copy. |
| `OVER` | `( x y -- x y x )` | Copy second item to top. | Read one cell below top, push copy. |
| `ROT` | `( x y z -- y z x )` | Left-rotate top three items. | Pop three, push in rotated order. |
| `-ROT` | `( x y z -- z x y )` | Right-rotate top three items. | Same three-item permutation skeleton as `ROT`, different order. |
| `2DROP` | `( x y -- )` | Remove top two items. | Two pops and discard. |
| `2DUP` | `( x y -- x y x y )` | Duplicate top pair. | Read top two without consuming, push copies in same order. |
| `2SWAP` | `( a b c d -- c d a b )` | Exchange top pair with next pair. | Four-item permutation. |
| `?DUP` | `( x -- x x )` if `x != 0`, else `( x -- x )` | Conditional duplication of top item. | `DUP` plus zero test guard. |

These are the clearest examples of pure stack-shape primitives. They do not compute a
new arithmetic value and they do not inspect payload; they only rearrange, copy, or
remove stack cells.

### 2. Arithmetic Helpers / Arithmetic

| Word | Stack effect | Core behavior | JonesForth implementation note |
| --- | --- | --- | --- |
| `1+` | `( x -- x+1 )` | Increment top item by 1. | In-place update of top cell. |
| `1-` | `( x -- x-1 )` | Decrement top item by 1. | In-place update of top cell. |
| `4+` | `( x -- x+4 )` | Add 4 to top item. | In-place update of top cell. |
| `4-` | `( x -- x-4 )` | Subtract 4 from top item. | In-place update of top cell. |
| `+` | `( x y -- x+y )` | Add top two items. | Pop top, combine into next cell in place. |
| `-` | `( x y -- x-y )` | Subtract top item from next item. | Pop top, subtract from next cell in place. |
| `*` | `( x y -- x*y )` | Multiply top two items. | Pop both, compute, push one result. |
| `/MOD` | `( n d -- rem quot )` | Divide `n` by `d`, returning remainder and quotient. | Pop two, compute two results, push remainder then quotient. |

The helpers `1+`, `1-`, `4+`, and `4-` are not a different kind of word from `+` and
`-`. They are simply unary arithmetic variants with a baked-in constant and the same
ordinary primitive status.

### 3. Comparisons / Bitwise

| Word | Stack effect | Core behavior | JonesForth implementation note |
| --- | --- | --- | --- |
| `=` | `( x y -- flag )` | Equality test. | Pop two, push `0` or `1`. |
| `<>` | `( x y -- flag )` | Inequality test. | Same skeleton as `=` with different predicate. |
| `<` | `( x y -- flag )` | Less-than test. | Same binary comparison skeleton. |
| `>` | `( x y -- flag )` | Greater-than test. | Same binary comparison skeleton. |
| `<=` | `( x y -- flag )` | Less-than-or-equal test. | Same binary comparison skeleton. |
| `>=` | `( x y -- flag )` | Greater-than-or-equal test. | Same binary comparison skeleton. |
| `0=` | `( x -- flag )` | Zero test. | Pop one, test against zero, push `0` or `1`. |
| `0<>` | `( x -- flag )` | Non-zero test. | Same unary predicate skeleton. |
| `0<` | `( x -- flag )` | Negative test. | Same unary predicate skeleton. |
| `0>` | `( x -- flag )` | Positive test. | Same unary predicate skeleton. |
| `0<=` | `( x -- flag )` | Non-positive test. | Same unary predicate skeleton. |
| `0>=` | `( x -- flag )` | Non-negative test. | Same unary predicate skeleton. |
| `AND` | `( x y -- x&y )` | Bitwise AND. | Pop top, combine into next cell in place. |
| `OR` | `( x y -- x\|y )` | Bitwise OR. | Same binary combine skeleton. |
| `XOR` | `( x y -- x^y )` | Bitwise XOR. | Same binary combine skeleton. |
| `INVERT` | `( x -- ~x )` | Bitwise NOT. | In-place unary bitwise transform. |

These are still ordinary primitives. The comparison words differ from arithmetic only in
the value domain of the result: JonesForth returns `0` or `1`, not a distinct tagged
boolean object.

### 4. Memory Primitives

| Word | Stack effect | Core behavior | JonesForth implementation note |
| --- | --- | --- | --- |
| `!` | `( x addr -- )` | Store a cell to memory. | Pop address and value, write one cell. |
| `@` | `( addr -- x )` | Fetch a cell from memory. | Pop address, read one cell, push value. |
| `+!` | `( n addr -- )` | Add into cell at address. | Pop address and delta, update memory in place. |
| `-!` | `( n addr -- )` | Subtract from cell at address. | Same update-at-address skeleton as `+!`. |
| `C!` | `( x addr -- )` | Store low byte to memory. | Same as `!`, but byte width. |
| `C@` | `( addr -- x )` | Fetch byte from memory as a cell value. | Same as `@`, but byte width and zero-extend. |
| `C@C!` | `( src dst -- src+1 dst+1 )` | Copy one byte from source to destination, then advance both pointers. | Byte copy with post-increment on both addresses. |
| `CMOVE` | `( src dst len -- )` | Copy `len` bytes from source to destination. | Bulk byte copy; consumes all three arguments. |

These remain ordinary primitives even though they touch memory. The important point for
family design is that they still do not need per-word inline payload.

### 5. Return/Data Stack Control

| Word | Stack effect | Core behavior | JonesForth implementation note |
| --- | --- | --- | --- |
| `>R` | `( x -- )` and `( R: -- x )` | Move top data-stack item to return stack. | Pop from data stack, push to return stack. |
| `R>` | `( -- x )` and `( R: x -- )` | Move top return-stack item to data stack. | Pop from return stack, push to data stack. |
| `RSP@` | `( -- rsp )` | Push current return-stack pointer. | Snapshot return-stack pointer. |
| `RSP!` | `( rsp -- )` | Replace return-stack pointer. | Pop pointer and install it. |
| `RDROP` | `( -- )` and `( R: x -- )` | Drop top return-stack item. | Advance return-stack pointer. |
| `DSP@` | `( -- dsp )` | Push current data-stack pointer. | Snapshot data-stack pointer. |
| `DSP!` | `( dsp -- )` | Replace data-stack pointer. | Pop pointer and install it. |

These words are still structurally ordinary primitives, but they are the clearest sign
that "ordinary primitive" does not mean "only touches the data stack." It means the code
field alone determines the behavior.

## Synthesis By Implementation Shape

The useful implementation question is not only "what category is this word in?" but also
"how many backend templates do we really need?"

### A. Pure Stack-Shuffle Templates

These words are mostly permutations, copies, and drops over a fixed small window of stack
cells.

| Template | Words | Shared shape |
| --- | --- | --- |
| discard 1 | `DROP` | `( x -- )` |
| discard 2 | `2DROP` | `( x y -- )` |
| duplicate top | `DUP` | `( x -- x x )` |
| conditional duplicate top | `?DUP` | `( x -- x )` or `( x -- x x )` |
| copy deeper item | `OVER` | `( x y -- x y x )` |
| swap 2 | `SWAP` | `( x y -- y x )` |
| rotate 3 | `ROT`, `-ROT` | `( x y z -- ... )` |
| duplicate pair | `2DUP` | `( x y -- x y x y )` |
| swap pair with pair | `2SWAP` | `( a b c d -- c d a b )` |

This suggests a compact internal abstraction:

- `drop_n(n)`
- `dup_top()`
- `dup_top_if_nonzero()`
- `copy_from_depth(depth)`
- `permute(k, order)`
- `dup_segment(width)`

`ROT` and `-ROT` are especially strong evidence for a shared permutation helper rather
than two unrelated implementations.

### B. Unary In-Place Top-Cell Transform

These words all conceptually read one cell and write one replacement cell to the same top
position.

| Template | Words | Shared shape |
| --- | --- | --- |
| unary arithmetic immediate | `1+`, `1-`, `4+`, `4-` | `( x -- x' )` |
| unary bitwise transform | `INVERT` | `( x -- x' )` |

JonesForth implements these literally in place on `(%esp)`. That does not force the same
machine strategy in `fythvm`, but it strongly suggests one IR-level lowering template:

- load top cell
- apply unary operator or constant delta
- store back to top cell

### C. Unary Predicate

These words consume one cell and produce one boolean-like cell.

| Template | Words | Shared shape |
| --- | --- | --- |
| compare against zero | `0=`, `0<>`, `0<`, `0>`, `0<=`, `0>=` | `( x -- flag )` |

This is a single family of variants differentiated only by predicate:

- `eq_zero`
- `ne_zero`
- `lt_zero`
- `gt_zero`
- `le_zero`
- `ge_zero`

### D. Binary Reducer To One Result

These words consume two cells and leave one cell.

| Template | Words | Shared shape | Important variation |
| --- | --- | --- | --- |
| binary arithmetic reducer | `+`, `-`, `*` | `( x y -- r )` | arithmetic result |
| binary predicate reducer | `=`, `<>`, `<`, `>`, `<=`, `>=` | `( x y -- flag )` | boolean result |
| binary bitwise reducer | `AND`, `OR`, `XOR` | `( x y -- r )` | bitwise result |

There are really two useful sub-observations here.

First, all of these words share the same high-level stack contract:

- pop right operand
- pop or expose left operand
- apply operator
- push or overwrite with result

Second, JonesForth splits them into two low-level implementation styles:

- in-place binary combine over the next-on-stack cell:
  `+`, `-`, `AND`, `OR`, `XOR`
- pop-two / compute / push-one:
  `*`, `=`, `<>`, `<`, `>`, `<=`, `>=`

So if `fythvm` wants maximum deduplication, there are two reasonable abstraction levels:

1. one semantic template for all binary `2 -> 1` words
2. two lowering templates if in-place update versus rebuild matters in the backend

### E. Binary To Two Results

| Template | Words | Shared shape |
| --- | --- | --- |
| divide with paired outputs | `/MOD` | `( n d -- rem quot )` |

`/MOD` is the main arithmetic outlier in this set. It still has ordinary primitive
status, but it needs a distinct multi-result lowering path.

The important design point is that it is still close to the binary reducer family:

- two inputs
- one arithmetic operation
- but two outputs instead of one

That makes it a variant of "binary arithmetic kernel" rather than a fundamentally
different family.

### F. Memory Load/Store/Update Templates

| Template | Words | Shared shape | Important variation |
| --- | --- | --- | --- |
| store | `!`, `C!` | `( x addr -- )` | cell width vs byte width |
| fetch | `@`, `C@` | `( addr -- x )` | cell width vs byte width |
| update at address | `+!`, `-!` | `( n addr -- )` | add vs subtract |

This is one of the clearest places where implementation reuse should pay off. The shape
is stable and the differences are small:

- data width: cell or byte
- update operator: assign, add, subtract
- readback policy: no result for store/update, one result for fetch

### G. Memory Copy Templates

| Template | Words | Shared shape | Notes |
| --- | --- | --- | --- |
| byte copy with pointer advance | `C@C!` | `( src dst -- src+1 dst+1 )` | special because it both performs I/O to memory and returns advanced pointers |
| block copy | `CMOVE` | `( src dst len -- )` | bulk copy, no returned pointers |

These two do not fit cleanly into simple load/store/update, but they do fit together as
"copy kernels." `C@C!` is the scalar stepping form; `CMOVE` is the bulk form.

### H. Cross-Stack Transfer Templates

| Template | Words | Shared shape |
| --- | --- | --- |
| data to return | `>R` | `( x -- )`, `( R: -- x )` |
| return to data | `R>` | `( -- x )`, `( R: x -- )` |
| drop on return stack | `RDROP` | `( -- )`, `( R: x -- )` |

`>R` and `R>` are obvious inverses. `RDROP` is the same general space: return-stack
consumption without a data-stack result.

If `fythvm` exposes the return stack explicitly in the runtime model, these likely want a
shared transfer/drop helper rather than ad hoc word-by-word code.

### I. Stack-Pointer Snapshot/Install Templates

| Template | Words | Shared shape |
| --- | --- | --- |
| pointer snapshot | `RSP@`, `DSP@` | `( -- ptr )` |
| pointer install | `RSP!`, `DSP!` | `( ptr -- )` |

These are almost perfect pairs. The only varying parameter is which stack pointer is
being addressed.

That suggests four words can collapse to two generic helpers:

- `get_stack_pointer(kind)`
- `set_stack_pointer(kind)`

## Highest-Value Commonality Map

If the goal is "do not repeat ourselves in implementation," the densest clusters are:

1. `ROT` / `-ROT` / `SWAP` / `2SWAP`
   These are all finite-window permutations.
2. `DUP` / `OVER` / `2DUP` / `?DUP`
   These are all copy-oriented stack shapers.
3. `1+` / `1-` / `4+` / `4-` / `INVERT`
   These are unary top-cell transforms.
4. `0=` / `0<>` / `0<` / `0>` / `0<=` / `0>=`
   These are unary predicates.
5. `+` / `-` / `*` / `=` / `<>` / `<` / `>` / `<=` / `>=` / `AND` / `OR` / `XOR`
   These are binary reducers, split only by operator and result kind.
6. `!` / `C!` and `@` / `C@`
   These are width variants of the same store/fetch operations.
7. `+!` / `-!`
   These are update-at-address variants.
8. `RSP@` / `DSP@` and `RSP!` / `DSP!`
   These are stack-pointer accessor pairs.
9. `>R` / `R>` / `RDROP`
   These are return-stack transfer/drop operations.

The main words that deserve their own special-case lowering are:

- `/MOD`
- `C@C!`
- `CMOVE`
- `2DROP`

Even there, only `/MOD`, `C@C!`, and `CMOVE` are truly unusual. `2DROP` is still just
the obvious `drop_n(2)` case.

## Practical Takeaway For `fythvm`

For implementation planning, the requested words do not look like dozens of unrelated
primitives. They look much closer to a small set of reusable kernels:

1. stack permutation/copy/drop
2. unary top-cell transform
3. unary predicate
4. binary reducer
5. binary multi-result arithmetic
6. memory fetch/store/update
7. memory copy
8. cross-stack transfer
9. stack-pointer snapshot/install

That is probably the right level to aim for in `fythvm`: preserve the surface primitive
names, but lower them through a much smaller number of shared implementation shapes.
