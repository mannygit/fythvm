"""Reify ctypes.Structure declarations into llvmlite struct handles and views."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass

from llvmlite import binding, ir


BYTEORDER = sys.byteorder
I8 = ir.IntType(8)
I32 = ir.IntType(32)
I64 = ir.IntType(64)


SIGNED_CTYPES: tuple[type[ctypes._SimpleCData], ...] = (  # type: ignore[attr-defined]
    ctypes.c_byte,
    ctypes.c_short,
    ctypes.c_int,
    ctypes.c_longlong,
)

CTYPES_TO_WIDTH: dict[type[ctypes._SimpleCData], int] = {  # type: ignore[attr-defined]
    ctypes.c_byte: 8,
    ctypes.c_ubyte: 8,
    ctypes.c_short: 16,
    ctypes.c_ushort: 16,
    ctypes.c_int: 32,
    ctypes.c_uint: 32,
    ctypes.c_longlong: 64,
    ctypes.c_ulonglong: 64,
}


def configure_llvm() -> binding.TargetMachine:
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()
    target = binding.Target.from_default_triple()
    return target.create_target_machine()


def int_ir_type(width: int) -> ir.IntType:
    return ir.IntType(width)


def ctypes_storage_ir_type(ctype: type[ctypes._SimpleCData]) -> ir.IntType:  # type: ignore[attr-defined]
    try:
        return int_ir_type(CTYPES_TO_WIDTH[ctype])
    except KeyError as exc:
        raise ValueError(f"unsupported ctypes field type: {ctype!r}") from exc


def normalize_int_width(builder: ir.IRBuilder, value: ir.Value, target_type: ir.IntType, *, name: str) -> ir.Value:
    if value.type == target_type:
        return value
    if not isinstance(value.type, ir.IntType):
        raise TypeError(f"expected integer IR value, got {value.type!r}")
    if value.type.width > target_type.width:
        return builder.trunc(value, target_type, name=name)
    return builder.zext(value, target_type, name=name)


@dataclass(frozen=True)
class PhysicalFieldSpec:
    name: str
    ir_type: ir.Type
    byte_offset: int
    byte_size: int
    kind: str


@dataclass(frozen=True)
class LogicalFieldSpec:
    name: str
    ctype: type[ctypes._SimpleCData]  # type: ignore[attr-defined]
    logical_ir_type: ir.IntType
    storage_ir_type: ir.IntType
    storage_index: int
    storage_name: str
    byte_offset: int
    signed: bool
    bit_offset: int | None = None
    bit_size: int | None = None

    @property
    def is_bitfield(self) -> bool:
        return self.bit_size is not None


@dataclass(frozen=True)
class LayoutSummary:
    label: str
    ir_text: str
    abi_size: int
    abi_alignment: int
    field_offsets: list[int]


@dataclass(frozen=True)
class BoundLogicalField:
    view: "BoundStructView"
    spec: LogicalFieldSpec

    def ptr(self, *, name: str | None = None) -> ir.Value:
        ptr_name = name or f"{self.spec.storage_name}_ptr"
        return self.view.field_ptr(self.spec.storage_index, name=ptr_name)

    def load(self, *, name: str | None = None) -> ir.Value:
        builder = self.view.builder
        if not self.spec.is_bitfield:
            return builder.load(self.ptr(name=name), name=name or self.spec.name)

        storage = builder.load(self.ptr(), name=f"{self.spec.name}_storage")
        if self.spec.bit_offset:
            storage = builder.lshr(
                storage,
                self.spec.storage_ir_type(self.spec.bit_offset),
                name=f"{self.spec.name}_shifted",
            )
        mask = (1 << self.spec.bit_size) - 1
        masked = builder.and_(storage, self.spec.storage_ir_type(mask), name=f"{self.spec.name}_masked")
        return builder.trunc(masked, self.spec.logical_ir_type, name=name or self.spec.name)

    def store(self, value: ir.Value) -> None:
        builder = self.view.builder
        if not self.spec.is_bitfield:
            builder.store(
                normalize_int_width(builder, value, self.spec.storage_ir_type, name=f"{self.spec.name}_value"),
                self.ptr(),
            )
            return

        ptr = self.ptr()
        current = builder.load(ptr, name=f"{self.spec.name}_storage")
        logical = normalize_int_width(builder, value, self.spec.logical_ir_type, name=f"{self.spec.name}_logical")
        widened = normalize_int_width(builder, logical, self.spec.storage_ir_type, name=f"{self.spec.name}_bits")
        if self.spec.bit_offset:
            shifted = builder.shl(
                widened,
                self.spec.storage_ir_type(self.spec.bit_offset),
                name=f"{self.spec.name}_shifted",
            )
        else:
            shifted = widened
        storage_mask = (1 << self.spec.storage_ir_type.width) - 1
        bit_mask = ((1 << self.spec.bit_size) - 1) << self.spec.bit_offset
        cleared = builder.and_(
            current,
            self.spec.storage_ir_type(storage_mask ^ bit_mask),
            name=f"{self.spec.name}_cleared",
        )
        builder.store(builder.or_(cleared, shifted, name=f"{self.spec.name}_updated"), ptr)


class LogicalFieldDescriptor:
    def __init__(self, spec: LogicalFieldSpec):
        self.spec = spec

    def __get__(self, instance: "BoundStructView" | None, owner: type["BoundStructView"]):
        if instance is None:
            return self
        return BoundLogicalField(instance, self.spec)


class BoundStructView:
    """A reified struct view bound to one active IR builder and one struct pointer."""

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


@dataclass(frozen=True)
class StructHandle:
    label: str
    ctypes_cls: type[ctypes.Structure]
    ir_type: ir.LiteralStructType
    view_type: type[BoundStructView]
    view_source: str
    logical_fields: tuple[LogicalFieldSpec, ...]
    physical_fields: tuple[PhysicalFieldSpec, ...]

    @classmethod
    def from_ctypes(cls, label: str, ctypes_cls: type[ctypes.Structure]) -> "StructHandle":
        if not issubclass(ctypes_cls, ctypes.Structure):
            raise TypeError(f"expected ctypes.Structure subclass, got {ctypes_cls!r}")

        physical_storage: list[tuple[str, PhysicalFieldSpec]] = []
        logical_fields: list[tuple[str, LogicalFieldSpec]] = []

        for field_name, ctype, *rest in ctypes_cls._fields_:
            if ctype not in CTYPES_TO_WIDTH:
                raise ValueError(f"unsupported ctypes field type: {ctype!r}")

            field_desc = getattr(ctypes_cls, field_name)
            storage_ir = ctypes_storage_ir_type(ctype)
            byte_offset = field_desc.offset
            signed = ctype in SIGNED_CTYPES

            if field_desc.is_bitfield:
                storage_key = f"storage:{byte_offset}:{ctypes.sizeof(ctype)}"
                if storage_key not in {key for key, _ in physical_storage}:
                    physical_storage.append(
                        (
                            storage_key,
                            PhysicalFieldSpec(
                                name=f"_{field_name}_storage",
                                ir_type=storage_ir,
                                byte_offset=byte_offset,
                                byte_size=ctypes.sizeof(ctype),
                                kind="storage",
                            ),
                        )
                    )
                logical_fields.append(
                    (
                        field_name,
                        LogicalFieldSpec(
                            name=field_name,
                            ctype=ctype,
                            logical_ir_type=int_ir_type(field_desc.bit_size),
                            storage_ir_type=storage_ir,
                            storage_index=-1,
                            storage_name="",
                            byte_offset=byte_offset,
                            signed=signed,
                            bit_offset=field_desc.bit_offset,
                            bit_size=field_desc.bit_size,
                        ),
                    )
                )
                continue

            storage_key = f"field:{field_name}"
            physical_storage.append(
                (
                    storage_key,
                    PhysicalFieldSpec(
                        name=field_name,
                        ir_type=storage_ir,
                        byte_offset=byte_offset,
                        byte_size=ctypes.sizeof(ctype),
                        kind="storage",
                    ),
                )
            )
            logical_fields.append(
                (
                    field_name,
                    LogicalFieldSpec(
                        name=field_name,
                        ctype=ctype,
                        logical_ir_type=storage_ir,
                        storage_ir_type=storage_ir,
                        storage_index=-1,
                        storage_name="",
                        byte_offset=byte_offset,
                        signed=signed,
                    ),
                )
            )

        storage_by_key = dict(physical_storage)
        ordered_storage = sorted(storage_by_key.items(), key=lambda item: (item[1].byte_offset, item[1].name))

        physical_fields: list[PhysicalFieldSpec] = []
        storage_index_by_key: dict[str, int] = {}
        current_offset = 0
        pad_index = 0
        for storage_key, storage_spec in ordered_storage:
            if storage_spec.byte_offset > current_offset:
                pad_size = storage_spec.byte_offset - current_offset
                physical_fields.append(
                    PhysicalFieldSpec(
                        name=f"_pad_{pad_index:02d}",
                        ir_type=ir.ArrayType(I8, pad_size),
                        byte_offset=current_offset,
                        byte_size=pad_size,
                        kind="padding",
                    )
                )
                pad_index += 1
                current_offset += pad_size

            storage_index_by_key[storage_key] = len(physical_fields)
            physical_fields.append(storage_spec)
            current_offset = storage_spec.byte_offset + storage_spec.byte_size

        total_size = ctypes.sizeof(ctypes_cls)
        if total_size > current_offset:
            pad_size = total_size - current_offset
            physical_fields.append(
                PhysicalFieldSpec(
                    name=f"_pad_{pad_index:02d}",
                    ir_type=ir.ArrayType(I8, pad_size),
                    byte_offset=current_offset,
                    byte_size=pad_size,
                    kind="padding",
                )
            )

        resolved_logical_fields: list[LogicalFieldSpec] = []
        for field_name, logical in logical_fields:
            if logical.is_bitfield:
                storage_key = f"storage:{logical.byte_offset}:{logical.storage_ir_type.width // 8}"
            else:
                storage_key = f"field:{field_name}"
            storage_spec = storage_by_key[storage_key]
            resolved_logical_fields.append(
                LogicalFieldSpec(
                    name=logical.name,
                    ctype=logical.ctype,
                    logical_ir_type=logical.logical_ir_type,
                    storage_ir_type=logical.storage_ir_type,
                    storage_index=storage_index_by_key[storage_key],
                    storage_name=storage_spec.name,
                    byte_offset=logical.byte_offset,
                    signed=logical.signed,
                    bit_offset=logical.bit_offset,
                    bit_size=logical.bit_size,
                )
            )

        view_type, view_source = build_generated_view_type(ctypes_cls, resolved_logical_fields)
        packed = getattr(ctypes_cls, "_pack_", None) is not None
        return cls(
            label=label,
            ctypes_cls=ctypes_cls,
            ir_type=ir.LiteralStructType([field.ir_type for field in physical_fields], packed=packed),
            view_type=view_type,
            view_source=view_source,
            logical_fields=tuple(resolved_logical_fields),
            physical_fields=tuple(physical_fields),
        )

    def bind(self, builder: ir.IRBuilder, struct_ptr: ir.Value) -> BoundStructView:
        return self.view_type(self, builder, struct_ptr)

    def logical_field(self, name: str) -> LogicalFieldSpec:
        for field in self.logical_fields:
            if field.name == name:
                return field
        raise KeyError(name)

    def constant_from_ctypes(self, instance: ctypes.Structure) -> ir.Constant:
        if not isinstance(instance, self.ctypes_cls):
            raise TypeError(f"expected {self.ctypes_cls.__name__}, got {type(instance).__name__}")

        raw = bytes(ctypes.string_at(ctypes.addressof(instance), ctypes.sizeof(instance)))
        values: list[ir.Constant] = []
        for field in self.physical_fields:
            data = raw[field.byte_offset : field.byte_offset + field.byte_size]
            if field.kind == "padding":
                values.append(ir.Constant(field.ir_type, [I8(byte) for byte in data]))
                continue
            values.append(ir.Constant(field.ir_type, int.from_bytes(data, byteorder=BYTEORDER, signed=False)))
        return ir.Constant(self.ir_type, values)

    def define_global_from_ctypes(
        self, module: ir.Module, name: str, instance: ctypes.Structure
    ) -> ir.GlobalVariable:
        global_var = ir.GlobalVariable(module, self.ir_type, name=name)
        global_var.initializer = self.constant_from_ctypes(instance)
        return global_var


class CounterPair(ctypes.Structure):
    _fields_ = [
        ("count", ctypes.c_int),
        ("total", ctypes.c_longlong),
    ]


class PackedPacket(ctypes.Structure):
    _pack_ = 1
    _layout_ = "ms"
    _fields_ = [
        ("kind", ctypes.c_ubyte),
        ("size", ctypes.c_ushort),
        ("value", ctypes.c_uint),
    ]


class FlagsHeader(ctypes.Structure):
    _fields_ = [
        ("flag", ctypes.c_ubyte, 1),
        ("mode", ctypes.c_ubyte, 3),
        ("count", ctypes.c_ubyte, 4),
        ("wide", ctypes.c_ushort),
    ]


def build_generated_view_type(
    ctypes_cls: type[ctypes.Structure], logical_fields: list[LogicalFieldSpec]
) -> tuple[type[BoundStructView], str]:
    view_name = f"{ctypes_cls.__name__}View"
    source_lines = [
        f"class {view_name}(BoundStructView):",
        f'    """Generated bound view for {ctypes_cls.__name__}."""',
    ]
    for logical in logical_fields:
        source_lines.append(
            f'    {logical.name} = LogicalFieldDescriptor(_logical_fields["{logical.name}"])'
        )
    source = "\n".join(source_lines)
    namespace: dict[str, object] = {
        "BoundStructView": BoundStructView,
        "LogicalFieldDescriptor": LogicalFieldDescriptor,
        "_logical_fields": {logical.name: logical for logical in logical_fields},
    }
    exec(source, namespace)
    return namespace[view_name], source


def binding_struct_for(module_ref: binding.ModuleRef, struct_handle: StructHandle) -> binding.TypeRef:
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
        abi_size=target_data.get_abi_size(struct_type),
        abi_alignment=target_data.get_abi_alignment(struct_type),
        field_offsets=[target_data.get_element_offset(struct_type, index) for index in range(len(elements))],
    )


def ctypes_layout_summary(ctypes_cls: type[ctypes.Structure]) -> str:
    parts: list[str] = []
    for field_name, *_ in ctypes_cls._fields_:
        field_desc = getattr(ctypes_cls, field_name)
        if field_desc.is_bitfield:
            parts.append(
                f"{field_name}@{field_desc.offset}:bits={field_desc.bit_offset}+{field_desc.bit_size}"
            )
        else:
            parts.append(f"{field_name}@{field_desc.offset}:size={field_desc.size}")
    return (
        f"class={ctypes_cls.__name__} "
        f"sizeof={ctypes.sizeof(ctypes_cls)} "
        f"pack={getattr(ctypes_cls, '_pack_', None)!r} "
        f"fields=[{', '.join(parts)}]"
    )


def describe_ctypes_decl(ctypes_cls: type[ctypes.Structure]) -> str:
    rendered_fields: list[str] = []
    for field_name, ctype, *rest in ctypes_cls._fields_:
        if rest:
            rendered_fields.append(f"{field_name}:{ctype.__name__}:{rest[0]}")
        else:
            rendered_fields.append(f"{field_name}:{ctype.__name__}")
    return (
        f"{ctypes_cls.__name__}(_pack_={getattr(ctypes_cls, '_pack_', None)!r}, "
        f"_fields_=[{', '.join(rendered_fields)}])"
    )


def describe_reified_mapping(handle: StructHandle) -> str:
    physical = ", ".join(
        f"{index}:{field.name}@{field.byte_offset}:{field.ir_type}"
        for index, field in enumerate(handle.physical_fields)
    )
    logical = ", ".join(
        (
            f"{field.name}->[{field.storage_index}] {field.storage_name}"
            if not field.is_bitfield
            else f"{field.name}->[{field.storage_index}] {field.storage_name} bits {field.bit_offset}+{field.bit_size}"
        )
        for field in handle.logical_fields
    )
    return f"physical=[{physical}] logical=[{logical}]"


def build_module() -> tuple[ir.Module, dict[str, StructHandle], dict[str, ctypes.Structure]]:
    target_machine = configure_llvm()
    module = ir.Module(name="ctypes_struct_reification")
    module.triple = binding.get_default_triple()
    module.data_layout = str(target_machine.target_data)

    handles = {
        "counter_pair": StructHandle.from_ctypes("counter pair", CounterPair),
        "packed_packet": StructHandle.from_ctypes("packed packet", PackedPacket),
        "flags_header": StructHandle.from_ctypes("flags header", FlagsHeader),
    }

    header = FlagsHeader()
    header.flag = 1
    header.mode = 5
    header.count = 12
    header.wide = 0x3456

    instances: dict[str, ctypes.Structure] = {
        "counter_pair": CounterPair(-2, 41),
        "packed_packet": PackedPacket(7, 300, 0x12345678),
        "flags_header": header,
    }

    counter_global = handles["counter_pair"].define_global_from_ctypes(module, "counter_pair_data", instances["counter_pair"])
    packet_global = handles["packed_packet"].define_global_from_ctypes(module, "packed_packet_data", instances["packed_packet"])
    header_global = handles["flags_header"].define_global_from_ctypes(module, "flags_header_data", instances["flags_header"])

    header_mode = handles["flags_header"].logical_field("mode")

    raw_fn = ir.Function(module, ir.FunctionType(I64, []), name="read_header_mode_raw")
    builder = ir.IRBuilder(raw_fn.append_basic_block("entry"))
    mode_storage_ptr = builder.gep(
        header_global,
        [I32(0), I32(header_mode.storage_index)],
        inbounds=True,
        name="mode_storage_ptr",
    )
    mode_storage = builder.load(mode_storage_ptr, name="mode_storage")
    mode_shifted = builder.lshr(mode_storage, header_mode.storage_ir_type(header_mode.bit_offset), name="mode_shifted")
    mode_masked = builder.and_(
        mode_shifted,
        header_mode.storage_ir_type((1 << header_mode.bit_size) - 1),
        name="mode_masked",
    )
    builder.ret(builder.zext(builder.trunc(mode_masked, header_mode.logical_ir_type, name="mode"), I64, name="mode_i64"))

    generated_mode_fn = ir.Function(module, ir.FunctionType(I64, []), name="read_header_mode_generated")
    builder = ir.IRBuilder(generated_mode_fn.append_basic_block("entry"))
    header_view = handles["flags_header"].bind(builder, header_global)
    builder.ret(builder.zext(header_view.mode.load(), I64, name="mode_i64"))

    set_mode_fn = ir.Function(module, ir.FunctionType(I64, [I8]), name="set_header_mode_generated")
    builder = ir.IRBuilder(set_mode_fn.append_basic_block("entry"))
    header_view = handles["flags_header"].bind(builder, header_global)
    header_view.mode.store(set_mode_fn.args[0])
    builder.ret(builder.zext(header_view.mode.load(name="updated_mode"), I64, name="updated_mode_i64"))

    sum_pair_fn = ir.Function(
        module,
        ir.FunctionType(I64, [handles["counter_pair"].ir_type.as_pointer()]),
        name="sum_counter_pair",
    )
    builder = ir.IRBuilder(sum_pair_fn.append_basic_block("entry"))
    pair_view = handles["counter_pair"].bind(builder, sum_pair_fn.args[0])
    count = builder.sext(pair_view.count.load(), I64, name="count_i64")
    builder.ret(builder.add(count, pair_view.total.load(), name="sum"))

    read_packet_fn = ir.Function(module, ir.FunctionType(I64, []), name="read_packed_packet_value")
    builder = ir.IRBuilder(read_packet_fn.append_basic_block("entry"))
    packet_view = handles["packed_packet"].bind(builder, packet_global)
    builder.ret(builder.zext(packet_view.value.load(), I64, name="value_i64"))

    header_sum_fn = ir.Function(
        module,
        ir.FunctionType(I64, [handles["flags_header"].ir_type.as_pointer()]),
        name="sum_header_fields_generated",
    )
    builder = ir.IRBuilder(header_sum_fn.append_basic_block("entry"))
    header_view = handles["flags_header"].bind(builder, header_sum_fn.args[0])
    flag = builder.zext(header_view.flag.load(), I64, name="flag_i64")
    mode = builder.zext(header_view.mode.load(), I64, name="mode_i64")
    count = builder.zext(header_view.count.load(), I64, name="count_i64")
    wide = builder.zext(header_view.wide.load(), I64, name="wide_i64")
    total = builder.add(flag, mode, name="flag_plus_mode")
    total = builder.add(total, count, name="plus_count")
    builder.ret(builder.add(total, wide, name="plus_wide"))

    _ = counter_global
    return module, handles, instances


def main() -> None:
    target_machine = configure_llvm()
    module, handles, instances = build_module()
    llvm_ir = str(module)
    parsed = binding.parse_assembly(llvm_ir)
    parsed.verify()

    engine = binding.create_mcjit_compiler(parsed, target_machine)
    engine.finalize_object()

    counter_addr = engine.get_global_value_address("counter_pair_data")
    packet_addr = engine.get_global_value_address("packed_packet_data")
    header_addr = engine.get_global_value_address("flags_header_data")

    counter_view = CounterPair.from_address(counter_addr)
    packet_view = PackedPacket.from_address(packet_addr)
    header_view = FlagsHeader.from_address(header_addr)

    read_header_mode_raw = ctypes.CFUNCTYPE(ctypes.c_int64)(engine.get_function_address("read_header_mode_raw"))
    read_header_mode_generated = ctypes.CFUNCTYPE(ctypes.c_int64)(engine.get_function_address("read_header_mode_generated"))
    set_header_mode_generated = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.c_uint8)(
        engine.get_function_address("set_header_mode_generated")
    )
    sum_counter_pair = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.POINTER(CounterPair))(
        engine.get_function_address("sum_counter_pair")
    )
    read_packed_packet_value = ctypes.CFUNCTYPE(ctypes.c_int64)(
        engine.get_function_address("read_packed_packet_value")
    )
    sum_header_fields_generated = ctypes.CFUNCTYPE(ctypes.c_int64, ctypes.POINTER(FlagsHeader))(
        engine.get_function_address("sum_header_fields_generated")
    )

    layout_summaries = [
        summarize_layout(target_machine.target_data, parsed, handles["counter_pair"]),
        summarize_layout(target_machine.target_data, parsed, handles["packed_packet"]),
        summarize_layout(target_machine.target_data, parsed, handles["flags_header"]),
    ]

    print("== Question ==")
    print(
        "How do you start from a ctypes.Structure declaration and reify the right "
        "llvmlite struct shape plus a named bound view, including real ctypes bitfields?"
    )
    print()
    print("== ctypes Declarations ==")
    print(describe_ctypes_decl(CounterPair))
    print(describe_ctypes_decl(PackedPacket))
    print(describe_ctypes_decl(FlagsHeader))
    print()
    print("== Reified Mapping ==")
    print(f"counter pair: {describe_reified_mapping(handles['counter_pair'])}")
    print(f"packed packet: {describe_reified_mapping(handles['packed_packet'])}")
    print(f"flags header: {describe_reified_mapping(handles['flags_header'])}")
    print()
    print("== Generated Python Views ==")
    print(handles["counter_pair"].view_source)
    print()
    print(handles["packed_packet"].view_source)
    print()
    print(handles["flags_header"].view_source)
    print()
    print("== Generated IR ==")
    print(llvm_ir.rstrip())
    print()
    print("== Layout Summary (LLVM Target Data) ==")
    for summary in layout_summaries:
        print(
            f"{summary.label}: ir={summary.ir_text} abi_size={summary.abi_size} "
            f"abi_align={summary.abi_alignment} field_offsets={summary.field_offsets}"
        )
    print()
    print("== ctypes Layout Summary ==")
    print(f"counter pair: {ctypes_layout_summary(CounterPair)}")
    print(f"packed packet: {ctypes_layout_summary(PackedPacket)}")
    print(f"flags header: {ctypes_layout_summary(FlagsHeader)}")
    print()
    print("== Live Proof ==")
    print(f"counter_pair_data ctypes view = ({counter_view.count}, {counter_view.total})")
    print(f"sum_counter_pair(&counter_pair_data) -> {sum_counter_pair(ctypes.byref(counter_view))}")
    print(f"packed_packet_data ctypes view = ({packet_view.kind}, {packet_view.size}, {packet_view.value})")
    print(f"read_packed_packet_value() -> {read_packed_packet_value()}")
    print(
        "flags_header_data ctypes view = "
        f"(flag={header_view.flag}, mode={header_view.mode}, count={header_view.count}, wide={header_view.wide})"
    )
    print(f"read_header_mode_raw() -> {read_header_mode_raw()}")
    print(f"read_header_mode_generated() -> {read_header_mode_generated()}")
    print(f"sum_header_fields_generated(&flags_header_data) -> {sum_header_fields_generated(ctypes.byref(header_view))}")
    header_view.mode = 2
    header_view.count = 9
    print(
        "flags_header_data after host mutation = "
        f"(flag={header_view.flag}, mode={header_view.mode}, count={header_view.count}, wide={header_view.wide})"
    )
    print(f"read_header_mode_generated() after host mutation -> {read_header_mode_generated()}")
    print(f"set_header_mode_generated(6) -> {set_header_mode_generated(6)}")
    print(
        "flags_header_data after generated bitfield store = "
        f"(flag={header_view.flag}, mode={header_view.mode}, count={header_view.count}, wide={header_view.wide})"
    )
    print()
    print("== Takeaway ==")
    print(
        "Treat the ctypes declaration as the source of truth, reify exact host layout "
        "into a literal LLVM struct with explicit padding or packing as needed, group "
        "shared bitfield storage explicitly, and generate a named bound view that keeps "
        "the logical fields readable without pretending the storage layout disappeared."
    )

    _ = instances


if __name__ == "__main__":
    main()
