# {{ title }}

## Question

What specific behavior or pattern is this lab trying to understand?

## Setup

Describe the minimal shape being constructed or varied.

If the lab has both raw and Pythonic variants, say which one is the source of truth
and what kind of readability improvement the Pythonic version is trying to earn.

## How to Run

```bash
uv run python explorations/lab/{{ slug }}/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/{{ slug }}/run.py
```

## What It Shows

Describe the expected output, IR, or behavior that demonstrates the result.
If there are raw and Pythonic variants, describe how they compare and what stays
structurally visible in the Pythonic form.

## Pattern / Takeaway

State the reusable lesson in plain language.
If there are two variants, make clear whether the takeaway is about the raw pattern,
the Pythonic wrapper, or the relationship between them.

## Non-Obvious Failure Modes

Document mistakes that are not simple syntax or obvious API misuse errors. Capture
the misunderstandings that a careful reader could still make until they trip over the
behavior in practice.

## Apply When

List the situations where this pattern is a good fit.

## Avoid When

List the situations where this pattern is misleading, overkill, or wrong.

## Next Questions

Capture remaining uncertainty or obvious follow-up experiments.
