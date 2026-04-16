"""Named word-family descriptors and handler-id-to-family mapping."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class PayloadKind(Enum):
    """Broad payload interpretation categories for dictionary word families."""

    NONE = "none"
    INLINE_DATA = "inline_data"
    THREAD = "thread"
    FIELD_INTERPRETER = "field_interpreter"
    DEFINING_WORD = "defining_word"


@dataclass(frozen=True, slots=True)
class WordFamily:
    """Semantic family descriptor layered over the shared dictionary contract."""

    key: str
    payload_kind: PayloadKind
    description: str

    @property
    def has_payload(self) -> bool:
        return self.payload_kind is not PayloadKind.NONE


PRIMITIVE_EMPTY_FAMILY = WordFamily(
    key="primitive-empty",
    payload_kind=PayloadKind.NONE,
    description="Primitive-dispatch word with no family-interpreted payload after DFA.",
)

PRIMITIVE_PAYLOAD_FAMILY = WordFamily(
    key="primitive-payload",
    payload_kind=PayloadKind.INLINE_DATA,
    description="Primitive-dispatch word that interprets payload after DFA.",
)

COLON_THREAD_FAMILY = WordFamily(
    key="colon-thread",
    payload_kind=PayloadKind.THREAD,
    description="DOCOL-style word whose DFA holds a thread of xts and inline operands.",
)

SHARED_FIELD_INTERPRETER_FAMILY = WordFamily(
    key="shared-field-interpreter",
    payload_kind=PayloadKind.FIELD_INTERPRETER,
    description="Shared action whose payload is interpreted as per-word field data.",
)

DEFINING_WORD_PRODUCED_FAMILY = WordFamily(
    key="defining-word-produced",
    payload_kind=PayloadKind.DEFINING_WORD,
    description="Family produced by a defining word with family-specific DFA interpretation.",
)


class InstructionFamilyRegistry:
    """Maps stored handler ids to semantic word-family descriptors."""

    def __init__(
        self,
        *,
        default_family: WordFamily = PRIMITIVE_EMPTY_FAMILY,
        mapping: dict[int, WordFamily] | None = None,
    ) -> None:
        self._default_family = default_family
        self._mapping: dict[int, WordFamily] = {}
        if mapping is not None:
            for handler_id, family in mapping.items():
                self.register(handler_id, family)

    @property
    def default_family(self) -> WordFamily:
        return self._default_family

    def register(self, handler_id: int, family: WordFamily) -> None:
        if handler_id < 0 or handler_id > 0x7F:
            raise ValueError(f"handler_id must fit in 7 bits, got {handler_id}")
        self._mapping[handler_id] = family

    def register_many(self, handler_ids: Iterable[int], family: WordFamily) -> None:
        for handler_id in handler_ids:
            self.register(handler_id, family)

    def family_for_handler_id(self, handler_id: int) -> WordFamily:
        return self._mapping.get(handler_id, self._default_family)

    def snapshot(self) -> dict[int, WordFamily]:
        return dict(self._mapping)


DEFAULT_INSTRUCTION_FAMILIES = InstructionFamilyRegistry()


def family_for_handler_id(
    handler_id: int,
    *,
    registry: InstructionFamilyRegistry | None = None,
) -> WordFamily:
    active_registry = DEFAULT_INSTRUCTION_FAMILIES if registry is None else registry
    return active_registry.family_for_handler_id(handler_id)


__all__ = [
    "COLON_THREAD_FAMILY",
    "DEFAULT_INSTRUCTION_FAMILIES",
    "DEFINING_WORD_PRODUCED_FAMILY",
    "InstructionFamilyRegistry",
    "PRIMITIVE_EMPTY_FAMILY",
    "PRIMITIVE_PAYLOAD_FAMILY",
    "PayloadKind",
    "SHARED_FIELD_INTERPRETER_FAMILY",
    "WordFamily",
    "family_for_handler_id",
]
