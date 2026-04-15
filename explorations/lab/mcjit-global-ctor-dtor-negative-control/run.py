"""Quarantined negative control for llvmlite MCJIT global ctor/dtor behavior."""

from __future__ import annotations

import argparse
import ctypes
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from llvmlite import binding, ir


I32 = ir.IntType(32)
I64 = ir.IntType(64)
I8 = ir.IntType(8)
VOID = ir.VoidType()

UNSAFE_CHILD_FLAG = "--unsafe-child"


@dataclass
class CounterSnapshot:
    ctor_hits: int
    dtor_hits: int


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def build_negative_control_module() -> ir.Module:
    """Build a module that intentionally uses ctor/dtor globals."""
    module = ir.Module(name="mcjit_global_ctor_dtor_negative_control")
    module.triple = binding.get_default_triple()

    ctor_hits = ir.GlobalVariable(module, I64, name="ctor_hits")
    ctor_hits.initializer = ir.Constant(I64, 0)

    dtor_hits = ir.GlobalVariable(module, I64, name="dtor_hits")
    dtor_hits.initializer = ir.Constant(I64, 0)

    hook_ty = ir.FunctionType(VOID, [])

    ctor_fn = ir.Function(module, hook_ty, name="record_ctor")
    block = ctor_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current = builder.load(ctor_hits, name="ctor_value")
    builder.store(builder.add(current, ir.Constant(I64, 1), name="ctor_next"), ctor_hits)
    builder.ret_void()

    dtor_fn = ir.Function(module, hook_ty, name="record_dtor")
    block = dtor_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    current = builder.load(dtor_hits, name="dtor_value")
    builder.store(builder.add(current, ir.Constant(I64, 1), name="dtor_next"), dtor_hits)
    builder.ret_void()

    read_ctor_fn = ir.Function(module, ir.FunctionType(I64, []), name="read_ctor_hits")
    block = read_ctor_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.ret(builder.load(ctor_hits, name="ctor_hits_value"))

    read_dtor_fn = ir.Function(module, ir.FunctionType(I64, []), name="read_dtor_hits")
    block = read_dtor_fn.append_basic_block(name="entry")
    builder = ir.IRBuilder(block)
    builder.ret(builder.load(dtor_hits, name="dtor_hits_value"))

    ctor_record_ty = ir.LiteralStructType([I32, hook_ty.as_pointer(), I8.as_pointer()])
    ctor_array_ty = ir.ArrayType(ctor_record_ty, 1)
    ctor_record = ir.Constant(
        ctor_record_ty,
        [
            ir.Constant(I32, 65535),
            ctor_fn,
            ir.Constant(I8.as_pointer(), None),
        ],
    )
    global_ctors = ir.GlobalVariable(module, ctor_array_ty, name="llvm.global_ctors")
    global_ctors.linkage = "appending"
    global_ctors.initializer = ir.Constant(ctor_array_ty, [ctor_record])

    dtor_record_ty = ir.LiteralStructType([I32, hook_ty.as_pointer(), I8.as_pointer()])
    dtor_array_ty = ir.ArrayType(dtor_record_ty, 1)
    dtor_record = ir.Constant(
        dtor_record_ty,
        [
            ir.Constant(I32, 65535),
            dtor_fn,
            ir.Constant(I8.as_pointer(), None),
        ],
    )
    global_dtors = ir.GlobalVariable(module, dtor_array_ty, name="llvm.global_dtors")
    global_dtors.linkage = "appending"
    global_dtors.initializer = ir.Constant(dtor_array_ty, [dtor_record])

    return module


def compile_module(module: ir.Module) -> tuple[str, binding.ExecutionEngine]:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()
    return llvm_ir, engine


def read_counter(engine: binding.ExecutionEngine, symbol_name: str) -> int:
    address = engine.get_function_address(symbol_name)
    reader = ctypes.CFUNCTYPE(ctypes.c_int64)(address)
    return int(reader())


def snapshot_counters(engine: binding.ExecutionEngine) -> CounterSnapshot:
    return CounterSnapshot(
        ctor_hits=read_counter(engine, "read_ctor_hits"),
        dtor_hits=read_counter(engine, "read_dtor_hits"),
    )


def run_quarantined_attempt(script_path: Path) -> tuple[int, str, str]:
    env = dict(os.environ)
    env[UNSAFE_CHILD_FLAG] = "1"
    command = [sys.executable, str(script_path), UNSAFE_CHILD_FLAG]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def print_block(title: str, body: str) -> None:
    print(f"== {title} ==")
    print(body.rstrip())
    print()


def parent_main(attempt_unsafe_path: bool) -> None:
    configure_llvm()
    module = build_negative_control_module()
    llvm_ir, engine = compile_module(module)

    host_triple = binding.get_default_triple()
    host_system = platform.system()
    platform_machine = platform.machine() or "unknown"
    counters = snapshot_counters(engine)

    print_block("Question", "What does the unsupported MCJIT ctor/dtor path look like, and how do we quarantine it safely?")
    print_block(
        "Host Context",
        "\n".join(
            [
                f"LLVM target triple: {host_triple}",
                f"Host system: {host_system}",
                f"Host machine: {platform_machine}",
                "Execution mode: safe default run; unsupported runtime attempt is opt-in and isolated in a child process.",
            ]
        ),
    )
    print_block("Generated IR", llvm_ir.rstrip())
    print_block(
        "Safe Observation",
        "\n".join(
            [
                "contains llvm.global_ctors: True",
                "contains llvm.global_dtors: True",
                f"initial read_ctor_hits() -> {counters.ctor_hits}",
                f"initial read_dtor_hits() -> {counters.dtor_hits}",
                "ctor/dtor execution was not attempted in the parent process.",
            ]
        ),
    )

    if attempt_unsafe_path:
        if host_system == "Darwin":
            print_block(
                "Quarantined Attempt",
                "\n".join(
                    [
                        "status: skipped on macOS",
                        "reason: the unsupported MCJIT ctor/dtor runtime path is already known to segfault on Mach-O and adds only noise here.",
                        "safe evidence retained: the parent process still shows the emitted llvm.global_ctors / llvm.global_dtors shape and the untouched counters above.",
                    ]
                ),
            )
            print_block(
                "Takeaway",
                "Keep the ctor/dtor path as a negative control: document the IR shape, keep the default run safe, and suppress the known-noisy macOS crash path.",
            )
            return

        script_path = Path(__file__).resolve()
        returncode, stdout, stderr = run_quarantined_attempt(script_path)
        if returncode == 0:
            status = "child completed without a crash in this environment, but the path remains unsupported"
        elif returncode < 0:
            status = f"child terminated by signal {-returncode}; this is the expected-failure shape for the quarantined negative control"
        else:
            status = f"child exited nonzero with code {returncode}; this is the expected-failure shape for the quarantined negative control"

        print_block(
            "Quarantined Attempt",
            "\n".join(
                [
                    f"command: {sys.executable} {script_path.name} {UNSAFE_CHILD_FLAG}",
                    f"return code: {returncode}",
                    f"status: {status}",
                    "stdout:",
                    stdout.rstrip() or "  <empty>",
                    "stderr:",
                    stderr.rstrip() or "  <empty>",
                ]
            ),
        )
    else:
        print_block(
            "Quarantined Attempt",
            "Skip by default. Re-run with --attempt-unsafe-path to isolate the unsupported runtime path in a child process.",
        )

    print_block(
        "Takeaway",
        "Keep the ctor/dtor path as a negative control: document the IR shape, keep the default run safe, and quarantine any execution attempt.",
    )


def child_main() -> None:
    configure_llvm()
    module = build_negative_control_module()
    llvm_ir, engine = compile_module(module)

    print("== Unsafe Child ==")
    print("This child process is the only place the unsupported runtime path is allowed to execute.")
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Pre-Execution Counters ==")
    print(snapshot_counters(engine))
    print()
    print("== Runtime Attempt ==")
    print("calling run_static_constructors()")
    engine.run_static_constructors()
    print("calling run_static_destructors()")
    engine.run_static_destructors()
    print()
    print("== Post-Execution Counters ==")
    print(snapshot_counters(engine))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Quarantined negative control for llvmlite MCJIT ctor/dtor behavior.",
    )
    parser.add_argument(
        "--attempt-unsafe-path",
        action="store_true",
        help="Run the unsupported ctor/dtor path in an isolated child process.",
    )
    parser.add_argument(
        UNSAFE_CHILD_FLAG,
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.unsafe_child:
        child_main()
        return
    parent_main(args.attempt_unsafe_path)


if __name__ == "__main__":
    main()
