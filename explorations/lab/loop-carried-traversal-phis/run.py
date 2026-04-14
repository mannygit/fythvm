"""Show loop-carried cursor and count phi nodes while traversing a linked list."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


I64 = ir.IntType(64)
I32 = ir.IntType(32)
ZERO = ir.Constant(I32, 0)
ONE = ir.Constant(I32, 1)

NODE_TYPE = ir.global_context.get_identified_type("LoopCarriedTraversalNode")
NODE_PTR = NODE_TYPE.as_pointer()
NODE_TYPE.set_body(I64, NODE_PTR)


@dataclass(frozen=True)
class CompiledModule:
    llvm_ir: str
    engine: binding.ExecutionEngine
    count_nodes_addr: int
    index_of_value_addr: int


class Node(ctypes.Structure):
    pass


NodePtr = ctypes.POINTER(Node)
Node._fields_ = [("value", ctypes.c_int64), ("next", NodePtr)]


def configure_llvm() -> None:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()


def make_target_machine() -> binding.TargetMachine:
    target = binding.Target.from_default_triple()
    return target.create_target_machine()


def make_module(name: str) -> ir.Module:
    module = ir.Module(name=name)
    module.triple = binding.get_default_triple()
    module.data_layout = str(make_target_machine().target_data)
    return module


def build_module() -> ir.Module:
    module = make_module("loop_carried_traversal_phis")

    count_nodes = ir.Function(module, ir.FunctionType(I64, [NODE_PTR]), name="count_nodes")
    entry = count_nodes.append_basic_block(name="entry")
    loop_header = count_nodes.append_basic_block(name="loop_header")
    body = count_nodes.append_basic_block(name="body")
    exit_block = count_nodes.append_basic_block(name="exit")

    builder = ir.IRBuilder(entry)
    builder.branch(loop_header)

    builder.position_at_end(loop_header)
    cursor = builder.phi(NODE_PTR, name="cursor")
    count = builder.phi(I64, name="count")
    live = builder.icmp_unsigned("!=", cursor, ir.Constant(NODE_PTR, None), name="cursor_live")
    builder.cbranch(live, body, exit_block)
    cursor.add_incoming(count_nodes.args[0], entry)
    count.add_incoming(ir.Constant(I64, 0), entry)

    builder.position_at_end(body)
    next_value_ptr = builder.gep(cursor, [ZERO, ZERO], name="value_ptr")
    _ = builder.load(next_value_ptr, name="value")
    next_ptr_ptr = builder.gep(cursor, [ZERO, ONE], name="next_ptr")
    next_cursor = builder.load(next_ptr_ptr, name="next_cursor")
    next_count = builder.add(count, ir.Constant(I64, 1), name="count_plus_one")
    builder.branch(loop_header)
    cursor.add_incoming(next_cursor, body)
    count.add_incoming(next_count, body)

    builder.position_at_end(exit_block)
    builder.ret(count)

    index_of_value = ir.Function(
        module, ir.FunctionType(I64, [NODE_PTR, I64]), name="index_of_value"
    )
    entry = index_of_value.append_basic_block(name="entry")
    loop_header = index_of_value.append_basic_block(name="loop_header")
    body = index_of_value.append_basic_block(name="body")
    found_block = index_of_value.append_basic_block(name="found")
    advance_block = index_of_value.append_basic_block(name="advance")
    not_found_block = index_of_value.append_basic_block(name="not_found")
    exit_block = index_of_value.append_basic_block(name="exit")

    builder = ir.IRBuilder(entry)
    builder.branch(loop_header)

    builder.position_at_end(loop_header)
    cursor = builder.phi(NODE_PTR, name="cursor")
    count = builder.phi(I64, name="count")
    live = builder.icmp_unsigned("!=", cursor, ir.Constant(NODE_PTR, None), name="cursor_live")
    builder.cbranch(live, body, not_found_block)
    cursor.add_incoming(index_of_value.args[0], entry)
    count.add_incoming(ir.Constant(I64, 0), entry)

    builder.position_at_end(body)
    value_ptr = builder.gep(cursor, [ZERO, ZERO], name="value_ptr")
    value = builder.load(value_ptr, name="value")
    matches = builder.icmp_signed("==", value, index_of_value.args[1], name="matches")
    builder.cbranch(matches, found_block, advance_block)

    builder.position_at_end(found_block)
    builder.branch(exit_block)

    builder.position_at_end(advance_block)
    next_ptr_ptr = builder.gep(cursor, [ZERO, ONE], name="next_ptr")
    next_cursor = builder.load(next_ptr_ptr, name="next_cursor")
    next_count = builder.add(count, ir.Constant(I64, 1), name="count_plus_one")
    builder.branch(loop_header)
    cursor.add_incoming(next_cursor, advance_block)
    count.add_incoming(next_count, advance_block)

    builder.position_at_end(not_found_block)
    builder.branch(exit_block)

    builder.position_at_end(exit_block)
    result = builder.phi(I64, name="result")
    result.add_incoming(count, found_block)
    result.add_incoming(ir.Constant(I64, -1), not_found_block)
    builder.ret(result)

    return module


def build_invalid_module() -> ir.Module:
    module = make_module("loop_carried_traversal_phis_invalid")
    count_nodes = ir.Function(module, ir.FunctionType(I64, [NODE_PTR]), name="broken_count_nodes")
    entry = count_nodes.append_basic_block(name="entry")
    loop_header = count_nodes.append_basic_block(name="loop_header")
    body = count_nodes.append_basic_block(name="body")
    exit_block = count_nodes.append_basic_block(name="exit")

    builder = ir.IRBuilder(entry)
    builder.branch(loop_header)

    builder.position_at_end(loop_header)
    cursor = builder.phi(NODE_PTR, name="cursor")
    count = builder.phi(I64, name="count")
    live = builder.icmp_unsigned("!=", cursor, ir.Constant(NODE_PTR, None), name="cursor_live")
    builder.cbranch(live, body, exit_block)
    cursor.add_incoming(count_nodes.args[0], entry)
    count.add_incoming(ir.Constant(I64, 0), entry)

    builder.position_at_end(body)
    next_ptr_ptr = builder.gep(cursor, [ZERO, ONE], name="next_ptr")
    next_cursor = builder.load(next_ptr_ptr, name="next_cursor")
    next_count = builder.add(count, ir.Constant(I64, 1), name="count_plus_one")
    builder.branch(loop_header)
    cursor.add_incoming(next_cursor, body)
    _ = next_count

    builder.position_at_end(exit_block)
    builder.ret(count)

    return module


def compile_module(module: ir.Module) -> CompiledModule:
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    target_machine = make_target_machine()
    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    return CompiledModule(
        llvm_ir=llvm_ir,
        engine=engine,
        count_nodes_addr=engine.get_function_address("count_nodes"),
        index_of_value_addr=engine.get_function_address("index_of_value"),
    )


def call_i64_ptr(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p)(address)


def call_i64_ptr_i64(address: int) -> ctypes.CFUNCTYPE:
    return ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_void_p, ctypes.c_int64)(address)


def build_runtime_list(values: list[int]) -> tuple[list[Node], ctypes.c_void_p]:
    nodes = [Node(value=value, next=NodePtr()) for value in values]
    for current, nxt in zip(nodes, nodes[1:]):
        current.next = ctypes.pointer(nxt)
    nodes[-1].next = NodePtr()
    return nodes, ctypes.c_void_p(ctypes.addressof(nodes[0]))


def describe_list(values: list[int]) -> str:
    return " -> ".join(str(value) for value in values) + " -> null"


def show_invalid_module_failure() -> str:
    invalid_module = build_invalid_module()
    try:
        parsed = binding.parse_assembly(str(invalid_module))
        parsed.verify()
    except Exception as exc:  # noqa: BLE001
        return str(exc).strip()
    return "unexpected success"


def phi_lines(raw_ir: str) -> list[str]:
    return [line.rstrip() for line in raw_ir.splitlines() if " phi " in line or line.lstrip().startswith("%") and " phi " in line]


def main() -> None:
    configure_llvm()
    compiled = compile_module(build_module())
    count_nodes = call_i64_ptr(compiled.count_nodes_addr)
    index_of_value = call_i64_ptr_i64(compiled.index_of_value_addr)

    values = [4, 7, 11]
    nodes, head = build_runtime_list(values)

    print("== Question ==")
    print("How do you carry a traversal cursor and a derived count through a linked list loop?")
    print()

    print("== Host Triple ==")
    print(binding.get_default_triple())
    print()

    print("== Runtime List ==")
    print(describe_list(values))
    print(f"head address: 0x{head.value:x}")
    print(f"nodes kept alive: {len(nodes)}")
    print()

    print("== Generated IR ==")
    print(compiled.llvm_ir.rstrip())
    print()

    print("== Phi Summary ==")
    for line in phi_lines(compiled.llvm_ir):
        print(line)
    print()

    print("== Runtime Results ==")
    print(f"count_nodes(head) -> {count_nodes(head)}")
    print(f"index_of_value(head, 4) -> {index_of_value(head, 4)}")
    print(f"index_of_value(head, 7) -> {index_of_value(head, 7)}")
    print(f"index_of_value(head, 99) -> {index_of_value(head, 99)}")
    print()

    print("== Invalid Attempt ==")
    print("broken_count_nodes() with a missing backedge incoming value:")
    print(show_invalid_module_failure())
    print()

    print("== What To Notice ==")
    print("The cursor phi carries the current node pointer; the count phi carries derived loop state.")
    print("The early-exit result is separate: a found index returns the count, and the not-found path returns -1.")
    print("If the count phi does not receive the backedge value from the actual loop body, the verifier rejects the module.")


if __name__ == "__main__":
    main()
