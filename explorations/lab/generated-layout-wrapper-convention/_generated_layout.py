"""DO NOT EDIT: generated for the wrapper-convention lab.

Regenerate with:
  uv run python explorations/lab/generated-layout-wrapper-convention/generate_layout.py
"""

from __future__ import annotations

from llvmlite import ir

from fythvm.codegen import BitField, BoundStructView, StructField, StructHandle

I16 = ir.IntType(16)


class GeneratedCodeFieldView(BoundStructView):
    cell = StructField(0)
    handler_id = BitField(0, 0, 7)
    hidden = BitField(0, 7, 1)
    immediate = BitField(0, 8, 1)
    name_length = BitField(0, 9, 5)
    unused = BitField(0, 14, 2)


def generated_code_field_handle() -> StructHandle:
    return StructHandle.identified(
        'lab code field',
        'LabCodeField',
        I16,
        view_type=GeneratedCodeFieldView,
    )
