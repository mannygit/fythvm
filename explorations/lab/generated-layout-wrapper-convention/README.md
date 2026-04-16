# Generated Layout Wrapper Convention

## Question

Where should ergonomic customization live when a layout file is generated and must
remain regenerable?

## Setup

This lab uses a deliberately small split:

- `_generated_layout.py`
  - generated
  - marked `DO NOT EDIT`
- `layout_wrapper.py`
  - hand-authored
  - marked `EDIT THIS FILE`

The generated file exposes the schema-derived core. The wrapper file adds the
ergonomic methods that another engineer is actually meant to touch.

The generated file is the source of truth for schema-derived structure. The wrapper is
the source of truth for developer ergonomics.
In the concrete example here, the generated core exposes `CodeField` with a
`handler_id` bitfield, and the wrapper keeps the surrounding naming explicit and
readable.

## How to Run

```bash
uv run python explorations/lab/generated-layout-wrapper-convention/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/generated-layout-wrapper-convention/run.py
```

## What It Shows

The run prints:

- the generated file source
- the wrapper file source
- the emitted IR
- a raw write path that uses only generated fields
- a wrapper path that uses the hand-authored helper methods

The important contrast is not semantic correctness alone. It is editing convention:
the generated file stays mechanical and regenerable, while the wrapper is where naming
and helper ergonomics live.

## Pattern / Takeaway

Use a two-file convention when generated layout code needs ergonomic customization:

- generated core: `DO NOT EDIT`
- neighboring wrapper: `EDIT THIS FILE`

That keeps regeneration simple and still gives engineers a clear place to add
well-named helpers.

## Non-Obvious Failure Modes

One easy mistake is trying to "just tweak one thing" in the generated file because it
looks small. That creates invisible debt: regeneration either blows the edit away or
forces the generator to become special-case aware later.

Another easy mistake is pushing too much logic into the wrapper until it stops being a
thin ergonomic layer and starts hiding the real layout. The wrapper should make the
generated core easier to use, not replace the mental model.

## Apply When

- the generated file is meant to be deterministic and mechanical
- engineers still need naming and helper ergonomics
- regeneration should remain safe and boring

## Avoid When

- there is no stable generated core yet
- the wrapper would mostly duplicate the generated file
- the real customization point should live in schema or generator metadata instead

## Next Questions

- When should helper methods stay in the wrapper versus move into schema metadata?
- How should multiple wrapper layers work if one team wants local convenience methods
  and another wants project-wide conventions?
- What is the cleanest way to expose extension points without making generated output
  depend on arbitrary hand-authored files?
