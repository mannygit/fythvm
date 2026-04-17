"""Reusable, still-evolving code-generation building blocks for fythvm.

This package is the promotion boundary for ideas that have graduated from
`explorations/` into real library code. Treat it as an internal incubation layer:
in-repo consumers should use it, but its API is intentionally still allowed to move.
"""

from .bytes import compare_aligned_i32_regions
from .exits import SharedExit
from .interpreter import FetchedCell, emit_tagged_cell_dispatch
from .joins import Join
from .llvm import CompiledIRModule, compile_ir_module, configure_llvm
from .dispatch import SwitchCaseSpec, SwitchDispatcher
from .loops import ParamLoop
from .stack import (
    AbstractStackAccess,
    BoundStackAccess,
    ContextStructStackAccess,
    PoppedPair,
    StructViewStackAccess,
)
from .structs import BitField, BoundBitField, BoundStructField, BoundStructView, StructField, StructHandle
from .thread import CurrentWordThreadIR, ThreadCursorIR, ThreadJumpIR, ThreadRefIR
from .types import I16, I16_PTR, I32

__all__ = [
    "AbstractStackAccess",
    "BoundStackAccess",
    "BoundStructField",
    "BoundBitField",
    "BoundStructView",
    "BitField",
    "CompiledIRModule",
    "compare_aligned_i32_regions",
    "ContextStructStackAccess",
    "FetchedCell",
    "I16",
    "I16_PTR",
    "I32",
    "Join",
    "ParamLoop",
    "PoppedPair",
    "SharedExit",
    "StructField",
    "StructHandle",
    "StructViewStackAccess",
    "SwitchCaseSpec",
    "SwitchDispatcher",
    "ThreadCursorIR",
    "ThreadJumpIR",
    "CurrentWordThreadIR",
    "ThreadRefIR",
    "compile_ir_module",
    "emit_tagged_cell_dispatch",
    "configure_llvm",
]
