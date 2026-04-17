"""Demonstrate a tiny Python interpreter loop driven by handler metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, TypeAlias

from fythvm import dictionary


HandlerFn = Callable[..., str]
CompilerWordHandlerFn = Callable[..., str]


@dataclass(frozen=True)
class Scenario:
    name: str
    text: str
    thread: tuple[int, ...] | None
    expected_decompile: tuple[str, ...]
    expected_stack: tuple[StackValue, ...]
    expected_halted: bool
    expected_final_ip: int
    expected_error_code: str | None
    expected_trace_words: tuple[str, ...]
    compile_source: str | None = None
    expected_compiled_thread: tuple[int, ...] | None = None
    custom_words: tuple["WordSpec", ...] = ()


@dataclass(frozen=True)
class TraceRow:
    step: int
    ip: int
    word: str
    family: str
    associated_data_source: str
    kernel: str | None
    injected_names: tuple[str, ...]
    stack_before: tuple[StackValue, ...]
    stack_after: tuple[StackValue, ...]
    note: str
    next_ip: int | None
    halted: bool


@dataclass(frozen=True)
class ScenarioResult:
    compiled_thread: tuple[int, ...]
    decompiled_thread: tuple[str, ...]
    final_stack: tuple[StackValue, ...]
    halted: bool
    final_ip: int
    error_code: str | None
    error_detail: str | None
    trace: tuple[TraceRow, ...]


@dataclass(frozen=True)
class WordSpec:
    xt: int
    name: str
    handler_id: int
    thread: tuple[int, ...] | None = None


@dataclass(frozen=True)
class ReturnFrame:
    thread_name: str
    thread: tuple[int, ...]
    return_ip: int


@dataclass(frozen=True)
class CountedPayload:
    """Opaque counted byte payload with no C-string semantics."""

    octets: bytes

    @property
    def length(self) -> int:
        return len(self.octets)


@dataclass(frozen=True)
class InlineStringRef:
    """Pointer-like inline payload view without exposing raw thread offsets."""

    payload: CountedPayload


StackValue: TypeAlias = int | InlineStringRef


@dataclass
class LoopState:
    """Minimal execution state for the proof-of-concept loop."""

    current_thread: tuple[int, ...]
    current_thread_name: str = "entry"
    stack_limit: int = 8
    ip: int = 0
    current_xt: int | None = None
    data_stack: list[StackValue] = field(default_factory=list)
    return_stack: list[ReturnFrame] = field(default_factory=list)
    halted: bool = False


class ExecutionFault(RuntimeError):
    """Lab-local execution failure with a stable status code."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def error_exit(code: str, detail: str) -> None:
    raise ExecutionFault(code, detail)


def stack_depth(data_stack: list[StackValue]) -> int:
    """Return the current logical stack depth."""

    return len(data_stack)


def stack_push(data_stack: list[StackValue], value: StackValue) -> None:
    """Push one value through the current stack abstraction."""

    data_stack.append(value)


def stack_pop(data_stack: list[StackValue]) -> StackValue:
    """Pop one value through the current stack abstraction."""

    return data_stack.pop()


def stack_peek(data_stack: list[StackValue], depth: int = 0) -> StackValue:
    """Read one value from the logical top window without consuming it."""

    return data_stack[-(depth + 1)]


def binary_reduce(data_stack: list[StackValue], fn: Callable[[int, int], int]) -> int:
    """Local stack-shape kernel: reduce two inputs into one output."""

    rhs = stack_pop(data_stack)
    lhs = stack_pop(data_stack)
    if not isinstance(lhs, int) or not isinstance(rhs, int):
        raise TypeError("binary_reduce expects integer stack cells")
    result = fn(lhs, rhs)
    stack_push(data_stack, result)
    return result


def pack_inline_payload(payload: CountedPayload) -> tuple[int, ...]:
    """Pack a counted payload into 32-bit little-endian thread cells."""

    if not payload.octets:
        return ()

    cells: list[int] = []
    for start in range(0, payload.length, 4):
        chunk = payload.octets[start : start + 4]
        padded = chunk.ljust(4, b"\x00")
        cells.append(int.from_bytes(padded, byteorder="little", signed=False))
    return tuple(cells)


def unpack_inline_payload(*, thread: tuple[int, ...], start: int, length: int) -> CountedPayload:
    """Decode one counted inline payload from packed 32-bit thread cells."""

    cell_count = litstring_payload_cells(length)
    payload_cells = thread[start : start + cell_count]
    raw = b"".join(int(cell).to_bytes(4, byteorder="little", signed=False) for cell in payload_cells)
    return CountedPayload(octets=raw[:length])


@dataclass
class ThreadCursor:
    """Thread-local operand access without handing the handler raw dispatch control."""

    state: LoopState

    def read_inline_cell(self) -> int:
        operand_ip = self.state.ip + 1
        if operand_ip >= len(self.state.current_thread):
            error_exit(
                "inline-operand-underflow",
                f"word at ip={self.state.ip} needs one inline cell",
            )
        literal = int(self.state.current_thread[operand_ip])
        self.state.ip = operand_ip
        return literal

    def read_counted_payload(self) -> CountedPayload:
        """Read one Forth-style counted inline payload."""

        length_ip = self.state.ip + 1
        if length_ip >= len(self.state.current_thread):
            error_exit(
                "inline-operand-underflow",
                f"word at ip={self.state.ip} needs one inline length cell",
            )

        length = int(self.state.current_thread[length_ip])
        payload_start = length_ip + 1
        payload_cells = litstring_payload_cells(length)
        payload_end = payload_start + payload_cells
        if payload_end > len(self.state.current_thread):
            error_exit(
                "inline-operand-underflow",
                (
                    f"word at ip={self.state.ip} needs {payload_cells} payload cells "
                    f"for counted length {length}"
                ),
            )

        payload = unpack_inline_payload(
            thread=self.state.current_thread,
            start=payload_start,
            length=length,
        )
        self.state.ip = payload_end - 1
        return payload


@dataclass
class ThreadJump:
    """Control helper for relative thread redirection."""

    state: LoopState

    def branch_relative(self, offset: int) -> None:
        self.state.ip += offset


@dataclass
class ExecutionControl:
    """Minimal local control hooks that stop short of owning dispatch policy."""

    state: LoopState

    def halt(self) -> None:
        self.state.halted = True

    def enter_thread(self, *, thread_name: str, thread: tuple[int, ...]) -> None:
        self.state.return_stack.append(
            ReturnFrame(
                thread_name=self.state.current_thread_name,
                thread=self.state.current_thread,
                return_ip=self.state.ip + 1,
            )
        )
        self.state.current_thread_name = thread_name
        self.state.current_thread = thread
        self.state.ip = -1

    def return_from_thread(self) -> str:
        if not self.state.return_stack:
            self.halt()
            return "halt"
        frame = self.state.return_stack.pop()
        self.state.current_thread_name = frame.thread_name
        self.state.current_thread = frame.thread
        self.state.ip = frame.return_ip - 1
        return f"return to {frame.thread_name} ip {frame.return_ip}"


@dataclass
class CurrentWordThread:
    """Abstract current-word payload view for colon-thread words."""

    state: LoopState
    word_registry: dict[int, WordSpec]

    def word_name(self) -> str:
        xt = self.state.current_xt
        if xt is None or xt not in self.word_registry:
            error_exit("unknown-word", "current_xt does not resolve to a word spec")
        return self.word_registry[xt].name

    def thread(self) -> tuple[int, ...]:
        xt = self.state.current_xt
        if xt is None or xt not in self.word_registry:
            error_exit("unknown-word", "current_xt does not resolve to a word spec")
        word = self.word_registry[xt]
        if word.thread is None:
            error_exit("no-word-thread", f"{word.name} does not carry a thread payload")
        return word.thread


@dataclass
class SourceCursor:
    """Structured compile-time parser state for the lab."""

    source: str
    position: int = 0

    def skip_whitespace(self) -> None:
        while self.position < len(self.source) and self.source[self.position].isspace():
            self.position += 1

    def at_end(self) -> bool:
        self.skip_whitespace()
        return self.position >= len(self.source)

    def read_token(self) -> str:
        self.skip_whitespace()
        if self.position >= len(self.source):
            error_exit("compile-parse-error", "expected another token")

        end = self.position
        while end < len(self.source) and not self.source[end].isspace():
            end += 1
        token = self.source[self.position:end]
        self.position = end
        return token

    def read_until_quote(self) -> CountedPayload:
        self.skip_whitespace()
        end = self.source.find('"', self.position)
        if end == -1:
            error_exit("compile-parse-error", 'unterminated S" string literal')
        payload = CountedPayload(octets=self.source[self.position:end].encode("ascii"))
        self.position = end + 1
        return payload


@dataclass
class ThreadEmitter:
    """Capability wrapper over compile-time thread emission."""

    emitted: list[int] = field(default_factory=list)

    def emit_cell(self, value: int) -> None:
        self.emitted.append(int(value))

    def emit_cells(self, values: tuple[int, ...] | list[int]) -> None:
        for value in values:
            self.emit_cell(int(value))

    def emit_packed_payload(self, payload: CountedPayload) -> None:
        self.emit_cells(pack_inline_payload(payload))

    def reserve_cell(self) -> int:
        self.emit_cell(0)
        return len(self.emitted) - 1

    def patch_cell(self, index: int, value: int) -> None:
        self.emitted[index] = int(value)

    def finish(self) -> tuple[int, ...]:
        return tuple(self.emitted)


@dataclass
class PatchStack:
    """Small patch-slot stack for compile-time control words."""

    slots: list[int] = field(default_factory=list)

    def push(self, index: int) -> None:
        self.slots.append(index)

    def pop(self) -> int:
        if not self.slots:
            error_exit("compile-parse-error", "THEN has no matching IF")
        return self.slots.pop()


def handle_lit(
    *,
    data_stack: list[StackValue],
    thread_cursor: ThreadCursor,
    err: Callable[[str, str], None],
) -> str:
    _ = err
    literal = thread_cursor.read_inline_cell()
    stack_push(data_stack, literal)
    return f"push literal {literal}"


def handle_litstring(
    *,
    data_stack: list[StackValue],
    thread_cursor: ThreadCursor,
    err: Callable[[str, str], None],
) -> str:
    _ = err
    payload = thread_cursor.read_counted_payload()
    string_ref = InlineStringRef(payload=payload)
    stack_push(data_stack, string_ref)
    stack_push(data_stack, payload.length)
    return f"push counted payload {payload.octets!r} len {payload.length}"


def handle_add(*, data_stack: list[StackValue], err: Callable[[str, str], None]) -> str:
    if stack_depth(data_stack) < 2:
        err("stack-underflow", "ADD needs two cells")
    lhs = stack_peek(data_stack, depth=1)
    rhs = stack_peek(data_stack, depth=0)
    result = binary_reduce(data_stack, lambda left, right: left + right)
    return f"{lhs} + {rhs} -> {result}"


def handle_branch(*, thread_cursor: ThreadCursor, thread_jump: ThreadJump, err: Callable[[str, str], None]) -> str:
    _ = err
    offset = thread_cursor.read_inline_cell()
    thread_jump.branch_relative(offset)
    return f"branch relative {offset}"


def handle_zero_branch(
    *,
    data_stack: list[int],
    thread_cursor: ThreadCursor,
    thread_jump: ThreadJump,
    err: Callable[[str, str], None],
) -> str:
    if stack_depth(data_stack) < 1:
        err("stack-underflow", "0BRANCH needs one condition cell")
    offset = thread_cursor.read_inline_cell()
    flag = stack_pop(data_stack)
    if flag == 0:
        thread_jump.branch_relative(offset)
        return f"branch relative {offset} because flag == 0"
    return f"fall through because flag != 0 ({flag})"


def handle_docol(
    *,
    current_word_thread: CurrentWordThread,
    control: ExecutionControl,
    err: Callable[[str, str], None],
) -> str:
    _ = err
    child_name = current_word_thread.word_name()
    control.enter_thread(thread_name=child_name, thread=current_word_thread.thread())
    return f"enter {child_name}"


def handle_exit(*, control: ExecutionControl, err: Callable[[str, str], None]) -> str:
    _ = err
    return control.return_from_thread()


def handle_s_quote(
    *,
    source_cursor: SourceCursor,
    thread_emitter: ThreadEmitter,
    err: Callable[[str, str], None],
) -> str:
    _ = err
    payload = source_cursor.read_until_quote()
    thread_emitter.emit_cell(int(dictionary.PrimitiveInstruction.LITSTRING))
    thread_emitter.emit_cell(payload.length)
    thread_emitter.emit_packed_payload(payload)
    return f'emit S" counted payload {payload.octets!r}'


def handle_if(
    *,
    thread_emitter: ThreadEmitter,
    patch_stack: PatchStack,
    err: Callable[[str, str], None],
) -> str:
    _ = err
    thread_emitter.emit_cell(int(dictionary.PrimitiveInstruction.ZBRANCH))
    operand_index = thread_emitter.reserve_cell()
    patch_stack.push(operand_index)
    return f"emit IF placeholder at {operand_index}"


def handle_then(
    *,
    thread_emitter: ThreadEmitter,
    patch_stack: PatchStack,
    err: Callable[[str, str], None],
) -> str:
    _ = err
    operand_index = patch_stack.pop()
    offset = len(thread_emitter.emitted) - operand_index - 1
    thread_emitter.patch_cell(operand_index, offset)
    return f"patch THEN placeholder at {operand_index} with {offset}"


HANDLERS: dict[int, HandlerFn] = {
    int(dictionary.PrimitiveInstruction.LIT): handle_lit,
    int(dictionary.PrimitiveInstruction.LITSTRING): handle_litstring,
    int(dictionary.PrimitiveInstruction.ADD): handle_add,
    int(dictionary.PrimitiveInstruction.BRANCH): handle_branch,
    int(dictionary.PrimitiveInstruction.ZBRANCH): handle_zero_branch,
    int(dictionary.PrimitiveInstruction.DOCOL): handle_docol,
    int(dictionary.PrimitiveInstruction.EXIT): handle_exit,
}


COMPILER_WORD_HANDLERS: dict[str, CompilerWordHandlerFn] = {
    'S"': handle_s_quote,
    "IF": handle_if,
    "THEN": handle_then,
}


SCENARIOS = (
    Scenario(
        name="success",
        text="LIT 2 LIT 3 + EXIT",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            3,
            int(dictionary.PrimitiveInstruction.ADD),
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LIT 2",
            "  2: LIT 3",
            "  4: +",
            "  5: EXIT",
        ),
        expected_stack=(5,),
        expected_halted=True,
        expected_final_ip=5,
        expected_error_code=None,
        expected_trace_words=("LIT", "LIT", "+", "EXIT"),
    ),
    Scenario(
        name="underflow",
        text="LIT 2 + EXIT",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            2,
            int(dictionary.PrimitiveInstruction.ADD),
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LIT 2",
            "  2: +",
            "  3: EXIT",
        ),
        expected_stack=(2,),
        expected_halted=False,
        expected_final_ip=2,
        expected_error_code="stack-underflow",
        expected_trace_words=("LIT",),
    ),
    Scenario(
        name="litstring",
        text='LITSTRING "hi" EXIT',
        thread=(
            int(dictionary.PrimitiveInstruction.LITSTRING),
            2,
            *pack_inline_payload(CountedPayload(octets=b"hi")),
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LITSTRING b'hi'",
            "  3: EXIT",
        ),
        expected_stack=(InlineStringRef(payload=CountedPayload(octets=b"hi")), 2),
        expected_halted=True,
        expected_final_ip=3,
        expected_error_code=None,
        expected_trace_words=("LITSTRING", "EXIT"),
    ),
    Scenario(
        name="compile-s-quote",
        text='compile S" hi" EXIT',
        thread=None,
        compile_source='S" hi" EXIT',
        expected_compiled_thread=(
            int(dictionary.PrimitiveInstruction.LITSTRING),
            2,
            *pack_inline_payload(CountedPayload(octets=b"hi")),
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LITSTRING b'hi'",
            "  3: EXIT",
        ),
        expected_stack=(InlineStringRef(payload=CountedPayload(octets=b"hi")), 2),
        expected_halted=True,
        expected_final_ip=3,
        expected_error_code=None,
        expected_trace_words=("LITSTRING", "EXIT"),
    ),
    Scenario(
        name="compile-s-quote-long",
        text='compile S" hello" EXIT',
        thread=None,
        compile_source='S" hello" EXIT',
        expected_compiled_thread=(
            int(dictionary.PrimitiveInstruction.LITSTRING),
            5,
            *pack_inline_payload(CountedPayload(octets=b"hello")),
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LITSTRING b'hello'",
            "  4: EXIT",
        ),
        expected_stack=(InlineStringRef(payload=CountedPayload(octets=b"hello")), 5),
        expected_halted=True,
        expected_final_ip=4,
        expected_error_code=None,
        expected_trace_words=("LITSTRING", "EXIT"),
    ),
    Scenario(
        name="branch-skip",
        text="LIT 7 BRANCH 2 LIT 999 EXIT",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            7,
            int(dictionary.PrimitiveInstruction.BRANCH),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            999,
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LIT 7",
            "  2: BRANCH 2",
            "  4: LIT 999",
            "  6: EXIT",
        ),
        expected_stack=(7,),
        expected_halted=True,
        expected_final_ip=6,
        expected_error_code=None,
        expected_trace_words=("LIT", "BRANCH", "EXIT"),
    ),
    Scenario(
        name="zero-branch-taken",
        text="LIT 0 0BRANCH 2 LIT 999 EXIT",
        thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            0,
            int(dictionary.PrimitiveInstruction.ZBRANCH),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            999,
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LIT 0",
            "  2: 0BRANCH 2",
            "  4: LIT 999",
            "  6: EXIT",
        ),
        expected_stack=(),
        expected_halted=True,
        expected_final_ip=6,
        expected_error_code=None,
        expected_trace_words=("LIT", "0BRANCH", "EXIT"),
    ),
    Scenario(
        name="compile-if-then",
        text="compile LIT 0 IF LIT 999 THEN EXIT",
        thread=None,
        compile_source="LIT 0 IF LIT 999 THEN EXIT",
        expected_compiled_thread=(
            int(dictionary.PrimitiveInstruction.LIT),
            0,
            int(dictionary.PrimitiveInstruction.ZBRANCH),
            2,
            int(dictionary.PrimitiveInstruction.LIT),
            999,
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: LIT 0",
            "  2: 0BRANCH 2",
            "  4: LIT 999",
            "  6: EXIT",
        ),
        expected_stack=(),
        expected_halted=True,
        expected_final_ip=6,
        expected_error_code=None,
        expected_trace_words=("LIT", "0BRANCH", "EXIT"),
    ),
    Scenario(
        name="compile-s-quote-unterminated",
        text='compile S" hi',
        thread=None,
        compile_source='S" hi',
        expected_decompile=(),
        expected_stack=(),
        expected_halted=False,
        expected_final_ip=0,
        expected_error_code="compile-parse-error",
        expected_trace_words=(),
    ),
    Scenario(
        name="compile-then-without-if",
        text="compile THEN EXIT",
        thread=None,
        compile_source="THEN EXIT",
        expected_decompile=(),
        expected_stack=(),
        expected_halted=False,
        expected_final_ip=0,
        expected_error_code="compile-parse-error",
        expected_trace_words=(),
    ),
    Scenario(
        name="compile-if-without-then",
        text="compile LIT 0 IF EXIT",
        thread=None,
        compile_source="LIT 0 IF EXIT",
        expected_decompile=(),
        expected_stack=(),
        expected_halted=False,
        expected_final_ip=0,
        expected_error_code="compile-parse-error",
        expected_trace_words=(),
    ),
    Scenario(
        name="docol-call",
        text="SUM23 EXIT  with SUM23 := LIT 2 LIT 3 + EXIT",
        thread=(
            1000,
            int(dictionary.PrimitiveInstruction.EXIT),
        ),
        expected_decompile=(
            "entry:",
            "  0: SUM23",
            "  1: EXIT",
            "word SUM23:",
            "  0: LIT 2",
            "  2: LIT 3",
            "  4: +",
            "  5: EXIT",
        ),
        expected_stack=(5,),
        expected_halted=True,
        expected_final_ip=1,
        expected_error_code=None,
        expected_trace_words=("SUM23", "LIT", "LIT", "+", "EXIT", "EXIT"),
        custom_words=(
            WordSpec(
                xt=1000,
                name="SUM23",
                handler_id=int(dictionary.PrimitiveInstruction.DOCOL),
                thread=(
                    int(dictionary.PrimitiveInstruction.LIT),
                    2,
                    int(dictionary.PrimitiveInstruction.LIT),
                    3,
                    int(dictionary.PrimitiveInstruction.ADD),
                    int(dictionary.PrimitiveInstruction.EXIT),
                ),
            ),
        ),
    ),
)


def build_word_registry(scenario: Scenario) -> dict[int, WordSpec]:
    """Build one scenario-local word registry from package descriptors and custom words."""

    registry: dict[int, WordSpec] = {}
    for primitive in dictionary.PrimitiveInstruction:
        descriptor = dictionary.instruction_descriptor_for_handler_id(int(primitive))
        if descriptor is None:
            continue
        registry[int(primitive)] = WordSpec(
            xt=int(primitive),
            name=descriptor.key,
            handler_id=int(primitive),
        )
    for word in scenario.custom_words:
        registry[word.xt] = word
    return registry


def resolve_entry_thread(scenario: Scenario) -> tuple[int, ...]:
    """Resolve one scenario entry thread, optionally through the tiny compiler."""

    if scenario.compile_source is not None:
        return compile_source_to_thread(scenario.compile_source)
    if scenario.thread is None:
        error_exit("scenario-shape-error", f"{scenario.name} has neither thread nor compile source")
    return scenario.thread


def litstring_payload_cells(length: int) -> int:
    """Return how many 32-bit cells are needed for one inline string payload."""

    return (length + 3) // 4


def injected_compile_resources(
    descriptor: dictionary.CompilerWordDescriptor,
    *,
    source_cursor: SourceCursor,
    thread_emitter: ThreadEmitter,
    patch_stack: PatchStack,
) -> dict[str, object]:
    """Build the compile-time capability set for one compiler word."""

    req = descriptor.requirements
    kwargs: dict[str, object] = {}

    if req.needs_source_cursor:
        kwargs["source_cursor"] = source_cursor
    if req.needs_thread_emitter:
        kwargs["thread_emitter"] = thread_emitter
    if req.needs_patch_stack:
        kwargs["patch_stack"] = patch_stack
    if req.needs_error_exit:
        kwargs["err"] = error_exit
    return kwargs


def compile_source_to_thread(source: str) -> tuple[int, ...]:
    """Compile a tiny source language into one entry thread."""

    source_cursor = SourceCursor(source)
    thread_emitter = ThreadEmitter()
    patch_stack = PatchStack()

    while not source_cursor.at_end():
        token = source_cursor.read_token()
        compiler_descriptor = dictionary.compiler_word_descriptor_for_key(token)
        if compiler_descriptor is not None:
            handler = COMPILER_WORD_HANDLERS.get(token)
            if handler is None:
                error_exit("missing-compiler-handler", f"no compiler handler wired for {token}")
            kwargs = injected_compile_resources(
                compiler_descriptor,
                source_cursor=source_cursor,
                thread_emitter=thread_emitter,
                patch_stack=patch_stack,
            )
            handler(**kwargs)
            continue

        if token == "LIT":
            literal_token = source_cursor.read_token()
            thread_emitter.emit_cell(int(dictionary.PrimitiveInstruction.LIT))
            thread_emitter.emit_cell(int(literal_token))
            continue
        if token == "+":
            thread_emitter.emit_cell(int(dictionary.PrimitiveInstruction.ADD))
            continue
        if token == "EXIT":
            thread_emitter.emit_cell(int(dictionary.PrimitiveInstruction.EXIT))
            continue

        error_exit("compile-parse-error", f"unknown compile token {token!r}")

    if patch_stack.slots:
        error_exit("compile-parse-error", "IF without matching THEN")

    return thread_emitter.finish()


def decompile_linear_thread(
    *,
    label: str,
    thread: tuple[int, ...],
    word_registry: dict[int, WordSpec],
) -> tuple[str, ...]:
    """Render one linear thread into human-readable instruction rows."""

    lines: list[str] = [f"{label}:"]
    ip = 0

    while ip < len(thread):
        xt = int(thread[ip])
        word = word_registry.get(xt)
        if word is None:
            lines.append(f"  {ip}: <unknown {xt}>")
            ip += 1
            continue
        descriptor = dictionary.instruction_descriptor_for_handler_id(word.handler_id)
        if descriptor is None:
            lines.append(f"  {ip}: <unknown-handler {word.handler_id}>")
            ip += 1
            continue

        key = word.name
        if key in {"LIT", "BRANCH", "0BRANCH"}:
            operand_ip = ip + 1
            if operand_ip >= len(thread):
                lines.append(f"  {ip}: {key} <missing-inline-cell>")
                break
            operand = int(thread[operand_ip])
            lines.append(f"  {ip}: {key} {operand}")
            ip = operand_ip + 1
            continue

        if key == "LITSTRING":
            length_ip = ip + 1
            if length_ip >= len(thread):
                lines.append(f"  {ip}: LITSTRING <missing-length>")
                break
            length = int(thread[length_ip])
            payload_start = length_ip + 1
            payload_end = payload_start + litstring_payload_cells(length)
            if payload_end > len(thread):
                lines.append(f"  {ip}: LITSTRING len={length} <missing-payload>")
                break
            payload = unpack_inline_payload(thread=thread, start=payload_start, length=length)
            lines.append(f"  {ip}: LITSTRING {payload.octets!r}")
            ip = payload_end
            continue

        lines.append(f"  {ip}: {key}")
        ip += 1

    return tuple(lines)


def decompile_program(
    scenario: Scenario,
    word_registry: dict[int, WordSpec],
) -> tuple[str, ...]:
    """Render the entry thread plus any custom threaded words."""

    lines: list[str] = list(
        decompile_linear_thread(label="entry", thread=scenario.thread, word_registry=word_registry)
    )
    for word in scenario.custom_words:
        if word.thread is None:
            continue
        lines.extend(
            decompile_linear_thread(
                label=f"word {word.name}",
                thread=word.thread,
                word_registry=word_registry,
            )
        )
    return tuple(lines)


def injected_resources(
    descriptor: dictionary.InstructionDescriptor,
    state: LoopState,
    *,
    word_registry: dict[int, WordSpec],
) -> dict[str, object]:
    """Build the concrete injected argument set from metadata."""

    req = descriptor.requirements
    kwargs: dict[str, object] = {}

    if req.min_data_stack_in > 0 or req.min_data_stack_out_space > 0:
        kwargs["data_stack"] = state.data_stack
    if req.needs_thread_cursor:
        kwargs["thread_cursor"] = ThreadCursor(state)
    if req.needs_thread_jump:
        kwargs["thread_jump"] = ThreadJump(state)
    if req.needs_current_xt:
        kwargs["current_word_thread"] = CurrentWordThread(state, word_registry)
    if req.needs_execution_control or req.needs_return_stack:
        kwargs["control"] = ExecutionControl(state)
    if req.needs_error_exit:
        kwargs["err"] = error_exit
    return kwargs


def enforce_requirements(
    descriptor: dictionary.InstructionDescriptor,
    state: LoopState,
) -> None:
    """Apply the current per-handler preflight checks."""

    req = descriptor.requirements
    depth = stack_depth(state.data_stack)
    available = state.stack_limit - depth

    if depth < req.min_data_stack_in:
        error_exit(
            "stack-underflow",
            (
                f"{descriptor.key} needs {req.min_data_stack_in} data cells at ingress, "
                f"but only {depth} are present"
            ),
        )
    if available < req.min_data_stack_out_space:
        error_exit(
            "stack-overflow",
            (
                f"{descriptor.key} declares {req.min_data_stack_out_space} cells of "
                f"data-stack egress space, but only {available} slots remain"
            ),
        )


def step_once(
    state: LoopState,
    *,
    word_registry: dict[int, WordSpec],
) -> tuple[dictionary.InstructionDescriptor, str, list[str], str]:
    if state.ip >= len(state.current_thread):
        error_exit("missing-exit", f"ip={state.ip} stepped past the end of the thread")

    state.current_xt = int(state.current_thread[state.ip])
    word = word_registry.get(state.current_xt)
    if word is None:
        error_exit("unknown-word", f"no word spec for xt {state.current_xt}")
    descriptor = dictionary.instruction_descriptor_for_handler_id(word.handler_id)
    if descriptor is None:
        error_exit("unknown-handler", f"no descriptor for handler id {word.handler_id}")

    handler = HANDLERS.get(word.handler_id)
    if handler is None:
        error_exit("missing-python-handler", f"no Python handler wired for {descriptor.key}")

    enforce_requirements(descriptor, state)
    kwargs = injected_resources(descriptor, state, word_registry=word_registry)
    injected_names = list(kwargs.keys())
    note = handler(**kwargs)

    if not state.halted:
        state.ip += 1
    return descriptor, word.name, injected_names, note


def execute_scenario(scenario: Scenario) -> ScenarioResult:
    word_registry = build_word_registry(scenario)
    trace_rows: list[TraceRow] = []

    try:
        compiled_thread = resolve_entry_thread(scenario)
        state = LoopState(current_thread=compiled_thread)
        decompiled_thread = decompile_program(
            Scenario(
                name=scenario.name,
                text=scenario.text,
                thread=compiled_thread,
                expected_decompile=scenario.expected_decompile,
                expected_stack=scenario.expected_stack,
                expected_halted=scenario.expected_halted,
                expected_final_ip=scenario.expected_final_ip,
                expected_error_code=scenario.expected_error_code,
                expected_trace_words=scenario.expected_trace_words,
                compile_source=scenario.compile_source,
                expected_compiled_thread=scenario.expected_compiled_thread,
                custom_words=scenario.custom_words,
            ),
            word_registry,
        )
        while not state.halted:
            step = len(trace_rows)
            stack_before = tuple(state.data_stack)
            active_ip = state.ip
            descriptor, word_name, injected_names, note = step_once(
                state,
                word_registry=word_registry,
            )
            trace_rows.append(
                TraceRow(
                    step=step,
                    ip=active_ip,
                    word=word_name,
                    family=descriptor.family.key,
                    associated_data_source=descriptor.associated_data_source.value,
                    kernel=descriptor.requirements.kernel,
                    injected_names=tuple(injected_names),
                    stack_before=stack_before,
                    stack_after=tuple(state.data_stack),
                    note=note,
                    next_ip=None if state.halted else state.ip,
                    halted=state.halted,
                )
            )
    except ExecutionFault as exc:
        return ScenarioResult(
            compiled_thread=tuple() if "compiled_thread" not in locals() else compiled_thread,
            decompiled_thread=tuple() if "decompiled_thread" not in locals() else decompiled_thread,
            final_stack=tuple() if "state" not in locals() else tuple(state.data_stack),
            halted=False if "state" not in locals() else state.halted,
            final_ip=0 if "state" not in locals() else state.ip,
            error_code=exc.code,
            error_detail=exc.detail,
            trace=tuple(trace_rows),
        )

    return ScenarioResult(
        compiled_thread=compiled_thread,
        decompiled_thread=decompiled_thread,
        final_stack=tuple(state.data_stack),
        halted=state.halted,
        final_ip=state.ip,
        error_code=None,
        error_detail=None,
        trace=tuple(trace_rows),
    )


def assert_result_matches(scenario: Scenario, result: ScenarioResult) -> None:
    if scenario.expected_compiled_thread is not None:
        assert result.compiled_thread == scenario.expected_compiled_thread, (
            f"{scenario.name}: expected compiled thread {scenario.expected_compiled_thread}, "
            f"got {result.compiled_thread}"
        )
    assert result.decompiled_thread == scenario.expected_decompile, (
        f"{scenario.name}: expected decompile {scenario.expected_decompile}, got {result.decompiled_thread}"
    )
    assert result.final_stack == scenario.expected_stack, (
        f"{scenario.name}: expected stack {scenario.expected_stack}, got {result.final_stack}"
    )
    assert result.halted is scenario.expected_halted, (
        f"{scenario.name}: expected halted={scenario.expected_halted}, got {result.halted}"
    )
    assert result.final_ip == scenario.expected_final_ip, (
        f"{scenario.name}: expected final ip {scenario.expected_final_ip}, got {result.final_ip}"
    )
    assert result.error_code == scenario.expected_error_code, (
        f"{scenario.name}: expected error {scenario.expected_error_code!r}, got {result.error_code!r}"
    )
    actual_trace_words = tuple(row.word for row in result.trace)
    assert actual_trace_words == scenario.expected_trace_words, (
        f"{scenario.name}: expected trace {scenario.expected_trace_words}, got {actual_trace_words}"
    )


def print_result_trace(scenario: Scenario, result: ScenarioResult) -> None:
    print(f"== {scenario.name.upper()} ==")
    print(f"thread: {scenario.text}")
    if scenario.compile_source is not None:
        print(f"compile source: {scenario.compile_source}")
        print(f"compiled thread: {list(result.compiled_thread)}")
    print("decompile:")
    for line in result.decompiled_thread:
        print(f"  {line}")
    print(
        "expected:"
        f" decompile={list(scenario.expected_decompile)}"
        f" stack={list(scenario.expected_stack)}"
        f" halted={scenario.expected_halted}"
        f" final_ip={scenario.expected_final_ip}"
        f" error={scenario.expected_error_code!r}"
        f" trace={list(scenario.expected_trace_words)}"
    )

    for row in result.trace:
        print(
            f"step {row.step}: ip={row.ip} word={row.word} "
            f"family={row.family} "
            f"source={row.associated_data_source} "
            f"kernel={row.kernel}"
        )
        print(f"  stack before: {list(row.stack_before)}")
        print(
            f"  injected: {', '.join(row.injected_names) if row.injected_names else '(none)'}"
        )
        print(f"  note: {row.note}")
        print(f"  stack after: {list(row.stack_after)}")
        print(f"  next ip: {'halt' if row.halted else row.next_ip}")

    if result.error_code is not None:
        print(f"result: error {result.error_code}: {result.error_detail}")
        print(f"final stack: {list(result.final_stack)}")
        print(f"final ip: {result.final_ip}")
    else:
        print(
            f"result: ok stack={list(result.final_stack)} "
            f"halted={result.halted} final_ip={result.final_ip}"
        )
    print("expectation check: ok")
    print()


def run_scenario(scenario: Scenario) -> None:
    result = execute_scenario(scenario)
    assert_result_matches(scenario, result)
    print_result_trace(scenario, result)


def main() -> None:
    print("HandlerRequirements-driven Python loop")
    print("This is a minimal proof of concept over package metadata, not the package runtime.")
    print()
    for scenario in SCENARIOS:
        run_scenario(scenario)


if __name__ == "__main__":
    main()
