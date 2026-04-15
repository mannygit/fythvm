"""Demonstrate llvmlite struct types, layout, and host-visible proof."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass

from llvmlite import binding, ir


I8 = ir.IntType(8)
I16 = ir.IntType(16)
I32 = ir.IntType(32)
I64 = ir.IntType(64)


def configure_llvm() -> binding.TargetMachine:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()
    target = binding.Target.from_default_triple()
    return target.create_target_machine()


@dataclass(frozen=True)
class BoundStructField:
    view: "BoundStructView"
    index: int
    field_name: str

    def ptr(self, *, name: str | None = None) -> ir.Value:
        ptr_name = name or f"{self.field_name}_ptr"
        return self.view.field_ptr(self.index, name=ptr_name)

    def load(self, *, name: str | None = None) -> ir.Value:
        load_name = name or self.field_name
        return self.view.builder.load(self.ptr(), name=load_name)

    def store(self, value: ir.Value) -> None:
        self.view.builder.store(value, self.ptr())


class StructField:
    def __init__(self, index: int):
        self.index = index
        self.field_name = f"field_{index:02d}"

    def __set_name__(self, owner: type["BoundStructView"], name: str) -> None:
        self.field_name = name

    def __get__(self, instance: "BoundStructView" | None, owner: type["BoundStructView"]):
        if instance is None:
            return self
        return BoundStructField(instance, self.index, self.field_name)


class BoundStructView:
    """A struct access object bound to one active IR builder and one struct pointer."""

    def __init__(self, handle: "StructHandle", builder: ir.IRBuilder, struct_ptr: ir.Value):
        self.handle = handle
        self.builder = builder
        self.struct_ptr = struct_ptr

    def field_ptr(self, field_index: int, *, name: str) -> ir.Value:
        return self.builder.gep(
            self.struct_ptr,
            [I32(0), I32(field_index)],
            inbounds=True,
            name=name,
        )


class PairView(BoundStructView):
    first = StructField(0)
    second = StructField(1)


class MixedWidthView(BoundStructView):
    flag = StructField(0)
    byte = StructField(1)
    short = StructField(2)
    wide = StructField(3)


@dataclass(frozen=True)
class StructHandle:
    label: str
    ir_type: ir.Type
    view_type: type[BoundStructView] = BoundStructView

    @classmethod
    def literal(
        cls,
        label: str,
        *fields: ir.Type,
        packed: bool = False,
        view_type: type[BoundStructView] = BoundStructView,
    ) -> "StructHandle":
        return cls(label=label, ir_type=ir.LiteralStructType(list(fields), packed=packed), view_type=view_type)

    @classmethod
    def identified(
        cls,
        label: str,
        name: str,
        *fields: ir.Type,
        view_type: type[BoundStructView] = BoundStructView,
    ) -> "StructHandle":
        struct_type = ir.global_context.get_identified_type(name)
        struct_type.set_body(*fields)
        return cls(label=label, ir_type=struct_type, view_type=view_type)

    def constant(self, *values: ir.Value) -> ir.Constant:
        return ir.Constant(self.ir_type, list(values))

    def define_global(self, module: ir.Module, name: str, *values: ir.Value) -> ir.GlobalVariable:
        global_var = ir.GlobalVariable(module, self.ir_type, name=name)
        global_var.initializer = self.constant(*values)
        return global_var

    def bind(self, builder: ir.IRBuilder, struct_ptr: ir.Value) -> BoundStructView:
        return self.view_type(self, builder, struct_ptr)


@dataclass(frozen=True)
class LayoutSummary:
    label: str
    ir_text: str
    literal: bool
    packed: bool
    abi_size: int
    abi_alignment: int
    field_offsets: list[int]


def map_ir_type_to_ctypes(ir_type: ir.Type):
    if isinstance(ir_type, ir.IntType):
        if ir_type.width == 1:
            return ctypes.c_uint8
        if ir_type.width == 8:
            return ctypes.c_int8
        if ir_type.width == 16:
            return ctypes.c_int16
        if ir_type.width == 32:
            return ctypes.c_int32
        if ir_type.width == 64:
            return ctypes.c_int64
        raise ValueError(f"unsupported integer width: {ir_type.width}")

    if isinstance(ir_type, ir.ArrayType):
        return map_ir_type_to_ctypes(ir_type.element) * ir_type.count

    if isinstance(ir_type, (ir.LiteralStructType, ir.IdentifiedStructType)):
        return map_ir_struct_to_ctypes(ir_type)

    if isinstance(ir_type, ir.PointerType):
        return ctypes.POINTER(map_ir_type_to_ctypes(ir_type.pointee))

    if isinstance(ir_type, ir.FunctionType):
        restype = map_ir_type_to_ctypes(ir_type.return_type)
        argtypes = [map_ir_type_to_ctypes(arg) for arg in ir_type.args]
        return ctypes.CFUNCTYPE(restype, *argtypes)

    if isinstance(ir_type, ir.VoidType):
        return None

    raise ValueError(f"unsupported IR type: {ir_type}")


def map_ir_struct_to_ctypes(ir_struct_type: ir.Type) -> type[ctypes.Structure]:
    if not isinstance(ir_struct_type, (ir.LiteralStructType, ir.IdentifiedStructType)):
        raise TypeError(f"expected struct type, got {ir_struct_type!r}")

    fields = [
        (f"field_{index:02d}", map_ir_type_to_ctypes(field))
        for index, field in enumerate(ir_struct_type.elements)
    ]
    namespace: dict[str, object] = {"_fields_": fields}
    if getattr(ir_struct_type, "packed", False):
        namespace["_pack_"] = 1
        namespace["_layout_"] = "ms"

    name = getattr(ir_struct_type, "name", "") or "LiteralStruct"
    safe_name = name.replace("%", "").replace('"', "").replace(".", "_")
    return type(f"{safe_name}View", (ctypes.Structure,), namespace)


def ctypes_field_offsets(struct_cls: type[ctypes.Structure]) -> list[int]:
    return [getattr(struct_cls, field_name).offset for field_name, _ in struct_cls._fields_]


def build_module() -> tuple[ir.Module, dict[str, StructHandle], str]:
    target_machine = configure_llvm()
    module = ir.Module(name="llvmlite_struct_machinery")
    module.triple = binding.get_default_triple()
    module.data_layout = str(target_machine.target_data)

    literal_pair = StructHandle.literal("literal pair", I8, I64, view_type=PairView)
    identified_pair = StructHandle.identified("identified pair", "PairRecord", I8, I64, view_type=PairView)
    packed_pair = StructHandle.literal("packed pair", I8, I64, packed=True, view_type=PairView)
    mixed_width = StructHandle.identified(
        "mixed-width identified",
        "MixedWidthRecord",
        ir.IntType(1),
        I8,
        I16,
        I64,
        view_type=MixedWidthView,
    )

    literal_global = literal_pair.define_global(module, "literal_pair_data", I8(1), I64(11))
    identified_global = identified_pair.define_global(module, "identified_pair_data", I8(2), I64(40))
    packed_global = packed_pair.define_global(module, "packed_pair_data", I8(3), I64(99))
    mixed_global = mixed_width.define_global(module, "mixed_width_data", ir.IntType(1)(1), I8(7), I16(300), I64(1000))

    # Raw anchor: explicit literal-struct field access without helper wrappers.
    raw_fn = ir.Function(module, ir.FunctionType(I64, []), name="read_literal_second_raw")
    builder = ir.IRBuilder(raw_fn.append_basic_block("entry"))
    second_ptr = builder.gep(literal_global, [I32(0), I32(1)], inbounds=True, name="literal_second_ptr")
    builder.ret(builder.load(second_ptr, name="literal_second"))

    sum_fn = ir.Function(module, ir.FunctionType(I64, [identified_pair.ir_type.as_pointer()]), name="sum_identified_pair")
    pair_ptr = sum_fn.args[0]
    builder = ir.IRBuilder(sum_fn.append_basic_block("entry"))
    pair = identified_pair.bind(builder, pair_ptr)
    first = builder.zext(pair.first.load(), I64, name="first_i64")
    second = pair.second.load()
    builder.ret(builder.add(first, second, name="sum"))

    add_second_fn = ir.Function(module, ir.FunctionType(I64, [I64]), name="add_to_identified_second")
    delta = add_second_fn.args[0]
    builder = ir.IRBuilder(add_second_fn.append_basic_block("entry"))
    identified = identified_pair.bind(builder, identified_global)
    current = identified.second.load(name="current")
    updated = builder.add(current, delta, name="updated")
    identified.second.store(updated)
    builder.ret(updated)

    read_packed_fn = ir.Function(module, ir.FunctionType(I64, []), name="read_packed_second")
    builder = ir.IRBuilder(read_packed_fn.append_basic_block("entry"))
    packed = packed_pair.bind(builder, packed_global)
    builder.ret(packed.second.load(name="packed_second"))

    sum_mixed_fn = ir.Function(
        module,
        ir.FunctionType(I64, [mixed_width.ir_type.as_pointer()]),
        name="sum_mixed_width_fields",
    )
    mixed_ptr = sum_mixed_fn.args[0]
    builder = ir.IRBuilder(sum_mixed_fn.append_basic_block("entry"))
    mixed = mixed_width.bind(builder, mixed_ptr)
    flag = builder.zext(mixed.flag.load(), I64, name="flag_i64")
    byte = builder.sext(mixed.byte.load(), I64, name="byte_i64")
    short = builder.sext(mixed.short.load(), I64, name="short_i64")
    total = builder.add(flag, byte, name="flag_plus_byte")
    total = builder.add(total, short, name="plus_short")
    total = builder.add(total, mixed.wide.load(), name="plus_wide")
    builder.ret(total)

    toggle_mixed_flag_fn = ir.Function(module, ir.FunctionType(I64, []), name="toggle_mixed_flag")
    builder = ir.IRBuilder(toggle_mixed_flag_fn.append_basic_block("entry"))
    mixed = mixed_width.bind(builder, mixed_global)
    toggled = builder.xor(mixed.flag.load(name="current_flag"), ir.IntType(1)(1), name="toggled_flag")
    mixed.flag.store(toggled)
    builder.ret(builder.zext(toggled, I64, name="toggled_flag_i64"))

    return module, {
        "literal_pair": literal_pair,
        "identified_pair": identified_pair,
        "packed_pair": packed_pair,
        "mixed_width": mixed_width,
    }


def binding_struct_for(module_ref: binding.ModuleRef, struct_handle: StructHandle) -> binding.TypeRef:
    if isinstance(struct_handle.ir_type, ir.IdentifiedStructType):
        for struct_type in module_ref.struct_types:
            if struct_type.name == struct_handle.ir_type.name:
                return struct_type
        raise ValueError(f"identified struct {struct_handle.ir_type.name!r} not found")

    target_repr = "".join(str(struct_handle.ir_type).split())
    for struct_type in module_ref.struct_types:
        if struct_type.is_literal_struct and "".join(str(struct_type).split()) == target_repr:
            return struct_type
    raise ValueError(f"literal struct {target_repr!r} not found")


def summarize_layout(
    target_data: binding.TargetData, module_ref: binding.ModuleRef, struct_handle: StructHandle
) -> LayoutSummary:
    struct_type = binding_struct_for(module_ref, struct_handle)
    elements = list(struct_type.elements)
    return LayoutSummary(
        label=struct_handle.label,
        ir_text=str(struct_type),
        literal=struct_type.is_literal_struct,
        packed=struct_type.is_packed_struct,
        abi_size=target_data.get_abi_size(struct_type),
        abi_alignment=target_data.get_abi_alignment(struct_type),
        field_offsets=[target_data.get_element_offset(struct_type, index) for index in range(len(elements))],
    )


def describe_ctypes_struct(label: str, struct_cls: type[ctypes.Structure]) -> str:
    packed = getattr(struct_cls, "_pack_", None)
    return (
        f"{label}: class={struct_cls.__name__} "
        f"sizeof={ctypes.sizeof(struct_cls)} "
        f"offsets={ctypes_field_offsets(struct_cls)} "
        f"pack={packed!r}"
    )


def main() -> None:
    target_machine = configure_llvm()
    module, structs = build_module()
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    literal_pair_cls = map_ir_struct_to_ctypes(structs["literal_pair"].ir_type)
    identified_pair_cls = map_ir_struct_to_ctypes(structs["identified_pair"].ir_type)
    packed_pair_cls = map_ir_struct_to_ctypes(structs["packed_pair"].ir_type)
    mixed_width_cls = map_ir_struct_to_ctypes(structs["mixed_width"].ir_type)

    literal_addr = engine.get_global_value_address("literal_pair_data")
    identified_addr = engine.get_global_value_address("identified_pair_data")
    packed_addr = engine.get_global_value_address("packed_pair_data")
    mixed_addr = engine.get_global_value_address("mixed_width_data")

    literal_view = literal_pair_cls.from_address(literal_addr)
    identified_view = identified_pair_cls.from_address(identified_addr)
    packed_view = packed_pair_cls.from_address(packed_addr)
    mixed_view = mixed_width_cls.from_address(mixed_addr)

    read_literal_second_raw = ctypes.CFUNCTYPE(ctypes.c_int64)(
        engine.get_function_address("read_literal_second_raw")
    )
    sum_identified_pair = ctypes.CFUNCTYPE(
        ctypes.c_int64, ctypes.POINTER(identified_pair_cls)
    )(engine.get_function_address("sum_identified_pair"))
    add_to_identified_second = ctypes.CFUNCTYPE(
        ctypes.c_int64, ctypes.c_int64
    )(engine.get_function_address("add_to_identified_second"))
    read_packed_second = ctypes.CFUNCTYPE(ctypes.c_int64)(
        engine.get_function_address("read_packed_second")
    )
    sum_mixed_width_fields = ctypes.CFUNCTYPE(
        ctypes.c_int64, ctypes.POINTER(mixed_width_cls)
    )(engine.get_function_address("sum_mixed_width_fields"))
    toggle_mixed_flag = ctypes.CFUNCTYPE(ctypes.c_int64)(
        engine.get_function_address("toggle_mixed_flag")
    )

    layout_summaries = [
        summarize_layout(target_machine.target_data, parsed, structs["literal_pair"]),
        summarize_layout(target_machine.target_data, parsed, structs["identified_pair"]),
        summarize_layout(target_machine.target_data, parsed, structs["packed_pair"]),
        summarize_layout(target_machine.target_data, parsed, structs["mixed_width"]),
    ]

    try:
        ir.Context().get_identified_type("PackedPairRejected").set_body(I8, I64, packed=True)  # type: ignore[call-arg]
        packed_identified_error = "unexpectedly accepted packed=True on identified struct"
    except TypeError as exc:
        packed_identified_error = str(exc)

    print("== Question ==")
    print("How do llvmlite literal, identified, and packed structs differ in IR construction, field access, and host-visible layout?")
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Layout Summary (LLVM Target Data) ==")
    for summary in layout_summaries:
        print(
            f"{summary.label}: ir={summary.ir_text} literal={summary.literal} "
            f"packed={summary.packed} abi_size={summary.abi_size} "
            f"abi_align={summary.abi_alignment} field_offsets={summary.field_offsets}"
        )
    print()
    print("== ctypes Bridge Summary ==")
    print(describe_ctypes_struct("literal pair", literal_pair_cls))
    print(describe_ctypes_struct("identified pair", identified_pair_cls))
    print(describe_ctypes_struct("packed pair", packed_pair_cls))
    print(describe_ctypes_struct("mixed-width identified", mixed_width_cls))
    print()
    print("== Live Proof ==")
    print(f"read_literal_second_raw() -> {read_literal_second_raw()}")
    print(f"literal_pair_data ctypes view = ({literal_view.field_00}, {literal_view.field_01})")
    print(f"sum_identified_pair(&identified_pair_data) -> {sum_identified_pair(ctypes.byref(identified_view))}")
    print(f"identified_pair_data before host mutation = ({identified_view.field_00}, {identified_view.field_01})")
    identified_view.field_00 = 7
    print(f"identified_pair_data after host mutation = ({identified_view.field_00}, {identified_view.field_01})")
    print(f"sum_identified_pair(&identified_pair_data) after host mutation -> {sum_identified_pair(ctypes.byref(identified_view))}")
    print(f"add_to_identified_second(5) -> {add_to_identified_second(5)}")
    print(f"identified_pair_data after JIT write = ({identified_view.field_00}, {identified_view.field_01})")
    print(f"read_packed_second() -> {read_packed_second()}")
    print(f"packed_pair_data ctypes view = ({packed_view.field_00}, {packed_view.field_01})")
    print(
        "mixed_width_data ctypes view = "
        f"({mixed_view.field_00}, {mixed_view.field_01}, {mixed_view.field_02}, {mixed_view.field_03})"
    )
    print(f"sum_mixed_width_fields(&mixed_width_data) -> {sum_mixed_width_fields(ctypes.byref(mixed_view))}")
    mixed_view.field_00 = 0
    mixed_view.field_01 = -4
    mixed_view.field_02 = 512
    print(
        "mixed_width_data after host mutation = "
        f"({mixed_view.field_00}, {mixed_view.field_01}, {mixed_view.field_02}, {mixed_view.field_03})"
    )
    print(
        "sum_mixed_width_fields(&mixed_width_data) after host mutation -> "
        f"{sum_mixed_width_fields(ctypes.byref(mixed_view))}"
    )
    print(f"toggle_mixed_flag() -> {toggle_mixed_flag()}")
    print(
        "mixed_width_data after JIT flag toggle = "
        f"({mixed_view.field_00}, {mixed_view.field_01}, {mixed_view.field_02}, {mixed_view.field_03})"
    )
    print()
    print("== Non-Obvious Constraint ==")
    print("identified struct packed=True attempt:")
    print(packed_identified_error)
    print()
    print("== Takeaway ==")
    print(
        "Literal versus identified structs mostly changes naming and body-definition style; "
        "packed versus unpacked changes the ABI layout, mixed-width fields make the offsets "
        "and padding visible, and even an i1 field still has to be bridged through the host "
        "layout carefully."
    )


if __name__ == "__main__":
    main()
