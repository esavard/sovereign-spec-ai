import argparse
import json
import os
import re

import yaml

from cli.views import console, print_error, print_spec_list, print_success
from core import PROJECT_ROOT, TOOL_DIR
from core.aider_runner import run_aider
from core.git_utils import (
    create_branch,
    get_default_branch,
    get_diff,
    merge_and_delete_branch,
    slugify,
    stage_and_commit,
)
from core.ollama_client import chat
from core.spec_manager import (
    ARCH_DIR,
    SPECS_DIR,
    append_feedback_to_spec,
    init_env,
    list_specs,
    move_spec,
    read_spec,
)


def _load_config() -> dict:
    config_path = os.path.join(TOOL_DIR, "factory_config.yaml")
    with open(config_path) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> None:
    init_env()
    print_success("Environment initialized.")


def cmd_architect(args: argparse.Namespace) -> None:
    config = _load_config()
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

    model_name = config["default_model"]
    # Strip "ollama/" prefix if present — ollama_client uses the bare model name
    ollama_model = model_name.removeprefix("ollama/")

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

    # Safety net: re-index tasks sequentially to eliminate any duplicate indices,
    # then enforce the two-digit prefix on every filename.
    task_plan.sort(key=lambda t: t.get("index", 0))
    for seq, task in enumerate(task_plan):
        task["index"] = seq
        fname = task.get("filename", "task.md")
        # Strip any existing leading digits+underscore, then reapply from seq
        bare = re.sub(r"^\d+_", "", fname)
        task["filename"] = f"{seq:02d}_{bare}"

    # --- Phase 2: Task authoring — one aider call per task ---
    task_agent_path = os.path.join(TOOL_DIR, "agents", "architect_task.md")
    with open(task_agent_path) as f:
        task_role_prompt = f.read()

    failed = 0
    for task in sorted(task_plan, key=lambda t: t.get("index", 0)):
        filename = task.get("filename", "")
        title = task.get("title", filename)
        console.print(f"  Writing [cyan]{filename}[/cyan] — {title}")

        filepath = f"{backlog_rel}/{filename}"
        message = (
            f"SYSTEM ROLE:\n{task_role_prompt}\n\n"
            f"OUTPUT FILEPATH (use this verbatim — do NOT change it): {filepath}\n\n"
            f"TASK PLAN ENTRY:\n{json.dumps(task, indent=2)}\n\n"
            f"BLUEPRINT (for context):\n{blueprint_content}"
        )

        result = run_aider(message, model_name)
        if result != 0:
            print_error(f"Failed to create {filename} (exit code {result}).")
            failed += 1

    if failed == 0:
        print_success(f"Architect complete. {len(task_plan)} task(s) created in 01_backlog.")
    else:
        print_error(f"Architect finished with {failed} failure(s). Check output above.")


def cmd_list(args: argparse.Namespace) -> None:
    files = list_specs(args.stage)
    print_spec_list(args.stage, files)


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
    config = _load_config()
    filename = args.filename

    agent_path = os.path.join(TOOL_DIR, "agents", "developer.md")
    with open(agent_path) as f:
        role_prompt = f.read()

    task_content = read_spec(filename, "02_ready_for_dev")
    branch = slugify(filename)
    create_branch(branch)
    move_spec(filename, "02_ready_for_dev", "03_ready_for_review")

    message = f"SYSTEM ROLE:\n{role_prompt}\n\nTASK:\n{task_content}"
    result = run_aider(message, config["default_model"])

    if result == 0:
        print_success(f"{filename} complete. Moved to 03_ready_for_review.")
    else:
        print_error(
            f"Agent failed (exit code {result}). "
            "Spec remains in 03_ready_for_review for inspection."
        )


def cmd_review(args: argparse.Namespace) -> None:
    """Trigger the Reviewer agent on a task in 03_ready_for_review.

    On completion the spec is automatically moved to 04_dev_done.
    Pass --no-agent to show the diff only without running the agent.
    """
    config = _load_config()
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

    agent_path = os.path.join(TOOL_DIR, "agents", "reviewer.md")
    with open(agent_path) as f:
        role_prompt = f.read()

    spec_path = os.path.join(SPECS_DIR, "03_ready_for_review", filename)
    message = f"SYSTEM ROLE:\n{role_prompt}\n\nDIFF:\n{diff}"
    result = run_aider(message, config["default_model"], extra_args=["--read", spec_path])

    if result == 0:
        move_spec(filename, "03_ready_for_review", "04_dev_done")
        print_success(f"Review complete. {filename} moved to 04_dev_done.")
    else:
        print_error(
            f"Reviewer agent failed (exit code {result}). "
            "Spec remains in 03_ready_for_review."
        )


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
    stage_and_commit(f"chore: approve {filename}")
    print_success(f"{filename} approved, merged, and moved to 05_done.")


def cmd_reject(args: argparse.Namespace) -> None:
    """Send a task back to 01_backlog with optional feedback."""
    filename = args.filename
    move_spec(filename, "03_ready_for_review", "01_backlog")
    if args.reason:
        append_feedback_to_spec(filename, "01_backlog", args.reason)
    print_success(f"{filename} rejected and moved back to 01_backlog.")


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
    list_parser = subparsers.add_parser("list", help="List specs in a Kanban stage.")
    list_parser.add_argument(
        "stage",
        nargs="?",
        default="01_backlog",
        help="Stage to list (default: 01_backlog).",
    )
    list_parser.set_defaults(func=cmd_list)

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
    reject_parser.add_argument("filename", help="Spec filename in 03_ready_for_review.")
    reject_parser.add_argument("--reason", default="", metavar="TEXT", help="Rejection feedback.")
    reject_parser.set_defaults(func=cmd_reject)

    return parser
