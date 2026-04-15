"""Shared llvmlite integer types used across code generation helpers."""

from __future__ import annotations

from llvmlite import ir


I16 = ir.IntType(16)
I16_PTR = I16.as_pointer()
I32 = ir.IntType(32)
