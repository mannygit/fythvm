"""Dictionary-backed current-word resolution for lowered interpreter dispatch."""

from __future__ import annotations

from dataclasses import dataclass

from llvmlite import ir

from ..codegen.structs import BoundStructView
from ..codegen.thread import ThreadRefIR
from ..codegen.types import I32
from .ir import DictionaryIR
from .schema import NULL_INDEX


@dataclass(frozen=True)
class CurrentWordIR:
    """Explicit current-word facts resolved through real dictionary layout."""

    state: BoundStructView
    dictionary_ir: DictionaryIR
    current_xt: ir.Value
    found_word_index: ir.Value
    resolved_handler_id: ir.Value
    current_xt_field_name: str = "current_xt"

    def is_custom_word(self) -> ir.Value:
        return self.dictionary_ir.builder.icmp_signed(
            "!=",
            self.found_word_index,
            I32(NULL_INDEX),
            name="current_word_is_custom",
        )

    def install_xt(self, xt: ir.Value) -> None:
        current_xt_field = getattr(self.state, self.current_xt_field_name)
        current_xt_field.store(xt)

    def thread_cells_ptr(self, *, name: str = "current_word_thread_cells") -> ir.Value:
        return self.dictionary_ir.thread_cells_ptr_for_cfa(self.current_xt, name=name)

    def thread_ref(
        self,
        thread_length_table: ir.Value,
        *,
        name_prefix: str = "current_word",
    ) -> ThreadRefIR:
        thread_length_ptr = self.dictionary_ir.builder.gep(
            thread_length_table,
            [self.current_xt],
            inbounds=True,
            name=f"{name_prefix}_thread_length_ptr",
        )
        return ThreadRefIR(
            cells=self.thread_cells_ptr(name=f"{name_prefix}_thread_cells"),
            length=self.dictionary_ir.builder.load(
                thread_length_ptr,
                name=f"{name_prefix}_thread_length",
            ),
        )

    @classmethod
    def resolve_from_state(
        cls,
        *,
        builder: ir.IRBuilder,
        state: BoundStructView,
        dispatch_custom_block: ir.Block,
        dispatch_primitive_block: ir.Block,
        dispatch_resolved_block: ir.Block,
        name_prefix: str,
        current_xt_field_name: str = "current_xt",
        dictionary_memory_field_name: str = "dictionary_memory",
    ) -> "CurrentWordIR":
        current_xt_field = getattr(state, current_xt_field_name)
        dictionary_memory_field = getattr(state, dictionary_memory_field_name)
        current_xt = current_xt_field.load(name=f"{name_prefix}_current_xt")
        dictionary_memory = dictionary_memory_field.load(name=f"{name_prefix}_dictionary_memory")
        dictionary_ir = DictionaryIR(builder, dictionary_memory)
        found_word_index = dictionary_ir.find_word_by_cfa(current_xt)
        found_custom_word = builder.icmp_signed(
            "!=",
            found_word_index,
            I32(NULL_INDEX),
            name=f"{name_prefix}_found_custom_word",
        )
        builder.cbranch(found_custom_word, dispatch_custom_block, dispatch_primitive_block)

        with builder.goto_block(dispatch_custom_block):
            custom_word = dictionary_ir.word(found_word_index)
            custom_code_field = custom_word.code_field.bind(dictionary_ir.code_field_handle)
            custom_handler_id = builder.zext(
                custom_code_field.handler_id.load(name=f"{name_prefix}_custom_handler_id_i7"),
                I32,
                name=f"{name_prefix}_custom_handler_id",
            )
            builder.branch(dispatch_resolved_block)

        with builder.goto_block(dispatch_primitive_block):
            builder.branch(dispatch_resolved_block)

        with builder.goto_block(dispatch_resolved_block):
            resolved_handler_id = builder.phi(I32, name=f"{name_prefix}_handler_id")
            resolved_handler_id.add_incoming(custom_handler_id, dispatch_custom_block)
            resolved_handler_id.add_incoming(current_xt, dispatch_primitive_block)

        return cls(
            state=state,
            dictionary_ir=dictionary_ir,
            current_xt=current_xt,
            found_word_index=found_word_index,
            resolved_handler_id=resolved_handler_id,
            current_xt_field_name=current_xt_field_name,
        )
