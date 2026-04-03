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

## Project Name
(the name of the project, e.g. "MyTaskApp")

## Domain Description
(2-3 sentences: what does this system do? Who uses it? What problem does it solve?)

## Technical Stack
- (framework / runtime)
- (database / persistence)
- (test runner)

## Technical Constraints
- (what NOT to do — e.g. "no backend", "no SSR", "mock IndexedDB in tests")

## Node Legend
All Mermaid nodes MUST use these prefixes so the Architect agent can categorize them unambiguously:

| Prefix | DDD Type           | Example                  |
|--------|--------------------|--------------------------|
| `C_`   | Command            | `C_AddTask`              |
| `A_`   | Aggregate          | `A_Task`                 |
| `E_`   | Entity             | `E_TaskEntry`            |
| `DE_`  | Domain Event       | `DE_TaskAdded`           |
| `P_`   | Policy / Saga      | `P_PersistToIndexedDB`   |
| `R_`   | Repository         | `R_TaskRepo`             |
| `RM_`  | Read Model / Store | `RM_TaskList`            |
| `DB_`  | Infrastructure     | `DB_Dexie`               |

## Domain Model
```mermaid
graph TD
    %% Commands
    C_Example[Command: Example] --> A_Example[Aggregate: Example]

    %% Domain Events
    A_Example -->|Publishes| DE_ExampleDone[Event: ExampleDone]

    %% Policies
    DE_ExampleDone --> P_Example[Policy: Example]
    P_Example -->|Calls| R_Example[Repository: Example]

    %% Infrastructure
    R_Example --> DB_Example[Infrastructure: Example DB]

    %% Read Models
    DE_ExampleDone --> RM_Example[ReadModel: ExampleStore]
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
    entry = f"\n# SovereignSpecAI Tooling\n{tool_dir_name}/\n.aider*\n"
    if os.path.exists(gitignore_path):
        with open(gitignore_path) as f:
            content = f.read()
        additions = []
        if f"{tool_dir_name}/" not in content:
            additions.append(f"\n# SovereignSpecAI Tooling\n{tool_dir_name}/\n")
        if ".aider*" not in content:
            additions.append(".aider*\n")
        if additions:
            with open(gitignore_path, "a") as f:
                f.writelines(additions)
    else:
        with open(gitignore_path, "w") as f:
            f.write(entry)

    aiderignore_path = os.path.join(PROJECT_ROOT, ".aiderignore")
    aiderignore_entries = [f"/{tool_dir_name}/\n", "architecture*/\n", "specs/\n"]
    if os.path.exists(aiderignore_path):
        with open(aiderignore_path) as f:
            existing = f.read()
        missing = [e for e in aiderignore_entries if e.strip() not in existing]
        if missing:
            with open(aiderignore_path, "a") as f:
                f.writelines(missing)
    else:
        with open(aiderignore_path, "w") as f:
            f.writelines(aiderignore_entries)

    # Remove tool dir from git index if it was previously tracked.
    # .gitignore only prevents future tracking; already-tracked entries must be
    # explicitly removed from the index (--cached leaves the files on disk).
    repo = Repo(PROJECT_ROOT)
    try:
        repo.git.rm("--cached", "--ignore-unmatch", "-r", tool_dir_name)
    except Exception:
        pass

    _commit_init_files(repo)


def _commit_init_files(repo: Repo) -> None:
    """Stage and commit all sovereign init artefacts.

    Runs on every `sovereign init` so that newly created files (.gitignore,
    architecture/, specs/) are committed even when the repository already has
    prior commits (e.g. an empty initial commit).
    """
    repo.git.add(A=True)
    try:
        # On a repo with commits, skip if nothing changed.
        if not repo.index.diff("HEAD") and not repo.untracked_files:
            return
    except Exception:
        pass  # zero-commit repo has no HEAD — always commit
    repo.index.commit("chore: sovereign init [sovereign]")


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
