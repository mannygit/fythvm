"""Compiler/meta-word metadata for parse-time words.

This layer sits next to runtime instruction metadata rather than inside it.

- runtime instruction descriptors are selected by ``CodeField.handler_id``
- compiler-word descriptors are selected by source token during parse/compile time
- both reuse ``HandlerRequirements`` so lowering/helper needs stay on one vocabulary
"""

from __future__ import annotations

from dataclasses import dataclass

from .instructions import HandlerRequirements


@dataclass(frozen=True, slots=True)
class CompilerWordDescriptor:
    """Package metadata for one compiler/meta word."""

    key: str
    requirements: HandlerRequirements
    immediate: bool
    compile_only: bool
    description: str


class CompilerWordRegistry:
    """Maps source tokens to compiler/meta word metadata."""

    def __init__(self, descriptors: dict[str, CompilerWordDescriptor] | None = None) -> None:
        self._descriptors: dict[str, CompilerWordDescriptor] = {}
        if descriptors is not None:
            for descriptor in descriptors.values():
                self.register(descriptor)

    def register(self, descriptor: CompilerWordDescriptor) -> None:
        self._descriptors[descriptor.key] = descriptor

    def descriptor_for_key(self, key: str) -> CompilerWordDescriptor | None:
        return self._descriptors.get(key)

    def snapshot(self) -> dict[str, CompilerWordDescriptor]:
        return dict(self._descriptors)


def _req(
    *,
    needs_source_cursor: bool = False,
    needs_thread_emitter: bool = False,
    needs_patch_stack: bool = False,
    needs_error_exit: bool = True,
    kernel: str | None = None,
) -> HandlerRequirements:
    return HandlerRequirements(
        needs_source_cursor=needs_source_cursor,
        needs_thread_emitter=needs_thread_emitter,
        needs_patch_stack=needs_patch_stack,
        needs_error_exit=needs_error_exit,
        kernel=kernel,
    )


def _descriptor(
    key: str,
    description: str,
    *,
    immediate: bool = True,
    compile_only: bool = True,
    requirements: HandlerRequirements | None = None,
) -> CompilerWordDescriptor:
    return CompilerWordDescriptor(
        key=key,
        requirements=HandlerRequirements() if requirements is None else requirements,
        immediate=immediate,
        compile_only=compile_only,
        description=description,
    )


DEFAULT_COMPILER_WORDS = CompilerWordRegistry(
    descriptors={
        'S"': _descriptor(
            'S"',
            "Parse a quoted string and emit a LITSTRING payload into the current definition.",
            requirements=_req(
                needs_source_cursor=True,
                needs_thread_emitter=True,
                kernel="compile_string_literal",
            ),
        ),
        "IF": _descriptor(
            "IF",
            "Emit a 0BRANCH placeholder and push a patch slot for the matching THEN.",
            requirements=_req(
                needs_thread_emitter=True,
                needs_patch_stack=True,
                kernel="compile_if",
            ),
        ),
        "THEN": _descriptor(
            "THEN",
            "Resolve the most recent IF placeholder against the current emitter position.",
            requirements=_req(
                needs_thread_emitter=True,
                needs_patch_stack=True,
                kernel="compile_then",
            ),
        ),
    }
)


def compiler_word_descriptor_for_key(
    key: str,
    *,
    registry: CompilerWordRegistry | None = None,
) -> CompilerWordDescriptor | None:
    active_registry = DEFAULT_COMPILER_WORDS if registry is None else registry
    return active_registry.descriptor_for_key(key)


__all__ = [
    "CompilerWordDescriptor",
    "CompilerWordRegistry",
    "DEFAULT_COMPILER_WORDS",
    "compiler_word_descriptor_for_key",
]
