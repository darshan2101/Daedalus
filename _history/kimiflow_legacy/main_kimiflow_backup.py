# main.py
# Usage:
#   python main.py "your goal here"
#   python main.py                    <- interactive prompt
#   python main.py --quiet "goal"     <- suppress verbose model-level output
#   python main.py --help             <- show all options

import sys
import os
import datetime
import json
import argparse

from rich.console import Console
from rich.panel   import Panel
from rich.table   import Table
from rich.rule    import Rule
from rich import box

# Always resolve outputs/ relative to this script, regardless of cwd
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")

console = Console()


# ── CLI arg parsing ─────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="KIMI FLOW — Multi-Model Self-Correcting AI Pipeline",
    )
    parser.add_argument(
        "goal", nargs="*",
        help="The task / goal to solve. Omit to enter interactively.",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress model-level try/success lines; show only pipeline-level output.",
    )
    verbosity.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show all output including full model responses (default).",
    )
    return parser.parse_args()


# ── Goal input ─────────────────────────────────────────────────────────────────

def get_goal(args) -> str:
    if args.goal:
        return " ".join(args.goal).strip()

    console.print(Panel.fit(
        "[bold cyan]KIMI FLOW[/bold cyan] — Multi-Model Self-Correcting AI Pipeline\n"
        "\n[dim]What do you want to build or solve?[/dim]\n"
        "[dim](Multi-line: press Enter twice when done)[/dim]",
        border_style="cyan",
    ))
    console.print()

    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)

    goal = "\n".join(lines).strip()
    if not goal:
        console.print("[red]No goal provided. Exiting.[/red]")
        sys.exit(0)
    return goal


# ── File extraction ────────────────────────────────────────────────────────────

def _extract_files(result_text: str) -> list[tuple[str, str]]:
    """
    Parse structured file blocks from LLM output.

    Format A (preferred):
        --- FILE: relative/path/file.py ---
        <content>
        --- END FILE ---

    Format B (markdown fenced with a filename comment as first line):
        ```python
        # app/main.py
        <content>
        ```
    """
    import re

    pattern_a = re.compile(
        r"---\s*FILE:\s*(.+?)\s*---\n(.*?)---\s*END FILE\s*---",
        re.DOTALL,
    )
    files = pattern_a.findall(result_text)
    if files:
        return [(p.strip(), c) for p, c in files]

    pattern_b = re.compile(
        r"```[a-z]*\n#\s*([\w/\\.\\-]+)\n(.*?)```",
        re.DOTALL,
    )
    files = pattern_b.findall(result_text)
    if files:
        return [(p.strip(), c) for p, c in files]

    return []


# ── Write & zip ────────────────────────────────────────────────────────────────

def _write_and_zip(parsed_files: list[tuple[str, str]], ts: str) -> str | None:
    """
    Write files into outputs/project_<ts>/ then zip to outputs/<ts>.zip.
    Returns the absolute path to the zip, or None on failure.
    """
    import zipfile

    project_dir = os.path.join(OUTPUTS_DIR, f"project_{ts}")
    zip_path    = os.path.join(OUTPUTS_DIR, f"{ts}.zip")
    os.makedirs(project_dir, exist_ok=True)

    console.print(f"\n[bold]Writing {len(parsed_files)} file(s) → {project_dir}[/bold]\n")

    for rel_path, content in parsed_files:
        rel_path = rel_path.replace("\\", "/").lstrip("/")
        abs_path = os.path.join(project_dir, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        console.print(f"  [green]wrote[/green] → {rel_path}")

    console.print(f"\n[bold]Zipping → {zip_path}[/bold]")
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _dirs, files in os.walk(project_dir):
                for fname in files:
                    abs_file = os.path.join(root, fname)
                    arc_name = os.path.relpath(abs_file, project_dir)
                    zf.write(abs_file, arc_name)
        return zip_path
    except Exception as e:
        console.print(f"[red][Zip failed: {e}][/red]")
        return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    args = parse_args()
    goal = get_goal(args)

    # Redirect noisy model-level prints when --quiet is active
    if args.quiet:
        import builtins, io
        _real_print = builtins.print
        def _quiet_print(*a, **kw):
            text = " ".join(str(x) for x in a)
            # Only suppress the low-level [trying / success / error] lines
            if any(text.startswith(p) for p in ("  [trying", "  [success", "  [error", "  [404", "  [429", "  [null")):
                return
            _real_print(*a, **kw)
        builtins.print = _quiet_print

    console.print()
    console.print(Panel.fit(
        f"[bold cyan]KIMI FLOW[/bold cyan]\n\n"
        f"[bold]Goal:[/bold] {goal[:160]}{'...' if len(goal) > 160 else ''}",
        border_style="cyan",
    ))
    console.print()

    from pipeline import pipeline  # import here so quiet patch is already in place

    initial_state = {
        "task":           goal,
        "plan":           "",
        "assigned_model": "",
        "result":         "",
        "quality_score":  0.0,
        "feedback":       "",
        "iterations":     0,
    }

    # Set recursion limit high enough to allow 15 full iterations (2 nodes each + routing)
    final = pipeline.invoke(initial_state, config={"recursion_limit": 100})

    # ── Summary panel ─────────────────────────────────────────────────────────
    score = final["quality_score"]
    score_color = "green" if score >= 0.85 else ("yellow" if score >= 0.6 else "red")

    summary = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    summary.add_column("Key",   style="dim", width=14)
    summary.add_column("Value", style="bold")
    summary.add_row("Iterations", str(final["iterations"]))
    summary.add_row("Final score", f"[{score_color}]{score:.0%}[/{score_color}]")
    summary.add_row("Specialist",  final["assigned_model"] or "—")
    summary.add_row("Feedback",    (final.get("feedback") or "—")[:120])

    console.print(Rule("[bold]Run Complete[/bold]", style="cyan"))
    console.print(summary)

    # ── Persist results ────────────────────────────────────────────────────────
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    ts          = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    result_text = final["result"]

    parsed_files = _extract_files(result_text)

    # Always write a JSON run summary (great for debugging iteration history)
    run_summary = {
        "goal":        goal,
        "timestamp":   ts,
        "iterations":  final["iterations"],
        "final_score": final["quality_score"],
        "specialist":  final["assigned_model"],
        "feedback":    final.get("feedback", ""),
        "files_found": len(parsed_files),
    }
    summary_path = os.path.join(OUTPUTS_DIR, f"run_{ts}.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(run_summary, f, indent=2)
    console.print(f"  [dim]Run summary →[/dim] {summary_path}")

    if parsed_files:
        zip_path = _write_and_zip(parsed_files, ts)

        if zip_path and os.path.exists(zip_path):
            console.print(Panel.fit(
                f"[bold green]SUCCESS[/bold green]\n\n"
                f"Files : {len(parsed_files)}\n"
                f"Zip   : {zip_path}",
                border_style="green",
            ))
            return zip_path
        else:
            console.print(f"[yellow][Zip step failed — files still in outputs/project_{ts}/][/yellow]")

    else:
        # No structured file blocks — save raw output as .txt
        txt_path = os.path.join(OUTPUTS_DIR, f"result_{ts}.txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"GOAL:\n{goal}\n\n")
            f.write(f"SCORE: {final['quality_score']:.2f}\n")
            f.write(f"SPECIALIST: {final['assigned_model']}\n")
            f.write(f"ITERATIONS: {final['iterations']}\n\n")
            f.write("RESULT:\n")
            f.write(result_text)

        console.print(Panel(
            f"[yellow]No structured file blocks found.[/yellow]\n"
            f"The model did not follow the [bold]--- FILE: path ---[/bold] format.\n\n"
            f"Raw result saved → [bold]{os.path.abspath(txt_path)}[/bold]\n\n"
            f"[dim]Tip: Re-run. A different model in the fallback chain may follow the format.[/dim]",
            border_style="yellow",
        ))

        if not args.quiet:
            console.print(Rule("[dim]RAW OUTPUT (first 3000 chars)[/dim]"))
            console.print(result_text[:3000])


if __name__ == "__main__":
    main()