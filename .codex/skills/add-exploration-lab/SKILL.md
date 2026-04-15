---
name: add-exploration-lab
description: Create or update exploratory labs under `explorations/lab` in this repository. Use when Codex is asked to add a new experiment, extend an existing exploration, capture a llvmlite concept in runnable code, document a discovered pattern, or update the exploration backlog and metadata so future agents can continue the work.
---

# Add Exploration Lab

## Overview

Add or update experiments in the repo's `explorations/` workspace without drifting from
the required lab contract. Keep labs runnable, demonstrative, and explicit about both
the learned pattern and any non-obvious failure modes discovered while building it.

## Read First

Read these repo files before making changes:

- `explorations/README.md` for the contract and authoring rules
- `explorations/BACKLOG.md` for the current queue and completion tracking
- `explorations/lab/_template/` for the required lab scaffold
- one existing concrete lab, especially `explorations/lab/llvmlite-minimal-jit-pipeline/`
- `tests/test_explorations.py` for the enforced metadata and README headings

## Workflow

1. Decide whether to create a new lab or extend an existing one.
2. If creating a new lab, pick a short slug that describes the concept, not the toy example.
3. Add or update the matching backlog item in `explorations/BACKLOG.md`.
4. Ensure the lab contains exactly the required baseline files:
   - `run.py`
   - `README.md`
   - `lab.toml`
5. Keep the code self-contained inside that lab directory unless a helper is clearly reusable.
6. Make the output intentionally demonstrative. Prefer labeled output, IR dumps, comparison
   cases, or small focused scenarios over raw debug noise.
7. Write the README so another engineer can understand:
   - what question the lab answers
   - what result it demonstrates
   - what reusable pattern was learned
   - when to apply that pattern
   - when not to apply it
   - which non-obvious failure modes or misunderstandings were discovered
8. Validate the lab by running the focused lab command and the repo tests.

When updating a builder-heavy existing lab, prefer a dual-style format:

- keep a raw IR-like version as the source of truth
- add a Pythonic companion version in the same lab when it genuinely improves readability

The Pythonic version should stay explainable against the raw baseline. Use context
managers and small helper objects first. Do not default to decorators, descriptors,
or broader "magic" layers unless the lab specifically proves that they help.

## Lab Requirements

Each lab `README.md` must include these headings:

- `## Question`
- `## Setup`
- `## How to Run`
- `## What It Shows`
- `## Pattern / Takeaway`
- `## Non-Obvious Failure Modes`
- `## Apply When`
- `## Avoid When` or `## Limits`
- `## Next Questions`

Treat `Non-Obvious Failure Modes` as a required knowledge-capture section. Use it for
mistakes that are not simple syntax issues or obvious API misuse, but mental-model
errors that are easy to make until you trip over them in practice.

`lab.toml` must include:

- `slug`
- `title`
- `summary`
- `status`
- `tags`
- `run`
- `agent_authored`

Use the canonical inner run command format:

```bash
uv run python explorations/lab/<slug>/run.py
```

## Backlog Rules

- Add new ideas to `Ready`.
- Move active work to `In Progress` only when there is real ongoing implementation.
- Move completed work to `Done` with the final lab path and a one-line takeaway.
- Keep backlog text short and decision-oriented.

## Validation

Run the focused lab and the exploration validator before finishing.

In cloud-agent Linux environments:

```bash
uv run python explorations/lab/<slug>/run.py
uv run pytest
```

For supported host-local development on Intel macOS with Python 3.14, run the lab
and tests directly with `uv`.

For other local hosts, use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/<slug>/run.py
docker compose run --rm dev uv run pytest
```

Do not add new dependencies casually for a lab. Prefer the existing repo environment unless
the exploration truly requires a repo-level dependency change.

Do not add a lab that merely runs. It should teach something reusable.
