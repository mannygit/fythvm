# Cell RPN Calculator

## Question

What is the smallest useful raw-cell RPN calculator once the program is a runtime
buffer of 16-bit cells instead of text, the stack lives in a passed context struct,
and `=` is the only explicit exit instruction?

## Setup

This lab builds one tiny calculator machine over a buffer of `i16` cells.

The cell contract is:

- top bit clear: literal operand `0..32767`
- top bit set: operator opcode in the low byte
- supported operators: `+`, `-`, `*`, `/`, `%`, `=`

The evaluator is a runtime interpreter, not a compiler for one fixed expression.
The host passes a live cell buffer, a context struct that owns the calculator stack,
and an out pointer for the final result.

The lab has two runnable variants:

- `eval_cells_raw`, the source-of-truth version with explicit loop, dispatch, stack
  field GEPs, and shared exit phis
- `eval_cells_pythonic`, which keeps the same interpreter shape but factors three
  learned boundaries into local helpers:
  - context-backed stack access, following `context-struct-stack-storage`
  - a shared status/result exit helper, following `result-carrier-phi-sentinels`
  - repetitive dispatch block generation, while keeping the opcode CFG visible

This is deliberately cell-based, not text-based. The host harness prints a readable
rendering like `2,1,1,+,+,=` only as display sugar for the raw cells.

For the lower-level stack building blocks behind this, see
[llvmlite-jit-stack-operations](/Users/manny/fythvm/explorations/lab/llvmlite-jit-stack-operations/README.md:1)
and
[context-struct-stack-storage](/Users/manny/fythvm/explorations/lab/context-struct-stack-storage/README.md:1).
For the loop/join mental model behind the instruction-pointer threading and shared
exit block, see
[block-parameter-joins](/Users/manny/fythvm/explorations/lab/block-parameter-joins/README.md:1)
and
[result-carrier-phi-sentinels](/Users/manny/fythvm/explorations/lab/result-carrier-phi-sentinels/README.md:1).

## How to Run

```bash
uv run python explorations/lab/cell-rpn-calculator/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/cell-rpn-calculator/run.py
```

## What It Shows

The output prints:

- the raw and Pythonic evaluator IR
- successful cell programs such as:
  - `2,1,1,+,+,=` -> `4`
  - `100,10,/,=` -> `10`
- failure cases for:
  - stack underflow
  - divide by zero
  - bad opcode
  - missing `=`
  - bad stack shape at `=`
  - stack overflow
- a parity check proving the raw and Pythonic variants return the same status,
  result, stack pointer, and logical stack trace for every scenario

The important part is that the machine input is always the raw cell buffer. The text
rendering is only there so the host-side traces are readable.

## Pattern / Takeaway

If you want a tiny stack-based interpreter, keep three things explicit at the same
time:

1. the raw cell encoding
2. the loop-carried instruction pointer
3. the context-backed stack state

That makes the calculator interpretable as a real machine instead of a disguised text
parser or expression evaluator.

The reusable boundary is the same one the stack labs converged on: keep stack
semantics separate from pointer derivation. Here the concrete storage is always a
context struct, but the Pythonic version still earns its keep by isolating:

- how the stack base and `sp` field are reached
- how the shared status/result exit is collected
- how repetitive opcode blocks are emitted without hiding the CFG

`=` is intentionally the only exit instruction. That keeps the return contract
concrete: either the program exits with exactly one value on the stack, or it fails
with an explicit status code.

## Non-Obvious Failure Modes

The easiest mistake is to slide back into a text mental model. This machine does not
parse characters. It executes tagged 16-bit cells. The host-side `2,1,1,+,+,=`
rendering is only a readable projection of those cells.

Another easy mistake is to think "literal" means signed immediate. It does not here.
Only `0..32767` are encoded directly. Negative values can still appear, but only as
the result of arithmetic on the stack.

It is also easy to conflate "program ended" with "program succeeded." Reaching
`cell_count` without `=` is a distinct failure, and reaching `=` with extra stack
items is another distinct failure. The evaluator is intentionally strict so those
contracts stay visible.

The shared exit block can also be misunderstood as unnecessary ceremony. It is doing
real work: centralizing one `{status, result}` contract even though several error
paths and the success path can terminate evaluation.

Finally, it is easy to abstract the Pythonic version too far. If the helper layer
hides where `ip` advances, which opcode block handles division-by-zero, or how the
stack field pointers are derived from the context struct, it has stopped being a
readability layer and become a second machine.

## Apply When

Use this pattern when:

- you want a tiny stack-based interpreter over a raw cell buffer
- you want the machine contract to be binary/cell oriented, not text oriented
- the interesting state is one stack plus one loop-carried instruction pointer
- you want a visible `{status, result}` exit contract instead of ad hoc returns
- you want to combine stack/context and phi/join learnings in one small runnable
  interpreter

## Avoid When

Do not use this as a general calculator parser. It intentionally avoids text input,
precedence rules, symbolic parsing, or a larger user-facing language.

Do not use this encoding if negative literals need to appear directly in the program
cells. This lab intentionally spends the high bit on operand-vs-operator tagging.

Avoid making the Pythonic variant the only version. The raw evaluator is what keeps
the cell contract, loop structure, and exit semantics honest.

## Next Questions

- When should the cell tag space grow beyond one high-bit split into a richer opcode
  family?
- What changes if stack effects become richer than binary arithmetic and `=`?
- When does this interpreter shape want direct-threaded `musttail` dispatch instead
  of one loop-and-switch evaluator?
- Should a follow-on lab add signed-immediate encoding or more explicit overflow
  behavior?
