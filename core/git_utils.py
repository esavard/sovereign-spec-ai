import re

from git import Repo

from core import PROJECT_ROOT


def get_repo() -> Repo:
    return Repo(PROJECT_ROOT)


def slugify(text: str) -> str:
    text = text.lower().replace(".md", "").strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "_", text)


def _ensure_has_commits() -> None:
    """Create an initial commit if the repo has none, so branching is possible."""
    repo = get_repo()
    try:
        repo.active_branch  # raises TypeError on a repo with zero commits
        _ = list(repo.iter_commits())  # may be empty even if branch exists
    except (TypeError, ValueError):
        pass
    else:
        return  # repo already has commits

    # Empty repo — stage everything and create an initial commit.
    repo.git.add(A=True)
    repo.index.commit("chore: initial commit [sovereign]")


def get_default_branch() -> str:
    """Return the name of the default branch (main, master, etc.).

    Checks for common default branch names rather than relying on the currently
    checked-out branch, which may be a feature branch.
    """
    repo = get_repo()
    branch_names = [b.name for b in repo.branches]

    for candidate in ("main", "master"):
        if candidate in branch_names:
            return candidate

    if branch_names:
        return branch_names[0]

    raise RuntimeError(
        "No branches found in repository. Run `uv run sovereign init` first."
    )


def create_branch(name: str) -> None:
    _ensure_has_commits()
    default = get_default_branch()
    repo = get_repo()
    try:
        repo.git.checkout(default)
        repo.git.checkout("-b", name)
    except Exception:
        repo.git.checkout(name)


def get_current_branch() -> str:
    return get_repo().active_branch.name


def get_diff(base: str, branch: str) -> str:
    return get_repo().git.diff(base, branch, "--", ".", ":!specs/", ":!architecture/")


def merge_and_delete_branch(branch: str) -> None:
    default = get_default_branch()
    repo = get_repo()
    repo.git.checkout(default)
    repo.git.merge(branch)
    repo.git.branch("-d", branch)


def stage_and_commit(message: str) -> None:
    repo = get_repo()
    repo.git.add(A=True)
    repo.index.commit(message)
