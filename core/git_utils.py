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


_AIDER_ARTIFACTS = (
    ".aider.chat.history.md",
    ".aider.input.history",
    ".aider.tags.cache.v4/cache.db",
)


def _clear_aider_artifacts(repo: Repo) -> None:
    """Remove aider artifacts from the index and working tree.

    Handles three states: clean, tracked-with-changes, and conflict (needs merge).
    Aider state is never precious — it is safe to discard unconditionally.
    Also drops any leftover stash entry from a previous failed pop.
    """
    import os

    # Drop stash left behind by a previous failed stash pop, if any.
    try:
        repo.git.stash("drop")
    except Exception:
        pass

    # Remove from index (covers both normal and conflicted index entries).
    for path in _AIDER_ARTIFACTS:
        try:
            repo.git.rm("-f", "--cached", "--ignore-unmatch", path)
        except Exception:
            pass

    # Remove from working tree.
    for path in _AIDER_ARTIFACTS:
        full = os.path.join(str(repo.working_dir), path)
        if os.path.exists(full):
            try:
                os.remove(full)
            except Exception:
                pass

    # If .gitignore is in a conflict state, keep ours and re-stage it.
    try:
        if ".gitignore" in repo.index.unmerged_blobs():
            repo.git.checkout("--ours", ".gitignore")
            repo.git.add(".gitignore")
    except Exception:
        pass


def create_branch(name: str, from_branch: str | None = None) -> None:
    _ensure_has_commits()
    base = from_branch or get_default_branch()
    repo = get_repo()
    _clear_aider_artifacts(repo)
    try:
        repo.git.checkout(base)
        repo.git.checkout("-b", name)
    except Exception:
        repo.git.checkout(name)


def delete_branch(name: str) -> None:
    """Force-delete a local branch without merging (used to retire superseded branches)."""
    repo = get_repo()
    try:
        repo.git.branch("-D", name)
    except Exception:
        pass


def get_current_branch() -> str:
    return get_repo().active_branch.name


def get_unmerged_branches() -> list[str]:
    """Return local branches that have not been merged into the default branch."""
    repo = get_repo()
    default = get_default_branch()
    merged = {b.strip() for b in repo.git.branch("--merged", default).splitlines()}
    return [
        b.name for b in repo.branches
        if b.name != default and b.name not in merged
    ]


def get_diff(base: str, branch: str) -> str:
    return get_repo().git.diff(
        base, branch, "--", ".",
        ":!specs/", ":!architecture/", ":!.aider*",
    )


def get_branch_files(branch: str) -> str:
    """Return a sorted newline-separated list of files tracked on a branch,
    excluding specs/, architecture/, and aider artifacts."""
    repo = get_repo()
    output = repo.git.ls_tree("-r", "--name-only", branch)
    lines = [
        path for path in output.splitlines()
        if not path.startswith("specs/")
        and not path.startswith("architecture/")
        and not path.startswith("sovereign-spec-ai/")
        and not path.startswith(".aider")
    ]
    return "\n".join(sorted(lines))


def merge_and_delete_branch(branch: str) -> None:
    default = get_default_branch()
    repo = get_repo()
    _clear_aider_artifacts(repo)
    repo.git.checkout(default)
    repo.git.merge(branch)
    repo.git.branch("-d", branch)


def stage_and_commit(message: str) -> None:
    repo = get_repo()
    # Untrack aider artifacts so they never accumulate in project history.
    for pattern in (".aider.chat.history.md", ".aider.input.history", ".aider.tags.cache.v4"):
        try:
            repo.git.rm("-r", "--cached", "--force", "--ignore-unmatch", pattern)
        except Exception:
            pass
    repo.git.add(A=True)
    repo.index.commit(message)
