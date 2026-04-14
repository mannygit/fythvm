# {{ title }}

## Question

What specific behavior or pattern is this lab trying to understand?

## Setup

Describe the minimal shape being constructed or varied.

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

## Pattern / Takeaway

State the reusable lesson in plain language.

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
