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
    original_llvm_ir: str
    assembly: str
    engine: binding.ExecutionEngine
    speed_level: int | None = None
    size_level: int = 0

    def function_address(self, name: str) -> int:
        return self.engine.get_function_address(name)


def compile_ir_module(
    module: ir.Module,
    *,
    speed_level: int | None = None,
    size_level: int = 0,
) -> CompiledIRModule:
    original_llvm_ir = str(module)
    parsed = binding.parse_assembly(original_llvm_ir)
    parsed.verify()
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    if speed_level is not None:
        tuning = binding.PipelineTuningOptions(
            speed_level=speed_level,
            size_level=size_level,
        )
        pass_builder = binding.create_pass_builder(target_machine, tuning)
        module_pass_manager = pass_builder.getModulePassManager()
        module_pass_manager.run(parsed, pass_builder)
        parsed.verify()
    llvm_ir = str(parsed)
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    assembly = target_machine.emit_assembly(parsed)
    return CompiledIRModule(
        llvm_ir=llvm_ir,
        original_llvm_ir=original_llvm_ir,
        assembly=assembly,
        engine=engine,
        speed_level=speed_level,
        size_level=size_level,
    )
