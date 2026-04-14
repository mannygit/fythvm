"""Demonstrate explicit host symbol exposure to llvmlite JIT code."""

from __future__ import annotations

import ctypes
from contextlib import contextmanager
from dataclasses import dataclass, field

from llvmlite import binding, ir


I64 = ir.IntType(64)
RAW_HOST_SYMBOL_NAME = "fythvm_host_scale_and_record_raw"
PYTHONIC_HOST_SYMBOL_NAME = "fythvm_host_scale_and_record_pythonic"
RAW_ENTRYPOINT_NAME = "exercise_host_symbol_raw"
PYTHONIC_ENTRYPOINT_NAME = "exercise_host_symbol_pythonic"


@dataclass(frozen=True)
class VariantRun:
    label: str
    symbol_name: str
    symbol_addr: int
    function_addr: int
    result: int
    call_log: list[int]
    llvm_ir: str


@dataclass
class HostSymbolHarness:
    """Own the callback lifetime and the symbol registration for the Pythonic path."""

    symbol_name: str
    scale: int = 10
    symbol_addr: int | None = None
    callback: object | None = None
    call_log: list[int] = field(default_factory=list)

    @contextmanager
    def registered(self):
        @ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)
        def host_scale_and_record(value: int) -> int:
            self.call_log.append(int(value))
            return value * self.scale

        self.callback = host_scale_and_record
        symbol_addr = ctypes.cast(host_scale_and_record, ctypes.c_void_p).value
        assert symbol_addr is not None
        self.symbol_addr = symbol_addr
        binding.add_symbol(self.symbol_name, symbol_addr)
        yield self

    def clear(self) -> None:
        self.callback = None


def ensure_llvm_initialized() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_module(symbol_name: str, entrypoint_name: str) -> ir.Module:
    module = ir.Module(name=f"host_symbol_exposure_{entrypoint_name}")
    module.triple = binding.get_default_triple()

    host_scale = ir.Function(
        module,
        ir.FunctionType(I64, [I64]),
        name=symbol_name,
    )

    func = ir.Function(
        module,
        ir.FunctionType(I64, [I64]),
        name=entrypoint_name,
    )
    block = func.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    first = builder.call(host_scale, [func.args[0]], name="first")
    second_arg = builder.add(func.args[0], I64(1), name="next_input")
    second = builder.call(host_scale, [second_arg], name="second")
    builder.ret(builder.add(first, second, name="combined_result"))

    return module


def compile_and_run(module: ir.Module, entrypoint_name: str, argument: int) -> tuple[str, int, int]:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    func_addr = engine.get_function_address(entrypoint_name)
    entrypoint = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)(func_addr)
    result = entrypoint(argument)
    return llvm_ir, func_addr, result


def run_raw_variant(argument: int) -> VariantRun:
    call_log: list[int] = []

    @ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_int64)
    def host_scale_and_record(value: int) -> int:
        call_log.append(int(value))
        return value * 10

    symbol_addr = ctypes.cast(host_scale_and_record, ctypes.c_void_p).value
    assert symbol_addr is not None
    binding.add_symbol(RAW_HOST_SYMBOL_NAME, symbol_addr)

    module = build_module(RAW_HOST_SYMBOL_NAME, RAW_ENTRYPOINT_NAME)
    llvm_ir, func_addr, result = compile_and_run(module, RAW_ENTRYPOINT_NAME, argument)

    return VariantRun(
        label="raw",
        symbol_name=RAW_HOST_SYMBOL_NAME,
        symbol_addr=symbol_addr,
        function_addr=func_addr,
        result=result,
        call_log=call_log,
        llvm_ir=llvm_ir,
    )


def run_pythonic_variant(argument: int) -> VariantRun:
    harness = HostSymbolHarness(PYTHONIC_HOST_SYMBOL_NAME)
    with harness.registered():
        assert harness.symbol_addr is not None
        module = build_module(PYTHONIC_HOST_SYMBOL_NAME, PYTHONIC_ENTRYPOINT_NAME)
        llvm_ir, func_addr, result = compile_and_run(
            module, PYTHONIC_ENTRYPOINT_NAME, argument
        )
    harness.clear()

    assert harness.symbol_addr is not None
    return VariantRun(
        label="pythonic",
        symbol_name=PYTHONIC_HOST_SYMBOL_NAME,
        symbol_addr=harness.symbol_addr,
        function_addr=func_addr,
        result=result,
        call_log=list(harness.call_log),
        llvm_ir=llvm_ir,
    )


def print_variant(run: VariantRun) -> None:
    print(f"== {run.label.title()} Variant ==")
    print("Generated IR:")
    print(run.llvm_ir.rstrip())
    print()
    print("Registered Host Symbol:")
    print(f"name: {run.symbol_name}")
    print(f"address: 0x{run.symbol_addr:x}")
    print()
    print("JIT Call:")
    print(f"entrypoint address: 0x{run.function_addr:x}")
    print(f"result: {run.result}")
    print()
    print("Host Call Log:")
    print(run.call_log)
    print()


def main() -> None:
    ensure_llvm_initialized()
    argument = 7
    raw = run_raw_variant(argument)
    pythonic = run_pythonic_variant(argument)

    print("== Question ==")
    print("What is the smallest reliable pattern for exposing a host-owned Python callback to JITed llvmlite code?")
    print()
    print_variant(raw)
    print_variant(pythonic)
    print("== Comparison ==")
    print(f"same result: {raw.result == pythonic.result}")
    print(f"same call log shape: {raw.call_log == pythonic.call_log}")
    print(f"same input: {argument}")
    print()
    print("== Takeaway ==")
    print("Keep the raw symbol-binding path explicit, then use a small context-managed harness when it makes the host-side lifetime rules clearer.")


if __name__ == "__main__":
    main()
