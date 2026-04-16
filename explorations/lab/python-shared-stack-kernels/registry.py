"""Operation metadata and collectors for the shared-stack-kernel lab."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class OperationSpec:
    """Metadata for one Forth-named operation implementation."""

    forth_name: str
    group: str
    variant: str
    kernel_name: str | None
    stack_effect: str
    func: Callable[[Any], None]


@dataclass(frozen=True)
class Scenario:
    """A runnable parity case for a group of operations."""

    label: str
    words: tuple[str, ...]
    build_state: Callable[[], Any]
    assert_state: Callable[[Any], None]
    note: str = ""


class OperationCollector:
    """Collect no-op decorated functions while preserving Forth naming."""

    def __init__(self, *, group: str, variant: str) -> None:
        self.group = group
        self.variant = variant
        self._specs: list[OperationSpec] = []

    def forth_op(
        self,
        forth_name: str,
        stack_effect: str,
        *,
        kernel_name: str | None = None,
    ) -> Callable[[Callable[[Any], None]], Callable[[Any], None]]:
        """Register one operation while leaving the callable unchanged."""

        def decorator(func: Callable[[Any], None]) -> Callable[[Any], None]:
            doc = func.__doc__ or ""
            first_line = doc.strip().splitlines()[0] if doc.strip() else ""
            required_prefix = f"{forth_name} {stack_effect}"
            if not first_line.startswith(required_prefix):
                raise ValueError(
                    f"{func.__name__} must start its docstring with {required_prefix!r}"
                )
            self._specs.append(
                OperationSpec(
                    forth_name=forth_name,
                    group=self.group,
                    variant=self.variant,
                    kernel_name=kernel_name,
                    stack_effect=stack_effect,
                    func=func,
                )
            )
            return func

        return decorator

    @property
    def specs(self) -> tuple[OperationSpec, ...]:
        return tuple(self._specs)

    def mapping(self) -> dict[str, OperationSpec]:
        return {spec.forth_name: spec for spec in self._specs}


__all__ = [
    "OperationCollector",
    "OperationSpec",
    "Scenario",
]
