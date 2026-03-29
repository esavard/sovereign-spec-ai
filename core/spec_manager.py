import os
import shutil

from git import Repo

from core import PROJECT_ROOT, TOOL_DIR

SPECS_DIR: str = os.path.join(PROJECT_ROOT, "specs")
ARCH_DIR: str = os.path.join(PROJECT_ROOT, "architecture")

STAGES: list[str] = [
    "01_backlog",
    "02_ready_for_dev",
    "03_ready_for_review",
    "04_dev_done",
    "05_done",
]

_DEFAULT_BLUEPRINT = """\
# Project Blueprint

## Technical Stack
- (define your stack here)

## Domain Model
```mermaid
graph TD
    A --> B
```
"""


def init_env() -> None:
    """Initialize the Kanban folder structure, default blueprint, .gitignore, and .aiderignore."""
    if not os.path.exists(os.path.join(PROJECT_ROOT, ".git")):
        raise RuntimeError(
            f"No git repository found at PROJECT_ROOT: {PROJECT_ROOT}\n"
            "Run `git init` in the parent project before running `sovereign init`."
        )
    for stage in STAGES:
        os.makedirs(os.path.join(SPECS_DIR, stage), exist_ok=True)

    os.makedirs(ARCH_DIR, exist_ok=True)

    blueprint_path = os.path.join(ARCH_DIR, "project_blueprint.md")
    if not os.path.exists(blueprint_path):
        with open(blueprint_path, "w") as f:
            f.write(_DEFAULT_BLUEPRINT)

    tool_dir_name = os.path.basename(TOOL_DIR)

    gitignore_path = os.path.join(PROJECT_ROOT, ".gitignore")
    entry = f"\n# SovereignSpecAI Tooling\n{tool_dir_name}/\n"
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            content = f.read()
        if f"{tool_dir_name}/" not in content:
            with open(gitignore_path, "a") as f:
                f.write(entry)
    else:
        with open(gitignore_path, "w") as f:
            f.write(entry)

    aiderignore_path = os.path.join(PROJECT_ROOT, ".aiderignore")
    if not os.path.exists(aiderignore_path):
        with open(aiderignore_path, "w") as f:
            f.write(f"/{tool_dir_name}/\n")
            f.write("architecture*/\n")

    _ensure_initial_commit()


def _ensure_initial_commit() -> None:
    """Create an initial commit if the repository has no commits yet."""
    repo = Repo(PROJECT_ROOT)
    try:
        repo.active_branch  # raises TypeError on empty repo
        return  # already has commits, nothing to do
    except TypeError:
        pass

    repo.git.add(A=True)
    repo.index.commit("chore: initial project structure [sovereign init]")


def list_specs(stage: str) -> list[str]:
    path = os.path.join(SPECS_DIR, stage)
    if not os.path.exists(path):
        return []
    return sorted(f for f in os.listdir(path) if f.endswith(".md"))


def read_spec(filename: str, stage: str) -> str:
    path = os.path.join(SPECS_DIR, stage, filename)
    with open(path) as f:
        return f.read()


def append_feedback_to_spec(filename: str, stage: str, feedback: str) -> None:
    path = os.path.join(SPECS_DIR, stage, filename)
    with open(path, "a") as f:
        f.write(f"\n\n## Rejection Feedback\n{feedback}\n")


def move_spec(filename: str, from_stage: str, to_stage: str) -> None:
    source = os.path.join(SPECS_DIR, from_stage, filename)
    dest_dir = os.path.join(SPECS_DIR, to_stage)
    os.makedirs(dest_dir, exist_ok=True)
    shutil.move(source, os.path.join(dest_dir, filename))
