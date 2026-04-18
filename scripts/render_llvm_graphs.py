"""Render LLVM CFG and callgraph SVGs for project IR artifacts.

This wraps the local `opt` + Graphviz workflow in a project-local tool that is
useful for the kinds of llvmlite explorations in this repository, especially the
lowered seam lab.

Usage examples:

    uv run python scripts/render_llvm_graphs.py
    uv run python scripts/render_llvm_graphs.py --artifact raw
    uv run python scripts/render_llvm_graphs.py --artifact o3
    uv run python scripts/render_llvm_graphs.py --input lowered-handler-python-loop-seam.O3.ll
    uv run python scripts/render_llvm_graphs.py --focus lowered_run _lowered_step_current

By default, the seam-lab raw and O3 artifacts are both rendered into one bundle.
"""

from __future__ import annotations

import argparse
import html
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
RAW_SEAM_IR = ROOT / "lowered-handler-python-loop-seam.ll"
OPT_SEAM_IR = ROOT / "lowered-handler-python-loop-seam.O3.ll"
DEFAULT_OUTPUT_ROOT = ROOT / "llvm-viz-output"

TOOL_PATH_CANDIDATES = (
    Path("/Users/manny/stuff/bin"),
    Path("/opt/homebrew/opt/llvm/bin"),
    Path("/opt/homebrew/opt/graphviz/bin"),
    Path("/usr/local/opt/llvm/bin"),
    Path("/usr/local/opt/graphviz/bin"),
)

DEFAULT_FOCUS = (
    "_lowered_step_current",
    "lowered_run",
    "lowered_step",
    "lowered_step_xt",
)


@dataclass(frozen=True)
class ToolPaths:
    opt: str
    dot: str


@dataclass(frozen=True)
class ArtifactInput:
    label: str
    input_path: Path


@dataclass(frozen=True)
class ArtifactRender:
    label: str
    input_path: Path
    output_dir: Path
    rendered_paths: list[tuple[str, Path]]
    callgraph_svg: Path | None
    function_summaries: dict[str, "FunctionIRSummary"]


@dataclass(frozen=True)
class FunctionIRSummary:
    alloca_count: int
    phi_count: int
    load_count: int
    store_count: int

    @property
    def has_alloca(self) -> bool:
        return self.alloca_count > 0


DEFINE_RE = re.compile(r"^define\s+(?:internal\s+)?(?:\w+\s+)*@(?P<name>[^(\s]+)\(")
ALLOCA_RE = re.compile(r"\balloca\b")
PHI_RE = re.compile(r"\bphi\b")
LOAD_RE = re.compile(r"(?:=\s*)?\bload\b")
STORE_RE = re.compile(r"\bstore\b")


def prepend_tool_paths() -> None:
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    prepend = [str(candidate) for candidate in TOOL_PATH_CANDIDATES if candidate.is_dir()]
    os.environ["PATH"] = os.pathsep.join([*prepend, *path_entries])


def find_required_tools() -> ToolPaths:
    prepend_tool_paths()
    opt = shutil.which("opt")
    dot = shutil.which("dot")
    if opt and dot:
        return ToolPaths(opt=opt, dot=dot)

    missing: list[str] = []
    if not opt:
        missing.append("opt")
    if not dot:
        missing.append("dot")
    candidate_text = "\n".join(f"  - {candidate}" for candidate in TOOL_PATH_CANDIDATES)
    raise SystemExit(
        "Missing required LLVM graphviz tools: "
        f"{', '.join(missing)}\n"
        "Searched PATH plus these local candidates:\n"
        f"{candidate_text}\n"
        "Install LLVM `opt` and Graphviz `dot`, then rerun this script."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render LLVM CFG/callgraph SVGs for repo IR artifacts."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Path to a .ll file. When provided, only that artifact is rendered.",
    )
    parser.add_argument(
        "--artifact",
        choices=("raw", "o3", "both"),
        default="both",
        help="Use the repo-top seam-lab artifact(s) when --input is omitted.",
    )
    parser.add_argument(
        "--focus",
        nargs="*",
        default=list(DEFAULT_FOCUS),
        help=(
            "Function names to emphasize in the generated HTML index. "
            "All rendered CFGs are still included."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Directory to write the rendered output to. "
            "Defaults to llvm-viz-output/<artifact-name>-cfg-<timestamp>/ "
            "or llvm-viz-output/lowered-handler-python-loop-seam-both-cfg-<timestamp>/"
        ),
    )
    parser.add_argument(
        "--keep-dot",
        action="store_true",
        help="Keep intermediate .dot files in the output directory.",
    )
    parser.add_argument(
        "--no-callgraph",
        action="store_true",
        help="Skip callgraph generation even if the local opt supports it.",
    )
    return parser.parse_args()


def choose_inputs(args: argparse.Namespace) -> list[ArtifactInput]:
    if args.input is not None:
        return [ArtifactInput(label="input", input_path=args.input.resolve())]
    if args.artifact == "raw":
        return [ArtifactInput(label="raw", input_path=RAW_SEAM_IR)]
    if args.artifact == "o3":
        return [ArtifactInput(label="o3", input_path=OPT_SEAM_IR)]
    return [
        ArtifactInput(label="raw", input_path=RAW_SEAM_IR),
        ArtifactInput(label="o3", input_path=OPT_SEAM_IR),
    ]


def default_output_dir(inputs: list[ArtifactInput]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if len(inputs) == 1:
        return DEFAULT_OUTPUT_ROOT / f"{inputs[0].input_path.stem}-cfg-{timestamp}"
    return DEFAULT_OUTPUT_ROOT / f"lowered-handler-python-loop-seam-both-cfg-{timestamp}"


def run_command(
    argv: list[str],
    *,
    cwd: Path,
    stderr_path: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        argv,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if stderr_path is not None:
        stderr_path.write_text(result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(argv)}\n"
            f"{result.stderr.strip()}"
        )
    return result


def generate_cfg_dots(*, opt: str, input_path: Path, work_dir: Path) -> None:
    run_command(
        [opt, "-passes=dot-cfg", "-disable-output", str(input_path)],
        cwd=work_dir,
        stderr_path=work_dir / "opt.stderr.txt",
    )
    (work_dir / "opt.command.txt").write_text(
        f"{opt} -passes=dot-cfg -disable-output {input_path}\n",
        encoding="utf-8",
    )


def try_generate_callgraph_dot(*, opt: str, input_path: Path, work_dir: Path) -> Path | None:
    attempts = (
        [opt, "-passes=dot-callgraph", "-disable-output", str(input_path)],
        [opt, "-dot-callgraph", "-disable-output", str(input_path)],
    )
    for argv in attempts:
        result = subprocess.run(
            argv,
            cwd=work_dir,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            (work_dir / "callgraph.command.txt").write_text(
                " ".join(argv) + "\n",
                encoding="utf-8",
            )
            (work_dir / "callgraph.stderr.txt").write_text(result.stderr, encoding="utf-8")
            candidates = sorted(work_dir.glob("*.callgraph.dot")) + sorted(work_dir.glob("callgraph*.dot"))
            if candidates:
                return candidates[0]
    return None


def render_svg(*, dot: str, dot_path: Path, svg_path: Path) -> None:
    run_command(
        [dot, "-Tsvg", str(dot_path), "-o", str(svg_path)],
        cwd=svg_path.parent,
    )


def cfg_dot_files(work_dir: Path) -> list[Path]:
    return sorted(
        path for path in work_dir.glob("*.dot") if "callgraph" not in path.name.lower()
    )


def display_name_for_dot(dot_path: Path) -> str:
    name = dot_path.stem
    if name.startswith("."):
        name = name[1:]
    if name.startswith("cfg."):
        name = name[4:]
    return name


def sort_focus(files: Iterable[Path], focus_names: list[str]) -> list[Path]:
    by_name = {display_name_for_dot(path): path for path in files}
    ordered: list[Path] = [by_name[name] for name in focus_names if name in by_name]
    remainder = [path for path in files if path not in ordered]
    return [*ordered, *remainder]


def seam_artifact_links(*, input_path: Path, output_dir: Path) -> list[tuple[str, str]]:
    links: list[tuple[str, str]] = []
    copied_input = output_dir / input_path.name
    if copied_input.exists():
        links.append((f"Rendered input copy: {input_path.name}", copied_input.name))

    known = [
        ("Seam raw IR", RAW_SEAM_IR),
        ("Seam O3 IR", OPT_SEAM_IR),
    ]
    seen: set[Path] = {copied_input.resolve()} if copied_input.exists() else set()
    for label, artifact_path in known:
        if not artifact_path.exists():
            continue
        resolved = artifact_path.resolve()
        if resolved in seen:
            continue
        try:
            rel = artifact_path.relative_to(output_dir)
        except ValueError:
            rel = Path(os.path.relpath(artifact_path, output_dir))
        links.append((label, rel.as_posix()))
        seen.add(resolved)
    return links


def summarize_functions(llvm_ir: str) -> dict[str, FunctionIRSummary]:
    summaries: dict[str, FunctionIRSummary] = {}
    current_name: str | None = None
    current_lines: list[str] = []

    def commit() -> None:
        nonlocal current_name, current_lines
        if current_name is None:
            return
        body = "\n".join(current_lines)
        summaries[current_name] = FunctionIRSummary(
            alloca_count=len(ALLOCA_RE.findall(body)),
            phi_count=len(PHI_RE.findall(body)),
            load_count=len(LOAD_RE.findall(body)),
            store_count=len(STORE_RE.findall(body)),
        )
        current_name = None
        current_lines = []

    for line in llvm_ir.splitlines():
        match = DEFINE_RE.match(line)
        if match:
            commit()
            current_name = match.group("name")
            current_lines = []
            continue
        if current_name is not None:
            if line == "}":
                commit()
            else:
                current_lines.append(line)

    commit()
    return summaries


def function_summary_html(summary: FunctionIRSummary | None) -> str:
    if summary is None:
        return "<p><em>No IR summary available for this function.</em></p>"
    alloca_badge = (
        f'<strong style="color:#b00020">alloca={summary.alloca_count}</strong>'
        if summary.has_alloca
        else f"alloca={summary.alloca_count}"
    )
    return (
        "<p><strong>IR summary:</strong> "
        f"{alloca_badge} "
        f"phi={summary.phi_count} "
        f"load={summary.load_count} "
        f"store={summary.store_count}"
        "</p>"
    )


def write_single_index(
    *,
    output_dir: Path,
    input_path: Path,
    rendered_paths: list[tuple[str, Path]],
    callgraph_svg: Path | None,
    focus_names: list[str],
    function_summaries: dict[str, FunctionIRSummary],
) -> None:
    artifact_links = seam_artifact_links(input_path=input_path, output_dir=output_dir)
    sections: list[str] = []
    if callgraph_svg is not None:
        rel = callgraph_svg.relative_to(output_dir)
        sections.append(
            f"""
            <section>
              <h2>Call Graph</h2>
              <p><a href="{html.escape(rel.as_posix())}">{html.escape(rel.as_posix())}</a></p>
              <img loading="lazy" src="{html.escape(rel.as_posix())}" alt="callgraph">
            </section>
            """
        )

    for function_name, svg_path in rendered_paths:
        rel = svg_path.relative_to(output_dir)
        highlighted = " (focus)" if function_name in focus_names else ""
        summary = function_summaries.get(function_name)
        sections.append(
            f"""
            <section>
              <h2>{html.escape(function_name)}{html.escape(highlighted)}</h2>
              <p><a href="{html.escape(rel.as_posix())}">{html.escape(rel.as_posix())}</a></p>
              {function_summary_html(summary)}
              <img loading="lazy" src="{html.escape(rel.as_posix())}" alt="{html.escape(function_name)}">
            </section>
            """
        )

    artifact_items = "".join(
        f'<li><a href="{html.escape(rel)}">{html.escape(label)}</a></li>'
        for label, rel in artifact_links
    )

    html_text = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>LLVM CFG Render</title>
    <style>
      body {{
        font-family: ui-sans-serif, system-ui, sans-serif;
        margin: 2rem;
        line-height: 1.5;
      }}
      code {{
        font-family: ui-monospace, monospace;
      }}
      section {{
        margin-block: 2rem 3rem;
      }}
      img {{
        max-width: 100%;
        height: auto;
        border: 1px solid #ddd;
        background: white;
      }}
    </style>
  </head>
  <body>
    <h1>LLVM CFG Render</h1>
    <p><strong>Input IR:</strong> <code>{html.escape(str(input_path))}</code></p>
    <p><strong>Focus functions:</strong> <code>{html.escape(', '.join(focus_names))}</code></p>
    <section>
      <h2>IR Artifacts</h2>
      <ul>
        {artifact_items}
      </ul>
    </section>
    {''.join(sections)}
  </body>
</html>
"""
    (output_dir / "index.html").write_text(html_text, encoding="utf-8")


def write_combined_index(
    *,
    output_dir: Path,
    renders: list[ArtifactRender],
    focus_names: list[str],
) -> None:
    sections: list[str] = []
    for render in renders:
        artifact_links = seam_artifact_links(input_path=render.input_path, output_dir=render.output_dir)
        artifact_items = "".join(
            f'<li><a href="{html.escape(Path(os.path.relpath(render.output_dir / rel, output_dir)).as_posix())}">{html.escape(label)}</a></li>'
            for label, rel in artifact_links
        )
        callgraph_section = ""
        if render.callgraph_svg is not None:
            rel = Path(os.path.relpath(render.callgraph_svg, output_dir)).as_posix()
            callgraph_section = f"""
            <section>
              <h3>{html.escape(render.label.upper())} Call Graph</h3>
              <p><a href="{html.escape(rel)}">{html.escape(rel)}</a></p>
              <img loading="lazy" src="{html.escape(rel)}" alt="{html.escape(render.label)} callgraph">
            </section>
            """

        rendered_sections = []
        for function_name, svg_path in render.rendered_paths:
            rel = Path(os.path.relpath(svg_path, output_dir)).as_posix()
            highlighted = " (focus)" if function_name in focus_names else ""
            summary = render.function_summaries.get(function_name)
            rendered_sections.append(
                f"""
                <section>
                  <h3>{html.escape(render.label.upper())}: {html.escape(function_name)}{html.escape(highlighted)}</h3>
                  <p><a href="{html.escape(rel)}">{html.escape(rel)}</a></p>
                  {function_summary_html(summary)}
                  <img loading="lazy" src="{html.escape(rel)}" alt="{html.escape(render.label)} {html.escape(function_name)}">
                </section>
                """
            )

        subindex_rel = Path(os.path.relpath(render.output_dir / "index.html", output_dir)).as_posix()
        sections.append(
            f"""
            <section>
              <h2>{html.escape(render.label.upper())} Artifact</h2>
              <p><strong>Input IR:</strong> <code>{html.escape(str(render.input_path))}</code></p>
              <p><strong>Sub-index:</strong> <a href="{html.escape(subindex_rel)}">{html.escape(subindex_rel)}</a></p>
              <ul>{artifact_items}</ul>
            </section>
            {callgraph_section}
            {''.join(rendered_sections)}
            """
        )

    html_text = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>LLVM CFG Render</title>
    <style>
      body {{
        font-family: ui-sans-serif, system-ui, sans-serif;
        margin: 2rem;
        line-height: 1.5;
      }}
      code {{
        font-family: ui-monospace, monospace;
      }}
      section {{
        margin-block: 2rem 3rem;
      }}
      img {{
        max-width: 100%;
        height: auto;
        border: 1px solid #ddd;
        background: white;
      }}
    </style>
  </head>
  <body>
    <h1>LLVM CFG Render</h1>
    <p><strong>Focus functions:</strong> <code>{html.escape(', '.join(focus_names))}</code></p>
    {''.join(sections)}
  </body>
</html>
"""
    (output_dir / "index.html").write_text(html_text, encoding="utf-8")


def render_artifact(
    *,
    tools: ToolPaths,
    artifact: ArtifactInput,
    output_dir: Path,
    focus_names: list[str],
    keep_dot: bool,
    no_callgraph: bool,
) -> ArtifactRender:
    rendered_dir = output_dir / "rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_dir.mkdir(parents=True, exist_ok=True)

    copied_input = output_dir / artifact.input_path.name
    llvm_ir = artifact.input_path.read_text(encoding="utf-8")
    copied_input.write_text(llvm_ir, encoding="utf-8")
    function_summaries = summarize_functions(llvm_ir)

    generate_cfg_dots(opt=tools.opt, input_path=artifact.input_path, work_dir=output_dir)
    callgraph_dot: Path | None = None
    if not no_callgraph:
        callgraph_dot = try_generate_callgraph_dot(
            opt=tools.opt,
            input_path=artifact.input_path,
            work_dir=output_dir,
        )

    dot_files = cfg_dot_files(output_dir)
    ordered_dots = sort_focus(dot_files, focus_names)
    rendered_paths: list[tuple[str, Path]] = []
    for dot_path in ordered_dots:
        function_name = display_name_for_dot(dot_path)
        svg_path = rendered_dir / f"{function_name}.svg"
        render_svg(dot=tools.dot, dot_path=dot_path, svg_path=svg_path)
        rendered_paths.append((function_name, svg_path))

    callgraph_svg: Path | None = None
    if callgraph_dot is not None:
        callgraph_svg = rendered_dir / "callgraph.svg"
        render_svg(dot=tools.dot, dot_path=callgraph_dot, svg_path=callgraph_svg)

    write_single_index(
        output_dir=output_dir,
        input_path=artifact.input_path,
        rendered_paths=rendered_paths,
        callgraph_svg=callgraph_svg,
        focus_names=focus_names,
        function_summaries=function_summaries,
    )

    if not keep_dot:
        for dot_path in output_dir.glob("*.dot"):
            dot_path.unlink()

    return ArtifactRender(
        label=artifact.label,
        input_path=artifact.input_path,
        output_dir=output_dir,
        rendered_paths=rendered_paths,
        callgraph_svg=callgraph_svg,
        function_summaries=function_summaries,
    )


def main() -> None:
    args = parse_args()
    tools = find_required_tools()
    inputs = choose_inputs(args)
    for artifact in inputs:
        if not artifact.input_path.is_file():
            raise SystemExit(f"IR input not found: {artifact.input_path}")

    output_dir = args.output_dir.resolve() if args.output_dir else default_output_dir(inputs)
    output_dir.mkdir(parents=True, exist_ok=True)

    renders: list[ArtifactRender] = []
    for artifact in inputs:
        artifact_output_dir = output_dir if len(inputs) == 1 else output_dir / artifact.label
        renders.append(
            render_artifact(
                tools=tools,
                artifact=artifact,
                output_dir=artifact_output_dir,
                focus_names=args.focus,
                keep_dot=args.keep_dot,
                no_callgraph=args.no_callgraph,
            )
        )

    if len(renders) > 1:
        write_combined_index(output_dir=output_dir, renders=renders, focus_names=args.focus)

    print(f"wrote {output_dir / 'index.html'}")
    for render in renders:
        for function_name, svg_path in render.rendered_paths:
            print(f"  {render.label}:{function_name}: {svg_path}")
        if render.callgraph_svg is not None:
            print(f"  {render.label}:callgraph: {render.callgraph_svg}")


if __name__ == "__main__":
    main()
