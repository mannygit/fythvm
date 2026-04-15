"""Reusable, still-evolving code-generation building blocks for fythvm.

This package is the promotion boundary for ideas that have graduated from
`explorations/` into real library code. Treat it as an internal incubation layer:
in-repo consumers should use it, but its API is intentionally still allowed to move.
"""

from .exits import SharedExit
from .joins import Join
from .llvm import CompiledIRModule, compile_ir_module, configure_llvm
from .stack import AbstractStackAccess, ContextStructStackAccess
from .types import I16, I16_PTR, I32

__all__ = [
    "AbstractStackAccess",
    "CompiledIRModule",
    "ContextStructStackAccess",
    "I16",
    "I16_PTR",
    "I32",
    "Join",
    "SharedExit",
    "compile_ir_module",
    "configure_llvm",
]
