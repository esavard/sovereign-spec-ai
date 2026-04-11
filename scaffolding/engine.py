"""Deterministic scaffolding engine for task 00 (init_project).

Orchestrates four phases:
  A — Render config file templates (package.json, go.mod, …)
  B — Apply DDD directory structure + .keep files
  C — Build and write .gitignore
  D — Write monorepo Makefile (only when multiple tech roles are present)

The blueprint's ``Project Structure`` section, when present, overrides the
DDD template for phase B.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

from scaffolding.gitignore import GitignoreFetcher
from scaffolding.registry import Stack, detect_stacks

# Resolved at import time so tests can monkeypatch scaffolding.engine.PROJECT_ROOT.
try:
    from core import PROJECT_ROOT as _PROJECT_ROOT
except ImportError:          # allow importing in tests without the full app
    _PROJECT_ROOT = str(Path.cwd())

PROJECT_ROOT: str = _PROJECT_ROOT

_SCAFFOLDING_DIR = Path(__file__).parent
_TEMPLATES_DIR = _SCAFFOLDING_DIR / "templates"
_DDD_DIR = _SCAFFOLDING_DIR / "ddd"

# Roles that occupy a named sub-directory in a monorepo.
_ROLE_DIRS: dict[str, str] = {
    "frontend": "frontend",
    "backend": "backend",
    "mobile": "mobile",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scaffold(spec_content: str) -> None:
    """Run all scaffold phases for task-00 spec *spec_content*."""
    project_name = _extract_section(spec_content, "Project Name")
    stack_text = _extract_section(spec_content, "Technical Stack")
    project_structure = _extract_section(spec_content, "Project Structure")

    stacks = detect_stacks(stack_text)
    if not stacks:
        from rich.console import Console
        Console().print(
            "[yellow]Warning: no recognised stack in Technical Stack. "
            "Applying base DDD structure only.[/yellow]"
        )
        stacks = [Stack(id="base", role="generic", templates=[], ddd="base", gitignore=[])]

    project_root = Path(PROJECT_ROOT)
    roots = _compute_roots(stacks, project_root)

    template_vars = _build_template_vars(project_name, stacks)

    # Phase A — config file templates
    for stack in stacks:
        if stack.templates:
            root = roots.get(stack.role, project_root)
            _render_templates(stack, root, template_vars)

    # Phase B — DDD directory structure
    _apply_ddd_structure(stacks, roots, project_root, project_structure, template_vars)

    # Phase C — .gitignore
    fetcher = GitignoreFetcher()
    # TOOL_DIR is the sidecar; its name relative to PROJECT_ROOT is what to ignore.
    sidecar_name = _SCAFFOLDING_DIR.parent.name
    gitignore_content = fetcher.build(stacks, sidecar_dir=sidecar_name)
    _merge_gitignore(project_root / ".gitignore", gitignore_content)

    # Phase D — root Makefile (monorepo only)
    active_roles = {s.role for s in stacks if s.role in _ROLE_DIRS}
    if len(active_roles) > 1:
        _render_root_makefile(stacks, roots, project_root, template_vars)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_section(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)"
    m = re.search(pattern, text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _compute_roots(stacks: list[Stack], project_root: Path) -> dict[str, Path]:
    """Return {role: Path} mapping.

    Single active role → flat structure (project_root itself).
    Multiple active roles → sub-directory per role.
    """
    active = [s for s in stacks if s.role in _ROLE_DIRS]
    if len(active) <= 1:
        return {s.role: project_root for s in stacks}
    # Stacks with a named role dir get their own subdirectory.
    # Roles like "database" have no filesystem root of their own.
    return {
        s.role: (project_root / _ROLE_DIRS[s.role] if s.role in _ROLE_DIRS else project_root)
        for s in stacks
    }


def _build_template_vars(project_name: str, stacks: list[Stack]) -> dict:
    project_slug = _slugify(project_name)
    vars_: dict = {
        "project_name": project_name,
        "project_slug": project_slug,
        "app_package": f"com.example.{re.sub(r'[^a-z0-9]', '', project_slug)}",
        "package_path": f"com/example/{re.sub(r'[^a-z0-9]', '', project_slug)}",
        "go_module": f"github.com/example/{project_slug}",
        # monorepo flags for the Makefile template
        "has_frontend": any(s.role == "frontend" for s in stacks),
        "has_backend": any(s.role == "backend" for s in stacks),
        "has_mobile": any(s.role == "mobile" for s in stacks),
        "frontend_pm": "npm",
    }
    for stack in stacks:
        vars_.update(stack.vars)
        if stack.role == "frontend":
            vars_["frontend_pm"] = stack.vars.get("package_manager", "npm")
    return vars_


def _render_templates(stack: Stack, root: Path, vars_: dict) -> None:
    for tpl_dir_name in stack.templates:
        tpl_dir = _TEMPLATES_DIR / tpl_dir_name
        if not tpl_dir.exists():
            continue
        env = Environment(
            loader=FileSystemLoader(str(tpl_dir)),
            keep_trailing_newline=True,
        )
        for tpl_path in tpl_dir.rglob("*.j2"):
            rel = tpl_path.relative_to(tpl_dir)
            # Strip the .j2 extension to get the target filename.
            target_rel = Path(str(rel)[:-3])
            target = root / target_rel
            target.parent.mkdir(parents=True, exist_ok=True)
            template = env.get_template(str(rel))
            target.write_text(template.render(**vars_), encoding="utf-8")


def _apply_ddd_structure(
    stacks: list[Stack],
    roots: dict[str, Path],
    project_root: Path,
    project_structure: str,
    vars_: dict,
) -> None:
    if project_structure:
        # Blueprint overrides DDD templates — parse the freeform structure block.
        dirs = _parse_project_structure(project_structure)
        _create_dirs(dirs, project_root, vars_)
        return

    for stack in stacks:
        if not stack.ddd:
            continue
        root = roots.get(stack.role, project_root)
        dirs = _load_ddd_dirs(stack.ddd)
        _create_dirs(dirs, root, vars_)


def _load_ddd_dirs(ddd_key: str) -> list[str]:
    """Load directory list from ddd/<ddd_key>.yaml."""
    yaml_path = _DDD_DIR / f"{ddd_key}.yaml"
    if not yaml_path.exists():
        yaml_path = _DDD_DIR / "base.yaml"
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    return [d.rstrip("/") for d in data.get("dirs", [])]


def _create_dirs(dirs: list[str], root: Path, vars_: dict) -> None:
    """Create each directory under *root*.

    A ``.keep`` file is added only when the directory is empty after creation
    (idempotent — existing files are not touched).
    """
    env = Environment()
    for raw in dirs:
        rendered = env.from_string(raw).render(**vars_)
        full = root / rendered
        full.mkdir(parents=True, exist_ok=True)
        keep = full / ".keep"
        if not any(full.iterdir()):
            keep.touch()


def _parse_project_structure(text: str) -> list[str]:
    """Convert a freeform indented directory tree into a flat list of paths.

    Handles the format used in project_blueprint.md::

        src/
          lib/
            domain/     # comment
          routes/
        tests/
    """
    # Strip optional code-fence wrapper
    text = re.sub(r"^```[^\n]*\n?|```$", "", text.strip(), flags=re.MULTILINE)

    dirs: list[str] = []
    stack: list[tuple[int, str]] = []   # (indent, segment)

    for line in text.splitlines():
        stripped = line.rstrip()
        if not stripped:
            continue
        # Remove inline comments
        stripped = re.sub(r"\s*#.*$", "", stripped).rstrip()
        if not stripped:
            continue
        # Only keep lines that look like directories (end with / or have no extension)
        name = stripped.lstrip()
        if not name.endswith("/") and "." in name:
            continue   # looks like a file reference, skip
        name = name.rstrip("/")
        indent = len(stripped) - len(name) - (1 if stripped.endswith("/") else 0)
        indent = len(line) - len(line.lstrip())

        # Pop stack until we find the parent
        while stack and stack[-1][0] >= indent:
            stack.pop()

        stack.append((indent, name))
        path = "/".join(seg for _, seg in stack)
        dirs.append(path)

    return dirs


def _merge_gitignore(gitignore_path: Path, new_content: str) -> None:
    """Write *new_content* to *gitignore_path*, preserving any pre-existing content.

    Sections are identified by their ``### Header ###`` line. A section already
    present in the file is not duplicated. This ensures entries written by
    ``sovereign init`` (e.g. the sidecar directory) are never lost.
    """
    if not gitignore_path.exists():
        gitignore_path.write_text(new_content, encoding="utf-8")
        return

    existing = gitignore_path.read_text(encoding="utf-8")
    new_sections = new_content.split("\n\n")
    parts = [existing.rstrip()]
    for section in new_sections:
        header = section.split("\n")[0]
        if header not in existing:
            parts.append(section)
    gitignore_path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def _render_root_makefile(
    stacks: list[Stack],
    roots: dict[str, Path],
    project_root: Path,
    vars_: dict,
) -> None:
    tpl_path = _TEMPLATES_DIR / "Makefile.j2"
    if not tpl_path.exists():
        return
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("Makefile.j2")
    (project_root / "Makefile").write_text(
        template.render(**vars_), encoding="utf-8"
    )