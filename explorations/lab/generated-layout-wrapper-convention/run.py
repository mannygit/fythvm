"""Demonstrate generated-layout core plus hand-authored wrapper convention."""

from __future__ import annotations

import ctypes
import importlib
import inspect
import sys
from pathlib import Path

from llvmlite import binding, ir

from fythvm.codegen import compile_ir_module, configure_llvm


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import generate_layout  # noqa: E402
import layout_wrapper  # noqa: E402
import _generated_layout  # noqa: E402


I1 = ir.IntType(1)
I5 = ir.IntType(5)
I7 = ir.IntType(7)
I16 = ir.IntType(16)
I32 = ir.IntType(32)


def refresh_generated_modules() -> str:
    expected = generate_layout.generate()
    current = (ROOT / "_generated_layout.py").read_text()
    if current != expected:
        raise AssertionError("committed generated file drifted from generator output")
    importlib.reload(_generated_layout)
    importlib.reload(layout_wrapper)
    return expected


def build_module() -> ir.Module:
    configure_llvm()
    module = ir.Module(name="generated_layout_wrapper_convention")
    module.triple = binding.get_default_triple()

    generated_handle = _generated_layout.generated_code_field_handle()
    wrapper_handle = layout_wrapper.code_field_handle()
    code_field_global = wrapper_handle.define_global(module, "code_field_data", I16(0))

    raw_fn = ir.Function(module, ir.FunctionType(I16, []), name="raw_write")
    builder = ir.IRBuilder(raw_fn.append_basic_block("entry"))
    generated = generated_handle.bind(builder, code_field_global)
    generated.handler_id.store(I7(9))
    generated.hidden.store(I1(1))
    generated.immediate.store(I1(0))
    generated.name_length.store(I5(6))
    generated.unused.store(ir.IntType(2)(0))
    builder.ret(generated.cell.load())

    wrapper_fn = ir.Function(module, ir.FunctionType(I16, []), name="wrapper_write")
    builder = ir.IRBuilder(wrapper_fn.append_basic_block("entry"))
    wrapped = wrapper_handle.bind(builder, code_field_global)
    wrapped.write_header(
        handler_id=I7(33),
        hidden=I1(0),
        immediate=I1(1),
        name_length=I5(12),
    )
    builder.ret(wrapped.cell.load())

    score_fn = ir.Function(module, ir.FunctionType(I32, []), name="wrapper_score")
    builder = ir.IRBuilder(score_fn.append_basic_block("entry"))
    wrapped = wrapper_handle.bind(builder, code_field_global)
    builder.ret(wrapped.load_header_score())

    return module


def main() -> None:
    refresh_generated_modules()
    module = build_module()
    compiled = compile_ir_module(module)

    raw_write = ctypes.CFUNCTYPE(ctypes.c_uint16)(compiled.function_address("raw_write"))
    wrapper_write = ctypes.CFUNCTYPE(ctypes.c_uint16)(compiled.function_address("wrapper_write"))
    wrapper_score = ctypes.CFUNCTYPE(ctypes.c_uint32)(compiled.function_address("wrapper_score"))

    print("== Question ==")
    print("Where should ergonomic customization live when a layout file is generated and must remain regenerable?")
    print()

    print("== Generated Core ==")
    print(inspect.getsource(_generated_layout).rstrip())
    print()

    print("== Hand-Authored Wrapper ==")
    print(inspect.getsource(layout_wrapper).rstrip())
    print()

    print("== Generated IR ==")
    print(compiled.llvm_ir)
    print()

    print("== Live Proof ==")
    print(f"raw_write()     -> 0x{raw_write():04x}")
    print(f"wrapper_write() -> 0x{wrapper_write():04x}")
    print(f"wrapper_score() -> {wrapper_score()}")
    print()

    print("== Takeaway ==")
    print("The generated file owns the schema-derived core and says DO NOT EDIT. The wrapper file is the intentional place to add naming, helpers, and ergonomic sugar.")


if __name__ == "__main__":
    main()
