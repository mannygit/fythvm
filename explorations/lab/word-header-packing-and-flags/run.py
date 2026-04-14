"""Demonstrate the v1 word-header packing model from `words.py`."""

from __future__ import annotations

from dataclasses import dataclass


CELL_SIZE = 8
LENGTH_MASK = 0x1F
HIDDEN_MASK = 0x40
IMMEDIATE_MASK = 0x80


def align_up(value: int, alignment: int) -> int:
    remainder = value % alignment
    return value if remainder == 0 else value + (alignment - remainder)


@dataclass(frozen=True)
class WordHeader:
    name: bytes
    hidden: bool = False
    immediate: bool = False

    def pack(self) -> bytes:
        if len(self.name) > LENGTH_MASK:
            raise ValueError(f"name is too long for a v1 header: {len(self.name)} > {LENGTH_MASK}")

        header = len(self.name)
        if self.hidden:
            header |= HIDDEN_MASK
        if self.immediate:
            header |= IMMEDIATE_MASK

        payload = bytes([header]) + self.name
        padded_length = align_up(len(payload), CELL_SIZE)
        return payload.ljust(padded_length, b"\x00")

    @classmethod
    def unpack(cls, blob: bytes) -> "UnpackedWord":
        if not blob:
            raise ValueError("cannot unpack an empty blob")

        header = blob[0]
        length = header & LENGTH_MASK
        if len(blob) < 1 + length:
            raise ValueError(
                f"blob is truncated: need at least {1 + length} bytes, got {len(blob)}"
            )

        return UnpackedWord(
            length=length,
            hidden=bool(header & HIDDEN_MASK),
            immediate=bool(header & IMMEDIATE_MASK),
            name=blob[1 : 1 + length],
            raw_header=header,
            padded_length=len(blob),
        )


@dataclass(frozen=True)
class UnpackedWord:
    length: int
    hidden: bool
    immediate: bool
    name: bytes
    raw_header: int
    padded_length: int


@dataclass(frozen=True)
class ComparisonResult:
    query: bytes
    hidden: bool
    immediate: bool
    status: str
    matched: bool | None


def header_bits(header: int) -> str:
    return f"{header:08b}"


def format_bytes(blob: bytes) -> str:
    return " ".join(f"{byte:02x}" for byte in blob)


def describe_packed(label: str, blob: bytes) -> None:
    unpacked = WordHeader.unpack(blob)
    print(f"{label}:")
    print(f"  packed bytes   : {format_bytes(blob)}")
    print(f"  header bits    : {header_bits(unpacked.raw_header)}")
    print(f"  decoded length : {unpacked.length}")
    print(f"  decoded hidden : {unpacked.hidden}")
    print(f"  decoded imm.   : {unpacked.immediate}")
    print(f"  decoded name   : {unpacked.name!r}")
    print(f"  padded length   : {unpacked.padded_length}")


def compare_visible(candidate_blob: bytes, query: bytes) -> ComparisonResult:
    unpacked = WordHeader.unpack(candidate_blob)
    if unpacked.hidden:
        return ComparisonResult(query=query, hidden=True, immediate=unpacked.immediate, status="skipped", matched=None)

    matched = unpacked.name == query
    return ComparisonResult(
        query=query,
        hidden=False,
        immediate=unpacked.immediate,
        status="match" if matched else "no-match",
        matched=matched,
    )


def show_comparison(label: str, candidate_blob: bytes, query: bytes) -> None:
    result = compare_visible(candidate_blob, query)
    query_text = query.decode("ascii", errors="replace")
    print(f"{label}:")
    print(f"  query          : {query_text!r}")
    print(f"  status         : {result.status}")
    print(f"  hidden         : {result.hidden}")
    print(f"  immediate      : {result.immediate}")
    print(f"  matched        : {result.matched}")


def decode_masked_header_byte(header: int) -> None:
    unpacked = WordHeader.unpack(bytes([header]) + b"abc")
    print("Masked header byte example:")
    print(f"  raw header     : 0x{header:02x}")
    print(f"  bits           : {header_bits(header)}")
    print(f"  decoded length : {unpacked.length}")
    print(f"  hidden         : {unpacked.hidden}")
    print(f"  immediate      : {unpacked.immediate}")
    print(f"  decoded name   : {unpacked.name!r}")


def main() -> None:
    visible = WordHeader(b"drop")
    immediate_visible = WordHeader(b"dup", immediate=True)
    hidden = WordHeader(b"secret", hidden=True)

    visible_blob = visible.pack()
    immediate_blob = immediate_visible.pack()
    hidden_blob = hidden.pack()

    print("== Question ==")
    print("How can a word header pack length and flags without conflating them with later dictionary layout?")
    print()

    print("== Canonical v1 Model ==")
    print("first byte = 5-bit length + hidden/immediate flags")
    print("rest = name bytes, padded to cell alignment")
    print(f"cell size = {CELL_SIZE} bytes")
    print(f"max name length = {LENGTH_MASK} bytes")
    print()

    print("== Packing ==")
    describe_packed("visible word", visible_blob)
    print()
    describe_packed("immediate word", immediate_blob)
    print()
    describe_packed("hidden word", hidden_blob)
    print()

    print("== Unpacking Limits ==")
    decode_masked_header_byte(0xE3)
    print()
    try:
        WordHeader(b"x" * 32).pack()
    except ValueError as exc:
        print("packing over the v1 name-length limit:")
        print(f"  {exc}")
    print()

    print("== Comparison ==")
    show_comparison("visible against matching query", visible_blob, b"drop")
    print()
    show_comparison("visible against non-matching query", visible_blob, b"swap")
    print()
    show_comparison("immediate metadata does not change lookup", immediate_blob, b"dup")
    print()
    show_comparison("hidden words are skipped", hidden_blob, b"secret")
    print()

    print("== Explicit Limits ==")
    print("This lab only models the lightweight v1 header from words.py.")
    print("It does not reconcile that model with the later dictionary/layout representation.")
    print("Immediate is metadata only here; hidden suppresses comparison/lookup.")


if __name__ == "__main__":
    main()
