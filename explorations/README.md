# Explorations

`explorations/` is the home for runnable research artifacts that are useful to keep
around but do not belong in the core package or test suite.

Each lab should answer a concrete question with code and an explanation that makes
the result reusable later. A finished lab is not just a scratch script. It should
make the pattern or takeaway obvious enough that another engineer can tell when to
apply it and when not to.

## Layout

- `BACKLOG.md` tracks exploration ideas and status.
- `lab/` contains one subdirectory per exploration.
- `lab/_template/` is the scaffold for new labs.

## Lab Contract

Every lab lives at `explorations/lab/<slug>/` and must include:

- `run.py`: the canonical runnable entrypoint.
- `README.md`: the human-facing explanation.
- `lab.toml`: machine-readable metadata.

The canonical inner run command is:

```bash
uv run python explorations/lab/<slug>/run.py
```

On local macOS or Windows development, wrap that with Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/<slug>/run.py
```

## Authoring Guidelines

Start from `explorations/lab/_template/`.

Keep each lab self-contained in its own directory. If a lab needs helpers, keep
them local to that lab unless the helpers are clearly reusable across multiple
explorations.

Prefer existing repo dependencies. Adding new dependencies is a repo-level decision
and should not be done casually from a lab.

`run.py` should produce intentionally demonstrative output. Prefer labeled output,
generated IR, comparison cases, or small focused examples over undifferentiated
debug prints.

Each lab `README.md` must include:

- `Question`
- `Setup`
- `How to Run`
- `What It Shows`
- `Pattern / Takeaway`
- `Non-Obvious Failure Modes`
- `Apply When`
- `Avoid When` or `Limits`
- `Next Questions`

Those sections are required because the goal is to preserve reusable knowledge, not
just archive executable snippets.

Document non-obvious failure modes explicitly. This means the kinds of mistakes that
are easy to make even when the code is syntactically valid and the API calls look
plausible, but the mental model is wrong. These are the "you only learn this by
doing" traps: lifetime requirements, ordering constraints, implicit invariants, and
other behavior that is easy to misunderstand if you have only read the API surface.

## Agent Workflow

AI agents should:

1. Pick an item from `BACKLOG.md` or add a new one before starting.
2. Copy `lab/_template/` into a new slugged directory.
3. Build a runnable example plus an explanation that makes the result interpretable.
4. Update `BACKLOG.md` when the lab is complete and link the finished directory.

A lab is only complete if another engineer can run it later, read the explanation,
and understand both the result and the situations where the learned pattern should
or should not be used.
