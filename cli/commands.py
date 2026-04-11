import argparse
import json
import os
import re
import subprocess

from cli.views import console, print_error, print_kanban, print_spec_list, print_success
from core import PROJECT_ROOT, TOOL_DIR
from core.aider_runner import run_aider
from core.git_utils import (
    create_branch,
    delete_branch,
    get_branch_files,
    get_default_branch,
    get_diff,
    get_unmerged_branches,
    merge_and_delete_branch,
    slugify,
    stage_and_commit,
)
from core.model_manager import ModelManager
from core.ollama_client import chat
from core.spec_manager import (
    ARCH_DIR,
    SPECS_DIR,
    STAGES,
    append_feedback_to_spec,
    init_env,
    list_specs,
    move_spec,
    read_spec,
)


def _model_manager() -> ModelManager:
    return ModelManager(os.path.join(TOOL_DIR, "factory_config.yaml"))





def _load_pre_review_checks() -> list[str]:
    """Load pre_review_checks from factory_config.yaml."""
    import yaml
    config_path = os.path.join(TOOL_DIR, "factory_config.yaml")
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("pre_review_checks", [])


def _run_pre_review_checks() -> list[tuple[str, str]]:
    """Run each pre-review check in PROJECT_ROOT.

    Returns a list of (command, output) tuples for every check that failed.
    """
    checks = _load_pre_review_checks()
    failures = []
    for cmd in checks:
        console.print(f"[bold]Running check:[/bold] {cmd}")
        result = subprocess.run(
            ["bash", "-lc", cmd],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            output = (result.stdout + result.stderr).strip()
            console.print(f"[bold red]FAILED:[/bold red] {cmd}\n{output}")
            failures.append((cmd, output))
        else:
            console.print(f"[bold green]PASSED:[/bold green] {cmd}")
    return failures


def _write_ci_rework_spec(original_filename: str, failures: list[tuple[str, str]]) -> str:
    """Write a rework spec auto-generated from CI check failures.

    Returns the rework filename.
    """
    rework_filename = _next_rework_filename(original_filename)
    title = original_filename.replace(".md", "").replace("_", " ").title()

    failure_blocks = []
    for cmd, output in failures:
        failure_blocks.append(
            f"- Fix the failure produced by `{cmd}`:\n```\n{output[:2000]}\n```"
        )
    criteria = "\n".join(failure_blocks)

    content = f"""\
# Rework: {title} — CI checks failed

## Original Task
{_original_filename(original_filename)}

## Context
This is a focused rework. Only the CI failures listed below are in scope.
The rest of the original implementation has been accepted.

## Acceptance Criteria
{criteria}

## Branch Name
{_next_rework_filename(original_filename).replace(".md", "")}
"""
    dest = os.path.join(SPECS_DIR, "02_ready_for_dev", rework_filename)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "w") as f:
        f.write(content)
    return rework_filename


# Matches rework tickets: 08_task_added_event_rework_00.md → (base, index)
_REWORK_RE = re.compile(r'^(.+)_rework_(\d+)\.md$')


def _next_rework_filename(filename: str) -> str:
    """Return the next rework filename for a given original or rework spec."""
    m = _REWORK_RE.match(filename)
    if m:
        return f"{m.group(1)}_rework_{int(m.group(2)) + 1:02d}.md"
    return f"{filename[:-3]}_rework_00.md"


def _original_filename(filename: str) -> str:
    """Return the original spec filename for a rework ticket."""
    m = _REWORK_RE.match(filename)
    return f"{m.group(1)}.md" if m else filename


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    init_env()
    print_success("Environment initialized.")


def cmd_architect(args: argparse.Namespace) -> None:
    blueprint_path = args.blueprint or os.path.join(ARCH_DIR, "project_blueprint.md")

    if not os.path.exists(blueprint_path):
        print_error(f"Blueprint not found: {blueprint_path}")
        return

    with open(blueprint_path) as f:
        blueprint_content = f.read()

    backlog_path = os.path.join(SPECS_DIR, "01_backlog")
    os.makedirs(backlog_path, exist_ok=True)
    backlog_rel = os.path.relpath(backlog_path, PROJECT_ROOT)

    # --- Phase 1: Planning — ask Ollama directly for a JSON task list ---
    console.print("[bold]Phase 1/2:[/bold] Generating task plan…")

    plan_agent_path = os.path.join(TOOL_DIR, "agents", "architect_plan.md")
    with open(plan_agent_path) as f:
        plan_system_prompt = f.read()

    mm = _model_manager()
    mm.ensure_model_loaded("architect")
    ollama_model = mm.get_model_for_role("architect").removeprefix("ollama/")

    try:
        raw_plan = chat(ollama_model, plan_system_prompt, f"BLUEPRINT:\n{blueprint_content}")
    except RuntimeError as e:
        print_error(str(e))
        return

    # Strip optional markdown fences the model may add despite instructions
    cleaned = raw_plan.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    cleaned = cleaned.strip()

    try:
        task_plan: list[dict] = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print_error(f"Architect plan was not valid JSON: {e}\nRaw response:\n{raw_plan}")
        return

    console.print(f"[green]Plan received:[/green] {len(task_plan)} task(s) to generate.")

    # Safety net: re-index tasks sequentially starting at 01.
    # Enforce the two-digit prefix on every filename.
    task_plan.sort(key=lambda t: t.get("index", 0))
    for seq, task in enumerate(task_plan, start=1):
        task["index"] = seq
        fname = task.get("filename", "task.md")
        # Strip any existing leading digits+underscore, then reapply from seq
        bare = re.sub(r"^\d+_", "", fname)
        task["filename"] = f"{seq:02d}_{bare}"

    # --- Phase 2: Task authoring — one Ollama call per task, written directly by Python ---
    # Aider cannot write to specs/ because it is in .aiderignore (intentionally, to keep
    # spec files out of the developer agent's context). Use chat() + direct file I/O instead.
    task_agent_path = os.path.join(TOOL_DIR, "agents", "architect_task.md")
    with open(task_agent_path) as f:
        task_role_prompt = f.read()

    failed = 0
    for task in sorted(task_plan, key=lambda t: t.get("index", 0)):
        filename = task.get("filename", "")
        title = task.get("title", filename)

        console.print(f"  Writing [cyan]{filename}[/cyan] — {title}")

        user_message = (
            f"TASK PLAN ENTRY:\n{json.dumps(task, indent=2)}\n\n"
            f"BLUEPRINT (for context):\n{blueprint_content}"
        )

        try:
            spec_content = chat(ollama_model, task_role_prompt, user_message)
        except RuntimeError as e:
            print_error(f"Failed to generate {filename}: {e}")
            failed += 1
            continue

        dest = os.path.join(PROJECT_ROOT, backlog_rel, filename)
        with open(dest, "w") as f:
            f.write(spec_content.strip() + "\n")

    if failed == 0:
        print_success(f"Architect complete. {len(task_plan)} task(s) created in 01_backlog.")
    else:
        print_error(f"Architect finished with {failed} failure(s). Check output above.")


def cmd_list(args: argparse.Namespace) -> None:
    files = list_specs(args.stage)
    print_spec_list(args.stage, files)


def cmd_kanban(args: argparse.Namespace) -> None:
    """Display all Kanban columns and their specs at a glance."""
    print_kanban([(stage, list_specs(stage)) for stage in STAGES])


def cmd_pick(args: argparse.Namespace) -> None:
    """Human gate 1 — promote a task from 01_backlog to 02_ready_for_dev."""
    filename = args.filename
    source = os.path.join(SPECS_DIR, "01_backlog", filename)
    if not os.path.exists(source):
        print_error(f"{filename} not found in 01_backlog.")
        return
    move_spec(filename, "01_backlog", "02_ready_for_dev")
    print_success(f"{filename} moved to 02_ready_for_dev.")


def cmd_run(args: argparse.Namespace) -> None:
    """Trigger the Developer agent on a task in 02_ready_for_dev."""
    filename = args.filename

    # Warn if there are unmerged branches — running a new task before approving
    # previous ones means the developer agent won't see their changes.
    unmerged = get_unmerged_branches()
    current_branch = slugify(filename)
    m_rework = _REWORK_RE.match(filename)
    original_branch = slugify(_original_filename(filename)) if m_rework else None
    pending = [
        b for b in unmerged
        if b != current_branch
        and (original_branch is None or not b.startswith(original_branch))
    ]
    if pending:
        console.print(
            f"[bold yellow]Warning:[/bold yellow] {len(pending)} unmerged branch(es) detected: "
            + ", ".join(f"[cyan]{b}[/cyan]" for b in pending)
        )
        console.print(
            "[yellow]The developer agent will NOT see changes from these branches. "
            "Run [bold]sovereign approve <spec>[/bold] first, or proceed with --force.[/yellow]"
        )
        if not args.force:
            return

    agent_path = os.path.join(TOOL_DIR, "agents", "developer.md")
    with open(agent_path) as f:
        role_prompt = f.read()

    mm = _model_manager()
    mm.ensure_model_loaded("developer")
    model = mm.get_model_for_role("developer")

    task_content = read_spec(filename, "02_ready_for_dev")
    branch = slugify(filename)
    # Rework branches must start from the original branch so the full diff is preserved
    m = _REWORK_RE.match(filename)
    from_branch = slugify(_original_filename(filename)) if m else None
    create_branch(branch, from_branch=from_branch)
    move_spec(filename, "02_ready_for_dev", "03_ready_for_review")

    message = f"SYSTEM ROLE:\n{role_prompt}\n\nTASK:\n{task_content}"
    result, _ = run_aider(message, model)

    if result == 0:
        stage_and_commit(f"feat: implement {filename}")
        failures = _run_pre_review_checks()
        if failures:
            rework_filename = _write_ci_rework_spec(filename, failures)
            stage_and_commit(f"chore: auto-rework {rework_filename} from CI failures")
            print_error(
                f"{len(failures)} CI check(s) failed. "
                f"Rework ticket written: {rework_filename}. "
                f"Run `sovereign run {rework_filename}` to fix."
            )
        else:
            print_success(f"{filename} complete. Moved to 03_ready_for_review.")
    else:
        print_error(
            f"Agent failed (exit code {result}). "
            "Spec remains in 03_ready_for_review for inspection."
        )


def _append_review_report(spec_path: str, aider_output: str) -> None:
    """Extract the Review Report block from aider output and write it to the spec.

    Handles both pretty-rendered output (no ##) and raw markdown (with ##).
    Replaces any existing ## Review Report section so the spec never accumulates
    stale reports across multiple review cycles.
    """
    # Accept both "## Review Report" (--no-pretty, raw) and "Review Report" (pretty/rendered)
    for marker in ("## Review Report", "Review Report"):
        idx = aider_output.find(marker)
        if idx != -1:
            break
    else:
        return

    report_body = aider_output[idx:].strip()
    # Ensure the section always starts with a level-2 heading in the file
    if not report_body.startswith("## "):
        report_body = f"## {report_body}"

    with open(spec_path) as f:
        content = f.read()
    existing = content.find("## Review Report")
    if existing != -1:
        content = content[:existing].rstrip()
    with open(spec_path, "w") as f:
        f.write(f"{content}\n\n{report_body}\n")


def _extract_verdict(output: str) -> str:
    """Extract the verdict keyword from the Review Report block."""
    m = re.search(r'\*\*Verdict\*\*:\s*\[(PASS|REQUEST CHANGES|REJECT)\]', output)
    return m.group(1) if m else ""


def cmd_review(args: argparse.Namespace) -> None:
    """Trigger the Reviewer agent on a task in 03_ready_for_review.

    Routing based on verdict:
      [PASS]            → 04_dev_done
      [REQUEST CHANGES] → stays in 03_ready_for_review (run `sovereign rework`)
      [REJECT]          → stays in 03_ready_for_review (run `sovereign rework`)
    Pass --no-agent to show the diff only without running the agent.
    """
    filename = args.filename
    branch = slugify(filename)

    try:
        diff = get_diff(get_default_branch(), branch)
    except Exception as e:
        print_error(f"Could not compute diff: {e}")
        return

    console.print(diff, highlight=False)

    if args.no_agent:
        return

    mm = _model_manager()
    mm.ensure_model_loaded("reviewer")
    ollama_model = mm.get_model_for_role("reviewer").removeprefix("ollama/")

    agent_path = os.path.join(TOOL_DIR, "agents", "reviewer.md")
    with open(agent_path) as f:
        role_prompt = f.read()

    spec_path = os.path.join(SPECS_DIR, "03_ready_for_review", filename)
    with open(spec_path) as f:
        spec_content = f.read()

    branch_files = get_branch_files(branch)

    is_rework = "_rework" in filename
    if is_rework:
        note = (
            "NOTE: The diff below is the full branch diff from main. It contains both the"
            " original implementation and the rework changes combined. Evaluate the final"
            " state of the branch against all Acceptance Criteria of the original task —"
            " do NOT flag files that were correctly introduced by the original"
            " implementation."
        )
        user_msg = (
            f"SPEC (rework):\n{spec_content}\n\n"
            "FILES ON BRANCH (ground truth — use this to verify file existence):\n"
            f"{branch_files}\n\n"
            f"{note}\n\n"
            f"FULL BRANCH DIFF:\n{diff}"
        )
    else:
        user_msg = (
            f"SPEC:\n{spec_content}\n\n"
            "FILES ON BRANCH (ground truth — use this to verify file existence):\n"
            f"{branch_files}\n\n"
            f"DIFF:\n{diff}"
        )

    try:
        output = chat(ollama_model, role_prompt, user_msg)
    except RuntimeError as e:
        print_error(str(e))
        return

    console.print(output, highlight=False)
    _append_review_report(spec_path, output)

    # Commit the updated spec (with review report) so that subsequent branch
    # switches (e.g. for rework_01) are not blocked by a dirty working tree.
    try:
        stage_and_commit(f"docs: review report for {filename}")
    except Exception:
        pass  # nothing to commit if report was not appended

    verdict = _extract_verdict(output)

    if verdict == "PASS":
        move_spec(filename, "03_ready_for_review", "04_dev_done")
        print_success(f"Review complete. [PASS] {filename} moved to 04_dev_done.")
    elif verdict in ("REQUEST CHANGES", "REJECT"):
        print_error(
            f"Review complete. [{verdict}] {filename} kept in 03_ready_for_review. "
            f"Run `sovereign rework {filename}` to create a fix ticket."
        )
    else:
        # Verdict not detected — move to 04_dev_done for human inspection
        move_spec(filename, "03_ready_for_review", "04_dev_done")
        print_success(
            f"Review complete (no verdict detected). {filename} moved to 04_dev_done"
            " for inspection."
        )


def cmd_rework(args: argparse.Namespace) -> None:
    """Generate a focused rework ticket from a rejected task's Review Report."""
    filename = args.filename

    for stage in ("04_dev_done", "03_ready_for_review"):
        spec_path = os.path.join(SPECS_DIR, stage, filename)
        if os.path.exists(spec_path):
            break
    else:
        print_error(f"{filename} not found in 04_dev_done or 03_ready_for_review.")
        return

    with open(spec_path) as f:
        spec_content = f.read()

    if "Review Report" not in spec_content:
        print_error(f"No Review Report found in {filename}. Run `sovereign review` first.")
        return

    agent_path = os.path.join(TOOL_DIR, "agents", "rework.md")
    with open(agent_path) as f:
        system_prompt = f.read()

    mm = _model_manager()
    mm.ensure_model_loaded("architect")
    ollama_model = mm.get_model_for_role("architect").removeprefix("ollama/")

    blueprint_path = os.path.join(ARCH_DIR, "project_blueprint.md")
    blueprint_content = ""
    if os.path.exists(blueprint_path):
        with open(blueprint_path) as f:
            blueprint_content = f.read()

    console.print("[bold]Generating rework ticket…[/bold]")
    user_message = f"ORIGINAL SPEC:\n{spec_content}"
    if blueprint_content:
        user_message += (
            "\n\nBLUEPRINT (use Technical Stack for stack-specific mock hints):\n"
            f"{blueprint_content}"
        )
    try:
        rework_content = chat(ollama_model, system_prompt, user_message)
    except RuntimeError as e:
        print_error(str(e))
        return

    rework_filename = _next_rework_filename(filename)
    rework_path = os.path.join(SPECS_DIR, "02_ready_for_dev", rework_filename)
    os.makedirs(os.path.dirname(rework_path), exist_ok=True)
    with open(rework_path, "w") as f:
        f.write(rework_content)

    print_success(f"Rework ticket created: {rework_filename} in 02_ready_for_dev.")


def cmd_scaffold(args: argparse.Namespace) -> None:
    """Scaffold the project structure directly from the blueprint. No LLM involved."""
    from scaffolding.engine import scaffold

    blueprint_path = args.blueprint or os.path.join(ARCH_DIR, "project_blueprint.md")
    if not os.path.exists(blueprint_path):
        print_error(
            f"Blueprint not found: {blueprint_path}\n"
            "Run `sovereign init` first, then fill in architecture/project_blueprint.md."
        )
        return

    with open(blueprint_path) as f:
        blueprint_content = f.read()

    if "<framework>" in blueprint_content or "(<framework>" in blueprint_content:
        print_error(
            "Blueprint has not been filled in yet.\n"
            "Edit architecture/project_blueprint.md before running scaffold."
        )
        return

    create_branch("init_project")
    console.print("[bold]Scaffolding project from blueprint…[/bold]")

    scaffold(blueprint_content)

    stage_and_commit("chore: scaffold project structure [sovereign]")

    from core.git_utils import merge_and_delete_branch
    merge_and_delete_branch("init_project")

    print_success("Project scaffolded and merged into [cyan]main[/cyan].")


def cmd_approve(args: argparse.Namespace) -> None:
    """Human gate 2 — accept a reviewed task, merge its branch, and close it."""
    filename = args.filename
    branch = slugify(filename)
    try:
        merge_and_delete_branch(branch)
    except Exception as e:
        print_error(f"Git merge failed: {e}")
        return

    move_spec(filename, "04_dev_done", "05_done")

    # Rework ticket: retire the superseded original branch and close both tickets
    if _REWORK_RE.match(filename):
        original = _original_filename(filename)
        original_branch = slugify(original)
        delete_branch(original_branch)
        original_path = os.path.join(SPECS_DIR, "04_dev_done", original)
        if os.path.exists(original_path):
            move_spec(original, "04_dev_done", "05_done")
            print_success(f"Original task {original} also moved to 05_done.")

    stage_and_commit(f"chore: approve {filename}")
    print_success(f"{filename} approved, merged, and moved to 05_done.")


def cmd_reject(args: argparse.Namespace) -> None:
    """Send a task back to 01_backlog with optional feedback."""
    filename = args.filename
    for stage in ("03_ready_for_review", "04_dev_done"):
        source = os.path.join(SPECS_DIR, stage, filename)
        if os.path.exists(source):
            move_spec(filename, stage, "01_backlog")
            if args.reason:
                append_feedback_to_spec(filename, "01_backlog", args.reason)
            print_success(f"{filename} rejected and moved back to 01_backlog.")
            return
    print_error(f"{filename} not found in 03_ready_for_review or 04_dev_done.")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sovereign",
        description="SovereignSpecAI — local-first AI code factory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    subparsers.add_parser(
        "init", help="Initialize the Kanban structure in the parent repo."
    ).set_defaults(func=cmd_init)

    # scaffold
    scaffold_parser = subparsers.add_parser(
        "scaffold",
        help="Scaffold the project structure from the blueprint. Run once after `init`.",
    )
    scaffold_parser.add_argument(
        "--blueprint",
        default=None,
        metavar="FILE",
        help="Path to the blueprint file (default: architecture/project_blueprint.md).",
    )
    scaffold_parser.set_defaults(func=cmd_scaffold)

    # architect
    architect_parser = subparsers.add_parser(
        "architect", help="Analyze a blueprint and generate prioritized tasks in 01_backlog."
    )
    architect_parser.add_argument(
        "--blueprint",
        default=None,
        metavar="FILE",
        help="Path to the blueprint file (default: architecture/project_blueprint.md).",
    )
    architect_parser.set_defaults(func=cmd_architect)

    # list
    list_parser = subparsers.add_parser("list", help="List specs in a single Kanban stage.")
    list_parser.add_argument(
        "stage",
        nargs="?",
        default="01_backlog",
        help="Stage to list (default: 01_backlog).",
    )
    list_parser.set_defaults(func=cmd_list)

    # kanban
    subparsers.add_parser(
        "kanban", help="Show all Kanban columns and their tasks at a glance."
    ).set_defaults(func=cmd_kanban)

    # pick  [human gate 1]
    pick_parser = subparsers.add_parser(
        "pick", help="[Human] Promote a task from 01_backlog to 02_ready_for_dev."
    )
    pick_parser.add_argument("filename", help="Spec filename in 01_backlog.")
    pick_parser.set_defaults(func=cmd_pick)

    # run
    run_parser = subparsers.add_parser(
        "run", help="Trigger the Developer agent on a task in 02_ready_for_dev."
    )
    run_parser.add_argument("filename", help="Spec filename in 02_ready_for_dev.")
    run_parser.add_argument(
        "--force", action="store_true",
        help="Run even if there are unmerged branches from previous tasks."
    )
    run_parser.set_defaults(func=cmd_run)

    # review
    review_parser = subparsers.add_parser(
        "review",
        help="Trigger the Reviewer agent on a task in 03_ready_for_review. Moves to 04_dev_done.",
    )
    review_parser.add_argument("filename", help="Spec filename in 03_ready_for_review.")
    review_parser.add_argument(
        "--no-agent", action="store_true", help="Print the diff only, skip the Reviewer agent."
    )
    review_parser.set_defaults(func=cmd_review)

    # rework
    rework_parser = subparsers.add_parser(
        "rework", help="Generate a focused rework ticket from a rejected task's Review Report."
    )
    rework_parser.add_argument(
        "filename", help="Spec filename in 04_dev_done (must contain a Review Report)."
    )
    rework_parser.set_defaults(func=cmd_rework)

    # approve  [human gate 2]
    approve_parser = subparsers.add_parser(
        "approve", help="[Human] Merge the feature branch and move the task to 05_done."
    )
    approve_parser.add_argument("filename", help="Spec filename in 04_dev_done.")
    approve_parser.set_defaults(func=cmd_approve)

    # reject
    reject_parser = subparsers.add_parser(
        "reject", help="Send a task back to 01_backlog with optional feedback."
    )
    reject_parser.add_argument(
        "filename", help="Spec filename in 03_ready_for_review or 04_dev_done."
    )
    reject_parser.add_argument("--reason", default="", metavar="TEXT", help="Rejection feedback.")
    reject_parser.set_defaults(func=cmd_reject)

    return parser
