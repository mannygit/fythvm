"""Render LLVM CFG and callgraph SVGs for project IR artifacts.

This wraps the local `opt` + Graphviz workflow in a project-local tool that is
useful for the kinds of llvmlite explorations in this repository, especially the
lowered seam lab.

Usage examples:

    uv run python scripts/render_llvm_graphs.py
    uv run python scripts/render_llvm_graphs.py --artifact raw
    uv run python scripts/render_llvm_graphs.py --input lowered-handler-python-loop-seam.O3.ll
    uv run python scripts/render_llvm_graphs.py --focus lowered_run _lowered_step_current

The default input is the optimized seam-lab IR artifact at the repo root.
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
        help="Path to a .ll file. Defaults to the optimized seam-lab artifact.",
    )
    parser.add_argument(
        "--artifact",
        choices=("raw", "o3"),
        default="o3",
        help="Use the repo-top seam-lab artifact when --input is omitted.",
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
            "Defaults to llvm-viz-output/<artifact-name>-cfg-<timestamp>/"
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


def choose_input(args: argparse.Namespace) -> Path:
    if args.input is not None:
        return args.input.resolve()
    if args.artifact == "raw":
        return RAW_SEAM_IR
    return OPT_SEAM_IR


def default_output_dir(input_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_ROOT / f"{input_path.stem}-cfg-{timestamp}"


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


def write_index(
    *,
    output_dir: Path,
    input_path: Path,
    rendered_paths: list[tuple[str, Path]],
    callgraph_svg: Path | None,
    focus_names: list[str],
) -> None:
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
        sections.append(
            f"""
            <section>
              <h2>{html.escape(function_name)}{html.escape(highlighted)}</h2>
              <p><a href="{html.escape(rel.as_posix())}">{html.escape(rel.as_posix())}</a></p>
              <img loading="lazy" src="{html.escape(rel.as_posix())}" alt="{html.escape(function_name)}">
            </section>
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
    <p><strong>Input IR:</strong> <code>{html.escape(str(input_path))}</code></p>
    <p><strong>Focus functions:</strong> <code>{html.escape(', '.join(focus_names))}</code></p>
    {''.join(sections)}
  </body>
</html>
"""
    (output_dir / "index.html").write_text(html_text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    tools = find_required_tools()
    input_path = choose_input(args)
    if not input_path.is_file():
        raise SystemExit(f"IR input not found: {input_path}")

    output_dir = args.output_dir.resolve() if args.output_dir else default_output_dir(input_path)
    rendered_dir = output_dir / "rendered"
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_dir.mkdir(parents=True, exist_ok=True)

    copied_input = output_dir / input_path.name
    copied_input.write_text(input_path.read_text(encoding="utf-8"), encoding="utf-8")

    generate_cfg_dots(opt=tools.opt, input_path=input_path, work_dir=output_dir)
    callgraph_dot: Path | None = None
    if not args.no_callgraph:
        callgraph_dot = try_generate_callgraph_dot(opt=tools.opt, input_path=input_path, work_dir=output_dir)

    dot_files = cfg_dot_files(output_dir)
    ordered_dots = sort_focus(dot_files, args.focus)
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

    write_index(
        output_dir=output_dir,
        input_path=input_path,
        rendered_paths=rendered_paths,
        callgraph_svg=callgraph_svg,
        focus_names=args.focus,
    )

    if not args.keep_dot:
        for dot_path in output_dir.glob("*.dot"):
            dot_path.unlink()

    print(f"wrote {output_dir / 'index.html'}")
    for function_name, svg_path in rendered_paths:
        print(f"  {function_name}: {svg_path}")
    if callgraph_svg is not None:
        print(f"  callgraph: {callgraph_svg}")


if __name__ == "__main__":
    main()
