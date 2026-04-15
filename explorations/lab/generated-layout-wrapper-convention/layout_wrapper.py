"""EDIT THIS FILE: ergonomic wrapper over the generated layout for the lab."""

from __future__ import annotations

from llvmlite import ir

from fythvm.codegen import StructHandle

from _generated_layout import GeneratedCodeFieldView


I1 = ir.IntType(1)
I5 = ir.IntType(5)
I7 = ir.IntType(7)
I16 = ir.IntType(16)
I32 = ir.IntType(32)


class CodeFieldView(GeneratedCodeFieldView):
    def write_header(
        self,
        *,
        instruction: ir.Value,
        hidden: ir.Value,
        immediate: ir.Value,
        name_length: ir.Value,
    ) -> None:
        self.instruction.store(instruction)
        self.hidden.store(hidden)
        self.immediate.store(immediate)
        self.name_length.store(name_length)
        self.unused.store(ir.IntType(2)(0))

    def load_header_score(self) -> ir.Value:
        builder = self.builder
        total = builder.zext(self.instruction.load(), I32, name="instruction_i32")
        total = builder.add(total, builder.zext(self.hidden.load(), I32, name="hidden_i32"), name="with_hidden")
        total = builder.add(
            total,
            builder.zext(self.immediate.load(), I32, name="immediate_i32"),
            name="with_immediate",
        )
        return builder.add(
            total,
            builder.zext(self.name_length.load(), I32, name="name_length_i32"),
            name="header_score",
        )


def code_field_handle() -> StructHandle:
    return StructHandle.identified(
        "lab code field",
        "LabCodeField",
        I16,
        view_type=CodeFieldView,
    )
