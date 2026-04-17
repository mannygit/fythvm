"""Instruction metadata for organizing primitive words.

This module is intentionally separate from ``families.py``.

- families describe semantic/runtime behavior and payload interpretation
- instruction metadata describes organizational categories for browsing and grouping
- handler requirements describe concrete lowering resources and shared kernel hints

Current kernel ids are metadata only. They are intended to line up, where practical,
with the shared-lowering vocabulary explored in:

- ``docs/references/forth/primitive-stack-shape-synthesis.md``
- ``explorations/lab/python-shared-stack-kernels/README.md``

The first pass assigns full metadata to the current ``primitive-empty`` instruction set
plus the first concrete non-empty/runtime-special cases:

- ``LIT``
- ``BRANCH``
- ``0BRANCH``
- ``LITSTRING``
- ``DOCOL``
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum

from .families import (
    COLON_THREAD_FAMILY,
    DEFAULT_INSTRUCTION_FAMILIES,
    PRIMITIVE_EMPTY_FAMILY,
    PRIMITIVE_INLINE_OPERAND_FAMILY,
    WordFamily,
)


class AssociatedDataSource(Enum):
    """Runtime source for handler-associated data beyond the base machine state."""

    NONE = "none"
    WORD_LOCAL_DFA = "word_local_dfa"
    INLINE_THREAD = "inline_thread"


@dataclass(frozen=True, slots=True)
class HandlerRequirements:
    """Declarative lowering requirements for a concrete handler."""

    min_data_stack_in: int = 0
    min_data_stack_out_space: int = 0
    min_return_stack_in: int = 0
    min_return_stack_out_space: int = 0
    needs_thread_cursor: bool = False
    needs_thread_jump: bool = False
    needs_execution_control: bool = False
    needs_current_xt: bool = False
    needs_return_stack: bool = False
    needs_input_source: bool = False
    needs_source_cursor: bool = False
    needs_error_exit: bool = False
    needs_dictionary: bool = False
    needs_here: bool = False
    needs_thread_emitter: bool = False
    needs_patch_stack: bool = False
    # Shared lowering-shape hint. This is metadata only for now, not a callable or
    # runtime ABI choice. Names are intended to track the stack-kernel exploration
    # vocabulary where practical.
    kernel: str | None = None


class InstructionCategory(Enum):
    """Organizational categories for primitive instructions."""

    STACK = "stack"
    ARITHMETIC = "arithmetic"
    COMPARISON_BITWISE = "comparison_bitwise"
    MEMORY = "memory"
    RETURN_DATA_STACK_CONTROL = "return_data_stack_control"
    PARSER_IO = "parser_io"
    DICTIONARY_COMPILER = "dictionary_compiler"
    HOST_BRIDGE = "host_bridge"


class PrimitiveInstruction(IntEnum):
    """Package-local ids for the current primitive-empty instruction set."""

    DROP = 1
    SWAP = 2
    DUP = 3
    OVER = 4
    ROT = 5
    NROT = 6
    TWODROP = 7
    TWODUP = 8
    TWOSWAP = 9
    QDUP = 10
    INCR = 11
    DECR = 12
    INCR4 = 13
    DECR4 = 14
    ADD = 15
    SUB = 16
    MUL = 17
    DIVMOD = 18
    EQU = 19
    NEQU = 20
    LT = 21
    GT = 22
    LE = 23
    GE = 24
    ZEQU = 25
    ZNEQU = 26
    ZLT = 27
    ZGT = 28
    ZLE = 29
    ZGE = 30
    AND = 31
    OR = 32
    XOR = 33
    INVERT = 34
    EXIT = 35
    STORE = 36
    FETCH = 37
    ADDSTORE = 38
    SUBSTORE = 39
    STOREBYTE = 40
    FETCHBYTE = 41
    CCOPY = 42
    CMOVE = 43
    TOR = 44
    FROMR = 45
    RSPFETCH = 46
    RSPSTORE = 47
    RDROP = 48
    DSPFETCH = 49
    DSPSTORE = 50
    KEY = 51
    EMIT = 52
    WORD = 53
    NUMBER = 54
    FIND = 55
    TCFA = 56
    CREATE = 57
    COMMA = 58
    LBRAC = 59
    RBRAC = 60
    IMMEDIATE = 61
    HIDDEN = 62
    TICK = 63
    TELL = 64
    INTERPRET = 65
    CHAR = 66
    EXECUTE = 67
    SYSCALL3 = 68
    SYSCALL2 = 69
    SYSCALL1 = 70
    SYSCALL0 = 71
    LIT = 72
    BRANCH = 73
    ZBRANCH = 74
    LITSTRING = 75
    DOCOL = 76
    HALT = 77


@dataclass(frozen=True, slots=True)
class InstructionDescriptor:
    """Package metadata for a concrete instruction id."""

    handler_id: int
    key: str
    family: WordFamily
    category: InstructionCategory
    associated_data_source: AssociatedDataSource
    requirements: HandlerRequirements
    description: str


class InstructionRegistry:
    """Maps concrete handler ids to their package metadata."""

    def __init__(self, descriptors: dict[int, InstructionDescriptor] | None = None) -> None:
        self._descriptors: dict[int, InstructionDescriptor] = {}
        if descriptors is not None:
            for descriptor in descriptors.values():
                self.register(descriptor)

    def register(self, descriptor: InstructionDescriptor) -> None:
        self._descriptors[descriptor.handler_id] = descriptor

    def descriptor_for_handler_id(self, handler_id: int) -> InstructionDescriptor | None:
        return self._descriptors.get(handler_id)

    def snapshot(self) -> dict[int, InstructionDescriptor]:
        return dict(self._descriptors)


def _descriptor(
    handler_id: PrimitiveInstruction,
    key: str,
    category: InstructionCategory,
    description: str,
    *,
    family: WordFamily = PRIMITIVE_EMPTY_FAMILY,
    associated_data_source: AssociatedDataSource = AssociatedDataSource.NONE,
    requirements: HandlerRequirements | None = None,
) -> InstructionDescriptor:
    return InstructionDescriptor(
        handler_id=int(handler_id),
        key=key,
        family=family,
        category=category,
        associated_data_source=associated_data_source,
        requirements=HandlerRequirements() if requirements is None else requirements,
        description=description,
    )


def _req(
    *,
    min_data_stack_in: int = 0,
    min_data_stack_out_space: int = 0,
    min_return_stack_in: int = 0,
    min_return_stack_out_space: int = 0,
    needs_thread_cursor: bool = False,
    needs_thread_jump: bool = False,
    needs_execution_control: bool = False,
    needs_current_xt: bool = False,
    needs_return_stack: bool = False,
    needs_input_source: bool = False,
    needs_source_cursor: bool = False,
    needs_error_exit: bool = True,
    needs_dictionary: bool = False,
    needs_here: bool = False,
    needs_thread_emitter: bool = False,
    needs_patch_stack: bool = False,
    kernel: str | None = None,
) -> HandlerRequirements:
    return HandlerRequirements(
        min_data_stack_in=min_data_stack_in,
        min_data_stack_out_space=min_data_stack_out_space,
        min_return_stack_in=min_return_stack_in,
        min_return_stack_out_space=min_return_stack_out_space,
        needs_thread_cursor=needs_thread_cursor,
        needs_thread_jump=needs_thread_jump,
        needs_execution_control=needs_execution_control,
        needs_current_xt=needs_current_xt,
        needs_return_stack=needs_return_stack,
        needs_input_source=needs_input_source,
        needs_source_cursor=needs_source_cursor,
        needs_error_exit=needs_error_exit,
        needs_dictionary=needs_dictionary,
        needs_here=needs_here,
        needs_thread_emitter=needs_thread_emitter,
        needs_patch_stack=needs_patch_stack,
        kernel=kernel,
    )


def _stack_req(min_in: int, out_space: int, kernel: str) -> HandlerRequirements:
    return _req(
        min_data_stack_in=min_in,
        min_data_stack_out_space=out_space,
        kernel=kernel,
    )


def _return_req(
    *,
    min_data_stack_in: int = 0,
    min_data_stack_out_space: int = 0,
    min_return_stack_in: int = 0,
    min_return_stack_out_space: int = 0,
    needs_execution_control: bool = False,
    kernel: str,
) -> HandlerRequirements:
    return _req(
        min_data_stack_in=min_data_stack_in,
        min_data_stack_out_space=min_data_stack_out_space,
        min_return_stack_in=min_return_stack_in,
        min_return_stack_out_space=min_return_stack_out_space,
        needs_return_stack=True,
        needs_execution_control=needs_execution_control,
        kernel=kernel,
    )


DEFAULT_INSTRUCTIONS = InstructionRegistry(
    descriptors={
        int(PrimitiveInstruction.DROP): _descriptor(PrimitiveInstruction.DROP, "DROP", InstructionCategory.STACK, "Drop top of data stack.", requirements=_stack_req(1, 0, "drop")),
        int(PrimitiveInstruction.SWAP): _descriptor(PrimitiveInstruction.SWAP, "SWAP", InstructionCategory.STACK, "Swap top two stack items.", requirements=_stack_req(2, 2, "swap2")),
        int(PrimitiveInstruction.DUP): _descriptor(PrimitiveInstruction.DUP, "DUP", InstructionCategory.STACK, "Duplicate top stack item.", requirements=_stack_req(1, 2, "dup")),
        int(PrimitiveInstruction.OVER): _descriptor(PrimitiveInstruction.OVER, "OVER", InstructionCategory.STACK, "Copy second item to top of stack.", requirements=_stack_req(2, 3, "over")),
        int(PrimitiveInstruction.ROT): _descriptor(PrimitiveInstruction.ROT, "ROT", InstructionCategory.STACK, "Rotate top three stack items.", requirements=_stack_req(3, 3, "rot3")),
        int(PrimitiveInstruction.NROT): _descriptor(PrimitiveInstruction.NROT, "-ROT", InstructionCategory.STACK, "Reverse-rotate top three stack items.", requirements=_stack_req(3, 3, "nrot3")),
        int(PrimitiveInstruction.TWODROP): _descriptor(PrimitiveInstruction.TWODROP, "2DROP", InstructionCategory.STACK, "Drop top two stack items.", requirements=_stack_req(2, 0, "drop2")),
        int(PrimitiveInstruction.TWODUP): _descriptor(PrimitiveInstruction.TWODUP, "2DUP", InstructionCategory.STACK, "Duplicate top two stack items.", requirements=_stack_req(2, 4, "dup2")),
        int(PrimitiveInstruction.TWOSWAP): _descriptor(PrimitiveInstruction.TWOSWAP, "2SWAP", InstructionCategory.STACK, "Swap top two stack pairs.", requirements=_stack_req(4, 4, "swap4")),
        int(PrimitiveInstruction.QDUP): _descriptor(PrimitiveInstruction.QDUP, "?DUP", InstructionCategory.STACK, "Duplicate top item if non-zero.", requirements=_stack_req(1, 2, "qdup")),
        int(PrimitiveInstruction.INCR): _descriptor(PrimitiveInstruction.INCR, "1+", InstructionCategory.ARITHMETIC, "Increment top of stack.", requirements=_stack_req(1, 1, "unary_transform")),
        int(PrimitiveInstruction.DECR): _descriptor(PrimitiveInstruction.DECR, "1-", InstructionCategory.ARITHMETIC, "Decrement top of stack.", requirements=_stack_req(1, 1, "unary_transform")),
        int(PrimitiveInstruction.INCR4): _descriptor(PrimitiveInstruction.INCR4, "4+", InstructionCategory.ARITHMETIC, "Add one cell to top of stack.", requirements=_stack_req(1, 1, "unary_transform")),
        int(PrimitiveInstruction.DECR4): _descriptor(PrimitiveInstruction.DECR4, "4-", InstructionCategory.ARITHMETIC, "Subtract one cell from top of stack.", requirements=_stack_req(1, 1, "unary_transform")),
        int(PrimitiveInstruction.ADD): _descriptor(PrimitiveInstruction.ADD, "+", InstructionCategory.ARITHMETIC, "Add top two stack items.", requirements=_stack_req(2, 1, "binary_reduce")),
        int(PrimitiveInstruction.SUB): _descriptor(PrimitiveInstruction.SUB, "-", InstructionCategory.ARITHMETIC, "Subtract top item from next item.", requirements=_stack_req(2, 1, "binary_reduce")),
        int(PrimitiveInstruction.MUL): _descriptor(PrimitiveInstruction.MUL, "*", InstructionCategory.ARITHMETIC, "Multiply top two stack items.", requirements=_stack_req(2, 1, "binary_reduce")),
        int(PrimitiveInstruction.DIVMOD): _descriptor(PrimitiveInstruction.DIVMOD, "/MOD", InstructionCategory.ARITHMETIC, "Compute quotient and remainder.", requirements=_stack_req(2, 2, "binary_divmod")),
        int(PrimitiveInstruction.EQU): _descriptor(PrimitiveInstruction.EQU, "=", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items for equality.", requirements=_stack_req(2, 1, "binary_compare")),
        int(PrimitiveInstruction.NEQU): _descriptor(PrimitiveInstruction.NEQU, "<>", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items for inequality.", requirements=_stack_req(2, 1, "binary_compare")),
        int(PrimitiveInstruction.LT): _descriptor(PrimitiveInstruction.LT, "<", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with less-than.", requirements=_stack_req(2, 1, "binary_compare")),
        int(PrimitiveInstruction.GT): _descriptor(PrimitiveInstruction.GT, ">", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with greater-than.", requirements=_stack_req(2, 1, "binary_compare")),
        int(PrimitiveInstruction.LE): _descriptor(PrimitiveInstruction.LE, "<=", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with less-or-equal.", requirements=_stack_req(2, 1, "binary_compare")),
        int(PrimitiveInstruction.GE): _descriptor(PrimitiveInstruction.GE, ">=", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with greater-or-equal.", requirements=_stack_req(2, 1, "binary_compare")),
        int(PrimitiveInstruction.ZEQU): _descriptor(PrimitiveInstruction.ZEQU, "0=", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for zero.", requirements=_stack_req(1, 1, "unary_predicate")),
        int(PrimitiveInstruction.ZNEQU): _descriptor(PrimitiveInstruction.ZNEQU, "0<>", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for non-zero.", requirements=_stack_req(1, 1, "unary_predicate")),
        int(PrimitiveInstruction.ZLT): _descriptor(PrimitiveInstruction.ZLT, "0<", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for negative.", requirements=_stack_req(1, 1, "unary_predicate")),
        int(PrimitiveInstruction.ZGT): _descriptor(PrimitiveInstruction.ZGT, "0>", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for positive.", requirements=_stack_req(1, 1, "unary_predicate")),
        int(PrimitiveInstruction.ZLE): _descriptor(PrimitiveInstruction.ZLE, "0<=", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for non-positive.", requirements=_stack_req(1, 1, "unary_predicate")),
        int(PrimitiveInstruction.ZGE): _descriptor(PrimitiveInstruction.ZGE, "0>=", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for non-negative.", requirements=_stack_req(1, 1, "unary_predicate")),
        int(PrimitiveInstruction.AND): _descriptor(PrimitiveInstruction.AND, "AND", InstructionCategory.COMPARISON_BITWISE, "Bitwise and on top two stack items.", requirements=_stack_req(2, 1, "binary_reduce")),
        int(PrimitiveInstruction.OR): _descriptor(PrimitiveInstruction.OR, "OR", InstructionCategory.COMPARISON_BITWISE, "Bitwise or on top two stack items.", requirements=_stack_req(2, 1, "binary_reduce")),
        int(PrimitiveInstruction.XOR): _descriptor(PrimitiveInstruction.XOR, "XOR", InstructionCategory.COMPARISON_BITWISE, "Bitwise xor on top two stack items.", requirements=_stack_req(2, 1, "binary_reduce")),
        int(PrimitiveInstruction.INVERT): _descriptor(PrimitiveInstruction.INVERT, "INVERT", InstructionCategory.COMPARISON_BITWISE, "Bitwise invert top of stack.", requirements=_stack_req(1, 1, "unary_transform")),
        int(PrimitiveInstruction.EXIT): _descriptor(PrimitiveInstruction.EXIT, "EXIT", InstructionCategory.DICTIONARY_COMPILER, "Return from the current threaded word.", requirements=_return_req(min_return_stack_in=1, needs_execution_control=True, kernel="exit")),
        int(PrimitiveInstruction.STORE): _descriptor(PrimitiveInstruction.STORE, "!", InstructionCategory.MEMORY, "Store a cell through an address.", requirements=_stack_req(2, 0, "store_cell")),
        int(PrimitiveInstruction.FETCH): _descriptor(PrimitiveInstruction.FETCH, "@", InstructionCategory.MEMORY, "Fetch a cell through an address.", requirements=_stack_req(1, 1, "fetch_cell")),
        int(PrimitiveInstruction.ADDSTORE): _descriptor(PrimitiveInstruction.ADDSTORE, "+!", InstructionCategory.MEMORY, "Add to a cell through an address.", requirements=_stack_req(2, 0, "update_cell")),
        int(PrimitiveInstruction.SUBSTORE): _descriptor(PrimitiveInstruction.SUBSTORE, "-!", InstructionCategory.MEMORY, "Subtract from a cell through an address.", requirements=_stack_req(2, 0, "update_cell")),
        int(PrimitiveInstruction.STOREBYTE): _descriptor(PrimitiveInstruction.STOREBYTE, "C!", InstructionCategory.MEMORY, "Store a byte through an address.", requirements=_stack_req(2, 0, "store_byte")),
        int(PrimitiveInstruction.FETCHBYTE): _descriptor(PrimitiveInstruction.FETCHBYTE, "C@", InstructionCategory.MEMORY, "Fetch a byte through an address.", requirements=_stack_req(1, 1, "fetch_byte")),
        int(PrimitiveInstruction.CCOPY): _descriptor(PrimitiveInstruction.CCOPY, "C@C!", InstructionCategory.MEMORY, "Copy one byte from source address to destination.", requirements=_stack_req(2, 0, "copy_byte")),
        int(PrimitiveInstruction.CMOVE): _descriptor(PrimitiveInstruction.CMOVE, "CMOVE", InstructionCategory.MEMORY, "Copy a byte range in memory.", requirements=_stack_req(3, 0, "move_bytes")),
        int(PrimitiveInstruction.TOR): _descriptor(PrimitiveInstruction.TOR, ">R", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Move top of data stack to return stack.", requirements=_return_req(min_data_stack_in=1, min_return_stack_out_space=1, kernel="to_return")),
        int(PrimitiveInstruction.FROMR): _descriptor(PrimitiveInstruction.FROMR, "R>", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Move top of return stack to data stack.", requirements=_return_req(min_data_stack_out_space=1, min_return_stack_in=1, kernel="from_return")),
        int(PrimitiveInstruction.RSPFETCH): _descriptor(PrimitiveInstruction.RSPFETCH, "RSP@", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Fetch return-stack pointer.", requirements=_return_req(min_data_stack_out_space=1, kernel="rsp_fetch")),
        int(PrimitiveInstruction.RSPSTORE): _descriptor(PrimitiveInstruction.RSPSTORE, "RSP!", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Store return-stack pointer.", requirements=_return_req(min_data_stack_in=1, kernel="rsp_store")),
        int(PrimitiveInstruction.RDROP): _descriptor(PrimitiveInstruction.RDROP, "RDROP", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Drop top of return stack.", requirements=_return_req(min_return_stack_in=1, kernel="rdrop")),
        int(PrimitiveInstruction.DSPFETCH): _descriptor(PrimitiveInstruction.DSPFETCH, "DSP@", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Fetch data-stack pointer.", requirements=_req(min_data_stack_out_space=1, kernel="dsp_fetch")),
        int(PrimitiveInstruction.DSPSTORE): _descriptor(PrimitiveInstruction.DSPSTORE, "DSP!", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Store data-stack pointer.", requirements=_req(min_data_stack_in=1, kernel="dsp_store")),
        int(PrimitiveInstruction.KEY): _descriptor(PrimitiveInstruction.KEY, "KEY", InstructionCategory.PARSER_IO, "Read one input character.", requirements=_req(min_data_stack_out_space=1, needs_input_source=True, kernel="read_char")),
        int(PrimitiveInstruction.EMIT): _descriptor(PrimitiveInstruction.EMIT, "EMIT", InstructionCategory.PARSER_IO, "Write one output character.", requirements=_req(min_data_stack_in=1, kernel="emit_char")),
        int(PrimitiveInstruction.WORD): _descriptor(PrimitiveInstruction.WORD, "WORD", InstructionCategory.PARSER_IO, "Parse the next token from input.", requirements=_req(min_data_stack_out_space=1, needs_input_source=True, kernel="parse_word")),
        int(PrimitiveInstruction.NUMBER): _descriptor(PrimitiveInstruction.NUMBER, "NUMBER", InstructionCategory.PARSER_IO, "Convert a parsed token to a number.", requirements=_req(needs_input_source=True, kernel="parse_number")),
        int(PrimitiveInstruction.FIND): _descriptor(PrimitiveInstruction.FIND, "FIND", InstructionCategory.DICTIONARY_COMPILER, "Look up a word name in the dictionary.", requirements=_req(needs_dictionary=True, kernel="find_word")),
        int(PrimitiveInstruction.TCFA): _descriptor(PrimitiveInstruction.TCFA, ">CFA", InstructionCategory.DICTIONARY_COMPILER, "Recover the code-field address from a dictionary header.", requirements=_req(min_data_stack_in=1, min_data_stack_out_space=1, kernel="to_cfa")),
        int(PrimitiveInstruction.CREATE): _descriptor(PrimitiveInstruction.CREATE, "CREATE", InstructionCategory.DICTIONARY_COMPILER, "Create and link a new dictionary entry.", requirements=_req(needs_input_source=True, needs_dictionary=True, needs_here=True, kernel="create_word")),
        int(PrimitiveInstruction.COMMA): _descriptor(PrimitiveInstruction.COMMA, ",", InstructionCategory.DICTIONARY_COMPILER, "Append one cell to the current definition.", requirements=_req(min_data_stack_in=1, needs_dictionary=True, needs_here=True, kernel="append_cell")),
        int(PrimitiveInstruction.LBRAC): _descriptor(PrimitiveInstruction.LBRAC, "[", InstructionCategory.DICTIONARY_COMPILER, "Switch compiler state to interpret mode.", requirements=_req(kernel="set_interpret_mode")),
        int(PrimitiveInstruction.RBRAC): _descriptor(PrimitiveInstruction.RBRAC, "]", InstructionCategory.DICTIONARY_COMPILER, "Switch compiler state to compile mode.", requirements=_req(kernel="set_compile_mode")),
        int(PrimitiveInstruction.IMMEDIATE): _descriptor(PrimitiveInstruction.IMMEDIATE, "IMMEDIATE", InstructionCategory.DICTIONARY_COMPILER, "Mark the latest word immediate.", requirements=_req(needs_dictionary=True, kernel="mark_immediate")),
        int(PrimitiveInstruction.HIDDEN): _descriptor(PrimitiveInstruction.HIDDEN, "HIDDEN", InstructionCategory.DICTIONARY_COMPILER, "Toggle hidden metadata on a word.", requirements=_req(min_data_stack_in=1, needs_dictionary=True, kernel="toggle_hidden")),
        int(PrimitiveInstruction.TICK): _descriptor(PrimitiveInstruction.TICK, "'", InstructionCategory.DICTIONARY_COMPILER, "Parse a name and return its xt.", requirements=_req(min_data_stack_out_space=1, needs_input_source=True, needs_dictionary=True, kernel="tick")),
        int(PrimitiveInstruction.TELL): _descriptor(PrimitiveInstruction.TELL, "TELL", InstructionCategory.PARSER_IO, "Write a counted or addressed string.", requirements=_req(min_data_stack_in=2, kernel="tell")),
        int(PrimitiveInstruction.INTERPRET): _descriptor(PrimitiveInstruction.INTERPRET, "INTERPRET", InstructionCategory.DICTIONARY_COMPILER, "Run the outer interpreter loop core.", requirements=_req(needs_input_source=True, needs_dictionary=True, kernel="interpret")),
        int(PrimitiveInstruction.CHAR): _descriptor(PrimitiveInstruction.CHAR, "CHAR", InstructionCategory.PARSER_IO, "Parse one character token.", requirements=_req(min_data_stack_out_space=1, needs_input_source=True, kernel="parse_char")),
        int(PrimitiveInstruction.EXECUTE): _descriptor(PrimitiveInstruction.EXECUTE, "EXECUTE", InstructionCategory.DICTIONARY_COMPILER, "Execute a word by xt.", requirements=_req(min_data_stack_in=1, kernel="execute_xt")),
        int(PrimitiveInstruction.SYSCALL3): _descriptor(PrimitiveInstruction.SYSCALL3, "SYSCALL3", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with three arguments.", requirements=_req(min_data_stack_in=4, min_data_stack_out_space=1, kernel="syscall3")),
        int(PrimitiveInstruction.SYSCALL2): _descriptor(PrimitiveInstruction.SYSCALL2, "SYSCALL2", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with two arguments.", requirements=_req(min_data_stack_in=3, min_data_stack_out_space=1, kernel="syscall2")),
        int(PrimitiveInstruction.SYSCALL1): _descriptor(PrimitiveInstruction.SYSCALL1, "SYSCALL1", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with one argument.", requirements=_req(min_data_stack_in=2, min_data_stack_out_space=1, kernel="syscall1")),
        int(PrimitiveInstruction.SYSCALL0): _descriptor(PrimitiveInstruction.SYSCALL0, "SYSCALL0", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with no arguments.", requirements=_req(min_data_stack_in=1, min_data_stack_out_space=1, kernel="syscall0")),
        int(PrimitiveInstruction.LIT): _descriptor(
            PrimitiveInstruction.LIT,
            "LIT",
            InstructionCategory.DICTIONARY_COMPILER,
            "Read one inline thread cell and push it as a literal.",
            family=PRIMITIVE_INLINE_OPERAND_FAMILY,
            associated_data_source=AssociatedDataSource.INLINE_THREAD,
            requirements=_req(
                min_data_stack_out_space=1,
                needs_thread_cursor=True,
                kernel="inline_literal",
            ),
        ),
        int(PrimitiveInstruction.BRANCH): _descriptor(
            PrimitiveInstruction.BRANCH,
            "BRANCH",
            InstructionCategory.DICTIONARY_COMPILER,
            "Read one inline branch offset from the current thread and continue there.",
            family=PRIMITIVE_INLINE_OPERAND_FAMILY,
            associated_data_source=AssociatedDataSource.INLINE_THREAD,
            requirements=_req(
                needs_thread_cursor=True,
                needs_thread_jump=True,
                kernel="inline_branch",
            ),
        ),
        int(PrimitiveInstruction.ZBRANCH): _descriptor(
            PrimitiveInstruction.ZBRANCH,
            "0BRANCH",
            InstructionCategory.DICTIONARY_COMPILER,
            "Read one inline branch offset and branch when the top of stack is zero.",
            family=PRIMITIVE_INLINE_OPERAND_FAMILY,
            associated_data_source=AssociatedDataSource.INLINE_THREAD,
            requirements=_req(
                min_data_stack_in=1,
                needs_thread_cursor=True,
                needs_thread_jump=True,
                kernel="inline_zero_branch",
            ),
        ),
        int(PrimitiveInstruction.LITSTRING): _descriptor(
            PrimitiveInstruction.LITSTRING,
            "LITSTRING",
            InstructionCategory.PARSER_IO,
            "Read inline string data from the current thread and push addr len.",
            family=PRIMITIVE_INLINE_OPERAND_FAMILY,
            associated_data_source=AssociatedDataSource.INLINE_THREAD,
            requirements=_req(
                min_data_stack_out_space=2,
                needs_thread_cursor=True,
                kernel="inline_string_literal",
            ),
        ),
        int(PrimitiveInstruction.DOCOL): _descriptor(
            PrimitiveInstruction.DOCOL,
            "DOCOL",
            InstructionCategory.DICTIONARY_COMPILER,
            "Enter the thread rooted at the current word's DFA.",
            family=COLON_THREAD_FAMILY,
            associated_data_source=AssociatedDataSource.WORD_LOCAL_DFA,
            requirements=_req(
                min_return_stack_out_space=1,
                needs_current_xt=True,
                needs_return_stack=True,
                needs_execution_control=True,
                kernel="enter_thread",
            ),
        ),
        int(PrimitiveInstruction.HALT): _descriptor(
            PrimitiveInstruction.HALT,
            "HALT",
            InstructionCategory.DICTIONARY_COMPILER,
            "Request that the current execution context halt.",
            requirements=_req(needs_execution_control=True, kernel="halt"),
        ),
    }
)

DEFAULT_INSTRUCTION_FAMILIES.register(
    int(PrimitiveInstruction.LIT),
    PRIMITIVE_INLINE_OPERAND_FAMILY,
)
DEFAULT_INSTRUCTION_FAMILIES.register_many(
    (
        int(PrimitiveInstruction.BRANCH),
        int(PrimitiveInstruction.ZBRANCH),
        int(PrimitiveInstruction.LITSTRING),
    ),
    PRIMITIVE_INLINE_OPERAND_FAMILY,
)
DEFAULT_INSTRUCTION_FAMILIES.register(
    int(PrimitiveInstruction.DOCOL),
    COLON_THREAD_FAMILY,
)


def instruction_descriptor_for_handler_id(
    handler_id: int,
    *,
    registry: InstructionRegistry | None = None,
) -> InstructionDescriptor | None:
    active_registry = DEFAULT_INSTRUCTIONS if registry is None else registry
    return active_registry.descriptor_for_handler_id(handler_id)


__all__ = [
    "AssociatedDataSource",
    "DEFAULT_INSTRUCTIONS",
    "HandlerRequirements",
    "InstructionCategory",
    "InstructionDescriptor",
    "InstructionRegistry",
    "PrimitiveInstruction",
    "instruction_descriptor_for_handler_id",
]
