# Result Carrier Phi Sentinels

## Question

When should a search carry its final answer through one exit block with a result phi, and how does that differ from the loop-carried phi that tracks scan position?

## Setup

This lab builds two pairs of llvmlite search functions over a small `i64[]` array:

- `find_first_ge_raw`, the raw source-of-truth version that computes the same behavior
  but forks to separate return blocks
- `find_first_ge_pythonic`, which uses a tiny local helper to centralize the result
  phi and keep the loop / found / not_found blocks easy to read
- `find_first_visible_length_value_raw`, a richer multi-stage search over simple
  records with `hidden`, `length`, and `value` fields
- `find_first_visible_length_value_pythonic`, the same staged search with the guard
  protocol and result phi bookkeeping centralized in a small helper

The first pair is a warm-up. The second pair is the main point of this lab: several
staged decisions converge on one exit block, while the loop-carried phi keeps only the
scan cursor alive and the result-carrying phi keeps the found value or sentinel.

That second pair is intentionally closer to the old `~/fyth` shape from
`WordName.compare(...)`: cheap reject, cheap reject, deeper compare, one semantic
result at the exit block.

The raw versions keep the control flow explicit. The Pythonic versions keep the same
CFG visible but make the result contract easier to read.

## How to Run

```bash
uv run python explorations/lab/result-carrier-phi-sentinels/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/result-carrier-phi-sentinels/run.py
```

## What It Shows

The output prints:

- the generated IR for both search shapes
- sample runtime results for matching and non-matching inputs
- the sentinel contract that makes `-1` mean "not found"

The important part is not just that both functions work. The raw versions keep the
search contracts explicit through direct block wiring. The Pythonic versions make the
meaning of the result explicit at one join point: one value comes out of the search,
and that value is either the found payload or the sentinel.

The helper does not hide the CFG. It only centralizes the exit phi and the repeated
guard-to-continue bookkeeping, while the loop cursor phi and the staged
`visible` / `same_length` / `same_value` blocks remain visible in the IR.

## Pattern / Takeaway

Use a final result phi when a search or staged comparison logically has one answer,
even if several control-flow paths can produce it.

This is cleaner than branching to separate returns because the exit block becomes the
single place where the semantic contract is defined. The IR says, in one location, what
the search means when it succeeds and what it means when it fails.

The more interesting multi-stage case shows the reusable shape from `~/fyth`: a hidden
check rejects early, a length check rejects early, and only then does the search pay
for the deeper value comparison. Those stages can converge on one eventual answer, but
the loop-carried phi is still only the cursor. The result phi carries the search
result; it should not be reused to track iteration state.

If the raw version is the clearest reference shape, keep it in the lab and let the
Pythonic version evolve around it. The raw version stays the truth table for the CFG;
the Pythonic version earns its keep by making the same structure easier to read.

## Non-Obvious Failure Modes

The easiest mistake is to treat `-1` as if LLVM itself understands "not found." It
does not. `-1` is only a sentinel because the host and the callee agree on that
contract. If `-1` is a legitimate data value in your domain, this pattern is the wrong
shape.

Another mistake is to think a verifier-valid function is automatically the clearest one.
The multi-return version here verifies just fine, but it is harder to reuse because the
meaning of the result is split across several exits instead of being carried through one
join.

It is also easy to conflate the loop cursor phi with the result phi. They solve
different problems. One tracks where the loop is scanning; the other carries what the
search found. Reusing a single Python variable name for both hides that distinction.

Another easy mistake is to send stage failures straight to the exit block. In the
multi-stage search, only the successful path should converge on the result phi; the
failed stages should keep scanning until the loop itself decides there is no match.

Another mistake is to let the helper become the abstraction instead of the CFG. The
helper should reduce boilerplate, not obscure which staged guard feeds the result phi
or which failures simply continue the scan.

## Apply When

Use this pattern when:

- a loop or staged comparison has one semantic answer
- the answer is either a found value or a reserved failure sentinel
- you want callers to consume a single exit contract instead of multiple returns
- multiple small decision stages should funnel into one eventual result without
  collapsing the loop cursor into the same variable
- the staged search naturally looks like cheap reject, cheap reject, deeper compare

## Avoid When

Do not use this pattern when the failure case needs richer information than a single
sentinel can carry. In that case, return a structured status/result pair or write into a
host-owned out parameter.

Do not use a sentinel at all if the sentinel value is valid business data. That makes
the contract ambiguous even if the IR is perfectly legal.

## Next Questions

- When should a search return a `{status, payload}` pair instead of a sentinel?
- How does this pattern change when the carried result is a pointer or aggregate?
- What is the cleanest way to generate these staged result-carrier searches from a
  higher-level AST?
