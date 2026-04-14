# Result Carrier Phi Sentinels

## Question

When should a loop's final phi carry the semantic result of a search instead of branching out to separate return blocks?

## Setup

This lab builds two llvmlite search functions over a small `i64[]` array:

- `find_first_ge_phi`, which uses one exit block and a final `phi` to carry either the
  matching value or `-1`
- `find_first_ge_multi_return`, which computes the same behavior but forks to separate
  return blocks

Both functions scan until they find the first value greater than or equal to a threshold.
The `phi` version keeps the result contract centralized in one place. The multi-return
version is still valid LLVM IR, but it spreads the same contract across several exits.

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

The important part is not just that both functions work. The `phi` version makes the
meaning of the search result explicit at the join point: one value comes out of the
search, and that value is either the found payload or the sentinel. That keeps the
semantic result in one SSA location instead of forcing callers to reconstruct it from
multiple return sites.

## Pattern / Takeaway

Use a final result phi when a search or staged comparison logically has one answer,
even if several control-flow paths can produce it.

This is cleaner than branching to separate returns because the exit block becomes the
single place where the semantic contract is defined. The IR says, in one location, what
the search means when it succeeds and what it means when it fails.

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

## Apply When

Use this pattern when:

- a loop or staged comparison has one semantic answer
- the answer is either a found value or a reserved failure sentinel
- you want callers to consume a single exit contract instead of multiple returns

## Avoid When

Do not use this pattern when the failure case needs richer information than a single
sentinel can carry. In that case, return a structured status/result pair or write into a
host-owned out parameter.

Do not use a sentinel at all if the sentinel value is valid business data. That makes
the contract ambiguous even if the IR is perfectly legal.

## Next Questions

- When should a search return a `{status, payload}` pair instead of a sentinel?
- How does this pattern change when the carried result is a pointer or aggregate?
- What is the cleanest way to generate these result-carrier phis from a higher-level AST?
