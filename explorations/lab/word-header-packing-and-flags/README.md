# Word Header Packing And Flags

## Question

How can a word header pack length plus `hidden` and `immediate` flags without
mixing that metadata into broader dictionary semantics?

## Setup

This lab treats the lightweight `~/fyth/src/fyth/words.py` model as canonical for
v1:

- the first byte stores a 5-bit length plus `hidden` and `immediate` flags
- the remaining bytes store the word name
- the packed blob is padded to cell alignment

The lab also keeps the semantics narrow on purpose:

- `hidden` means skip the word in comparison and lookup
- `immediate` is just explicit packed metadata
- the later dictionary/header model from other `fyth` code is not reconciled here

## How to Run

```bash
uv run python explorations/lab/word-header-packing-and-flags/run.py
```

Supported native host development is available on Intel macOS with Python 3.14.
Other local hosts should use Docker:

```bash
docker compose run --rm dev uv run python explorations/lab/word-header-packing-and-flags/run.py
```

## What It Shows

The output is intentionally labeled so you can see:

- the canonical packed header byte in binary and hex
- how unpacking recovers length, flags, and name bytes
- how cell padding affects the serialized layout
- how comparison behaves for visible, immediate, and hidden words
- what happens when the name length exceeds the 5-bit limit

The important result is that the metadata stays local to the header byte. A word
can be immediate without changing lookup behavior, and a hidden word is skipped
without pretending that its bytes are malformed.

## Pattern / Takeaway

Keep the header format small and explicit: one byte for length and flags, then the
name bytes, then padding.

Treat lookup and visibility as policy layered on top of packing, not as extra hidden
state inside the encoded word.

## Non-Obvious Failure Modes

The easiest mistake is to get the bit masks right in isolation but still misread the
header as if the flags were part of the length. The length lives in the low 5 bits;
the flags are separate.

Another common misunderstanding is to conflate `immediate` with lookup behavior.
In this v1 model, `immediate` is only metadata. It does not make a word visible,
hidden, or executable by itself.

The biggest trap is assuming the two older `fyth` header models are already
reconciled. They are not. This lab deliberately uses the lightweight `words.py`
shape only, so it stays honest about what v1 actually proves.

## Apply When

Use this pattern when:

- you need a compact, inspectable word-header format
- you want to reason about visibility and metadata separately from dictionary layout
- you are building exploratory tooling around name packing or word lookup rules

## Avoid When

Do not use this lab as a stand-in for the later dictionary representation, compile
state, or any broader word lifecycle semantics.

Do not assume the packed header is the final answer for all `fyth` word machinery.
It is intentionally a narrow first pass.

## Next Questions

- How should this header model connect to a linked dictionary without changing the
  packing rules?
- When should `hidden` flip, and which layer should own that transition?
- What extra validation belongs in a fuller word-definition pipeline?
