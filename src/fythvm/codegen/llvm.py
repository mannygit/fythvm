"""Small llvmlite/JIT helpers shared by real package code."""

from __future__ import annotations

from dataclasses import dataclass

from llvmlite import binding, ir


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


@dataclass(frozen=True)
class CompiledIRModule:
    llvm_ir: str
    engine: binding.ExecutionEngine

    def function_address(self, name: str) -> int:
        return self.engine.get_function_address(name)


def compile_ir_module(module: ir.Module) -> CompiledIRModule:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    return CompiledIRModule(llvm_ir=llvm_ir, engine=engine)
