"""Instruction metadata for organizing primitive words.

This module is intentionally separate from ``families.py``.

- families describe semantic/runtime behavior and payload interpretation
- instruction metadata describes organizational categories for browsing and grouping

The first pass only assigns categories to the approved ``primitive-empty`` instruction
set. Payload-bearing primitives and colon-thread instructions remain out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum

from .families import PRIMITIVE_EMPTY_FAMILY, WordFamily


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


@dataclass(frozen=True, slots=True)
class InstructionDescriptor:
    """Package metadata for a concrete instruction id."""

    instruction: int
    key: str
    family: WordFamily
    category: InstructionCategory
    description: str


class InstructionRegistry:
    """Maps concrete instruction ids to their package metadata."""

    def __init__(self, descriptors: dict[int, InstructionDescriptor] | None = None) -> None:
        self._descriptors: dict[int, InstructionDescriptor] = {}
        if descriptors is not None:
            for descriptor in descriptors.values():
                self.register(descriptor)

    def register(self, descriptor: InstructionDescriptor) -> None:
        self._descriptors[descriptor.instruction] = descriptor

    def descriptor_for_instruction(self, instruction: int) -> InstructionDescriptor | None:
        return self._descriptors.get(instruction)

    def snapshot(self) -> dict[int, InstructionDescriptor]:
        return dict(self._descriptors)


def _descriptor(
    instruction: PrimitiveInstruction,
    key: str,
    category: InstructionCategory,
    description: str,
) -> InstructionDescriptor:
    return InstructionDescriptor(
        instruction=int(instruction),
        key=key,
        family=PRIMITIVE_EMPTY_FAMILY,
        category=category,
        description=description,
    )


DEFAULT_INSTRUCTIONS = InstructionRegistry(
    descriptors={
        int(PrimitiveInstruction.DROP): _descriptor(PrimitiveInstruction.DROP, "DROP", InstructionCategory.STACK, "Drop top of data stack."),
        int(PrimitiveInstruction.SWAP): _descriptor(PrimitiveInstruction.SWAP, "SWAP", InstructionCategory.STACK, "Swap top two stack items."),
        int(PrimitiveInstruction.DUP): _descriptor(PrimitiveInstruction.DUP, "DUP", InstructionCategory.STACK, "Duplicate top stack item."),
        int(PrimitiveInstruction.OVER): _descriptor(PrimitiveInstruction.OVER, "OVER", InstructionCategory.STACK, "Copy second item to top of stack."),
        int(PrimitiveInstruction.ROT): _descriptor(PrimitiveInstruction.ROT, "ROT", InstructionCategory.STACK, "Rotate top three stack items."),
        int(PrimitiveInstruction.NROT): _descriptor(PrimitiveInstruction.NROT, "-ROT", InstructionCategory.STACK, "Reverse-rotate top three stack items."),
        int(PrimitiveInstruction.TWODROP): _descriptor(PrimitiveInstruction.TWODROP, "2DROP", InstructionCategory.STACK, "Drop top two stack items."),
        int(PrimitiveInstruction.TWODUP): _descriptor(PrimitiveInstruction.TWODUP, "2DUP", InstructionCategory.STACK, "Duplicate top two stack items."),
        int(PrimitiveInstruction.TWOSWAP): _descriptor(PrimitiveInstruction.TWOSWAP, "2SWAP", InstructionCategory.STACK, "Swap top two stack pairs."),
        int(PrimitiveInstruction.QDUP): _descriptor(PrimitiveInstruction.QDUP, "?DUP", InstructionCategory.STACK, "Duplicate top item if non-zero."),
        int(PrimitiveInstruction.INCR): _descriptor(PrimitiveInstruction.INCR, "1+", InstructionCategory.ARITHMETIC, "Increment top of stack."),
        int(PrimitiveInstruction.DECR): _descriptor(PrimitiveInstruction.DECR, "1-", InstructionCategory.ARITHMETIC, "Decrement top of stack."),
        int(PrimitiveInstruction.INCR4): _descriptor(PrimitiveInstruction.INCR4, "4+", InstructionCategory.ARITHMETIC, "Add one cell to top of stack."),
        int(PrimitiveInstruction.DECR4): _descriptor(PrimitiveInstruction.DECR4, "4-", InstructionCategory.ARITHMETIC, "Subtract one cell from top of stack."),
        int(PrimitiveInstruction.ADD): _descriptor(PrimitiveInstruction.ADD, "+", InstructionCategory.ARITHMETIC, "Add top two stack items."),
        int(PrimitiveInstruction.SUB): _descriptor(PrimitiveInstruction.SUB, "-", InstructionCategory.ARITHMETIC, "Subtract top item from next item."),
        int(PrimitiveInstruction.MUL): _descriptor(PrimitiveInstruction.MUL, "*", InstructionCategory.ARITHMETIC, "Multiply top two stack items."),
        int(PrimitiveInstruction.DIVMOD): _descriptor(PrimitiveInstruction.DIVMOD, "/MOD", InstructionCategory.ARITHMETIC, "Compute quotient and remainder."),
        int(PrimitiveInstruction.EQU): _descriptor(PrimitiveInstruction.EQU, "=", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items for equality."),
        int(PrimitiveInstruction.NEQU): _descriptor(PrimitiveInstruction.NEQU, "<>", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items for inequality."),
        int(PrimitiveInstruction.LT): _descriptor(PrimitiveInstruction.LT, "<", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with less-than."),
        int(PrimitiveInstruction.GT): _descriptor(PrimitiveInstruction.GT, ">", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with greater-than."),
        int(PrimitiveInstruction.LE): _descriptor(PrimitiveInstruction.LE, "<=", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with less-or-equal."),
        int(PrimitiveInstruction.GE): _descriptor(PrimitiveInstruction.GE, ">=", InstructionCategory.COMPARISON_BITWISE, "Compare top two stack items with greater-or-equal."),
        int(PrimitiveInstruction.ZEQU): _descriptor(PrimitiveInstruction.ZEQU, "0=", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for zero."),
        int(PrimitiveInstruction.ZNEQU): _descriptor(PrimitiveInstruction.ZNEQU, "0<>", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for non-zero."),
        int(PrimitiveInstruction.ZLT): _descriptor(PrimitiveInstruction.ZLT, "0<", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for negative."),
        int(PrimitiveInstruction.ZGT): _descriptor(PrimitiveInstruction.ZGT, "0>", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for positive."),
        int(PrimitiveInstruction.ZLE): _descriptor(PrimitiveInstruction.ZLE, "0<=", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for non-positive."),
        int(PrimitiveInstruction.ZGE): _descriptor(PrimitiveInstruction.ZGE, "0>=", InstructionCategory.COMPARISON_BITWISE, "Test top of stack for non-negative."),
        int(PrimitiveInstruction.AND): _descriptor(PrimitiveInstruction.AND, "AND", InstructionCategory.COMPARISON_BITWISE, "Bitwise and on top two stack items."),
        int(PrimitiveInstruction.OR): _descriptor(PrimitiveInstruction.OR, "OR", InstructionCategory.COMPARISON_BITWISE, "Bitwise or on top two stack items."),
        int(PrimitiveInstruction.XOR): _descriptor(PrimitiveInstruction.XOR, "XOR", InstructionCategory.COMPARISON_BITWISE, "Bitwise xor on top two stack items."),
        int(PrimitiveInstruction.INVERT): _descriptor(PrimitiveInstruction.INVERT, "INVERT", InstructionCategory.COMPARISON_BITWISE, "Bitwise invert top of stack."),
        int(PrimitiveInstruction.EXIT): _descriptor(PrimitiveInstruction.EXIT, "EXIT", InstructionCategory.DICTIONARY_COMPILER, "Return from the current threaded word."),
        int(PrimitiveInstruction.STORE): _descriptor(PrimitiveInstruction.STORE, "!", InstructionCategory.MEMORY, "Store a cell through an address."),
        int(PrimitiveInstruction.FETCH): _descriptor(PrimitiveInstruction.FETCH, "@", InstructionCategory.MEMORY, "Fetch a cell through an address."),
        int(PrimitiveInstruction.ADDSTORE): _descriptor(PrimitiveInstruction.ADDSTORE, "+!", InstructionCategory.MEMORY, "Add to a cell through an address."),
        int(PrimitiveInstruction.SUBSTORE): _descriptor(PrimitiveInstruction.SUBSTORE, "-!", InstructionCategory.MEMORY, "Subtract from a cell through an address."),
        int(PrimitiveInstruction.STOREBYTE): _descriptor(PrimitiveInstruction.STOREBYTE, "C!", InstructionCategory.MEMORY, "Store a byte through an address."),
        int(PrimitiveInstruction.FETCHBYTE): _descriptor(PrimitiveInstruction.FETCHBYTE, "C@", InstructionCategory.MEMORY, "Fetch a byte through an address."),
        int(PrimitiveInstruction.CCOPY): _descriptor(PrimitiveInstruction.CCOPY, "C@C!", InstructionCategory.MEMORY, "Copy one byte from source address to destination."),
        int(PrimitiveInstruction.CMOVE): _descriptor(PrimitiveInstruction.CMOVE, "CMOVE", InstructionCategory.MEMORY, "Copy a byte range in memory."),
        int(PrimitiveInstruction.TOR): _descriptor(PrimitiveInstruction.TOR, ">R", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Move top of data stack to return stack."),
        int(PrimitiveInstruction.FROMR): _descriptor(PrimitiveInstruction.FROMR, "R>", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Move top of return stack to data stack."),
        int(PrimitiveInstruction.RSPFETCH): _descriptor(PrimitiveInstruction.RSPFETCH, "RSP@", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Fetch return-stack pointer."),
        int(PrimitiveInstruction.RSPSTORE): _descriptor(PrimitiveInstruction.RSPSTORE, "RSP!", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Store return-stack pointer."),
        int(PrimitiveInstruction.RDROP): _descriptor(PrimitiveInstruction.RDROP, "RDROP", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Drop top of return stack."),
        int(PrimitiveInstruction.DSPFETCH): _descriptor(PrimitiveInstruction.DSPFETCH, "DSP@", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Fetch data-stack pointer."),
        int(PrimitiveInstruction.DSPSTORE): _descriptor(PrimitiveInstruction.DSPSTORE, "DSP!", InstructionCategory.RETURN_DATA_STACK_CONTROL, "Store data-stack pointer."),
        int(PrimitiveInstruction.KEY): _descriptor(PrimitiveInstruction.KEY, "KEY", InstructionCategory.PARSER_IO, "Read one input character."),
        int(PrimitiveInstruction.EMIT): _descriptor(PrimitiveInstruction.EMIT, "EMIT", InstructionCategory.PARSER_IO, "Write one output character."),
        int(PrimitiveInstruction.WORD): _descriptor(PrimitiveInstruction.WORD, "WORD", InstructionCategory.PARSER_IO, "Parse the next token from input."),
        int(PrimitiveInstruction.NUMBER): _descriptor(PrimitiveInstruction.NUMBER, "NUMBER", InstructionCategory.PARSER_IO, "Convert a parsed token to a number."),
        int(PrimitiveInstruction.FIND): _descriptor(PrimitiveInstruction.FIND, "FIND", InstructionCategory.DICTIONARY_COMPILER, "Look up a word name in the dictionary."),
        int(PrimitiveInstruction.TCFA): _descriptor(PrimitiveInstruction.TCFA, ">CFA", InstructionCategory.DICTIONARY_COMPILER, "Recover the code-field address from a dictionary header."),
        int(PrimitiveInstruction.CREATE): _descriptor(PrimitiveInstruction.CREATE, "CREATE", InstructionCategory.DICTIONARY_COMPILER, "Create and link a new dictionary entry."),
        int(PrimitiveInstruction.COMMA): _descriptor(PrimitiveInstruction.COMMA, ",", InstructionCategory.DICTIONARY_COMPILER, "Append one cell to the current definition."),
        int(PrimitiveInstruction.LBRAC): _descriptor(PrimitiveInstruction.LBRAC, "[", InstructionCategory.DICTIONARY_COMPILER, "Switch compiler state to interpret mode."),
        int(PrimitiveInstruction.RBRAC): _descriptor(PrimitiveInstruction.RBRAC, "]", InstructionCategory.DICTIONARY_COMPILER, "Switch compiler state to compile mode."),
        int(PrimitiveInstruction.IMMEDIATE): _descriptor(PrimitiveInstruction.IMMEDIATE, "IMMEDIATE", InstructionCategory.DICTIONARY_COMPILER, "Mark the latest word immediate."),
        int(PrimitiveInstruction.HIDDEN): _descriptor(PrimitiveInstruction.HIDDEN, "HIDDEN", InstructionCategory.DICTIONARY_COMPILER, "Toggle hidden metadata on a word."),
        int(PrimitiveInstruction.TICK): _descriptor(PrimitiveInstruction.TICK, "'", InstructionCategory.DICTIONARY_COMPILER, "Parse a name and return its xt."),
        int(PrimitiveInstruction.TELL): _descriptor(PrimitiveInstruction.TELL, "TELL", InstructionCategory.PARSER_IO, "Write a counted or addressed string."),
        int(PrimitiveInstruction.INTERPRET): _descriptor(PrimitiveInstruction.INTERPRET, "INTERPRET", InstructionCategory.DICTIONARY_COMPILER, "Run the outer interpreter loop core."),
        int(PrimitiveInstruction.CHAR): _descriptor(PrimitiveInstruction.CHAR, "CHAR", InstructionCategory.PARSER_IO, "Parse one character token."),
        int(PrimitiveInstruction.EXECUTE): _descriptor(PrimitiveInstruction.EXECUTE, "EXECUTE", InstructionCategory.DICTIONARY_COMPILER, "Execute a word by xt."),
        int(PrimitiveInstruction.SYSCALL3): _descriptor(PrimitiveInstruction.SYSCALL3, "SYSCALL3", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with three arguments."),
        int(PrimitiveInstruction.SYSCALL2): _descriptor(PrimitiveInstruction.SYSCALL2, "SYSCALL2", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with two arguments."),
        int(PrimitiveInstruction.SYSCALL1): _descriptor(PrimitiveInstruction.SYSCALL1, "SYSCALL1", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with one argument."),
        int(PrimitiveInstruction.SYSCALL0): _descriptor(PrimitiveInstruction.SYSCALL0, "SYSCALL0", InstructionCategory.HOST_BRIDGE, "Invoke a host syscall with no arguments."),
    }
)


def instruction_descriptor_for(
    instruction: int,
    *,
    registry: InstructionRegistry | None = None,
) -> InstructionDescriptor | None:
    active_registry = DEFAULT_INSTRUCTIONS if registry is None else registry
    return active_registry.descriptor_for_instruction(instruction)


__all__ = [
    "DEFAULT_INSTRUCTIONS",
    "InstructionCategory",
    "InstructionDescriptor",
    "InstructionRegistry",
    "PrimitiveInstruction",
    "instruction_descriptor_for",
]
