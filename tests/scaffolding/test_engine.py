"""Integration tests for scaffolding/engine.py.

Each test uses a tmp_path fixture as the PROJECT_ROOT so that no real
filesystem outside the temp directory is touched.
"""

from __future__ import annotations

import urllib.error
from pathlib import Path
from unittest.mock import patch

import scaffolding.engine as engine
from scaffolding.engine import (
    _build_template_vars,
    _compute_roots,
    _load_ddd_dirs,
    _parse_project_structure,
    scaffold,
)
from scaffolding.registry import Stack

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _stack(id_: str, role: str, templates=None, ddd="", gitignore=None, vars_=None):
    return Stack(
        id=id_,
        role=role,
        templates=templates or [],
        ddd=ddd,
        gitignore=gitignore or [],
        vars=vars_ or {},
    )


def _patch_root(tmp_path: Path):
    """Context manager: patch PROJECT_ROOT to *tmp_path*."""
    return patch.object(engine, "PROJECT_ROOT", str(tmp_path))


def _offline():
    """Context manager: make all HTTP calls raise URLError (offline mode)."""
    return patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline"))


# ---------------------------------------------------------------------------
# _compute_roots
# ---------------------------------------------------------------------------

class TestComputeRoots:
    def test_single_frontend_is_flat(self, tmp_path):
        stacks = [_stack("sveltekit", "frontend")]
        roots = _compute_roots(stacks, tmp_path)
        assert roots["frontend"] == tmp_path

    def test_single_backend_is_flat(self, tmp_path):
        stacks = [_stack("go-beego", "backend")]
        roots = _compute_roots(stacks, tmp_path)
        assert roots["backend"] == tmp_path

    def test_frontend_and_backend_monorepo(self, tmp_path):
        stacks = [_stack("sveltekit", "frontend"), _stack("go-beego", "backend")]
        roots = _compute_roots(stacks, tmp_path)
        assert roots["frontend"] == tmp_path / "frontend"
        assert roots["backend"] == tmp_path / "backend"

    def test_database_role_does_not_trigger_monorepo_by_itself(self, tmp_path):
        stacks = [_stack("sveltekit", "frontend"), _stack("postgresql", "database")]
        roots = _compute_roots(stacks, tmp_path)
        # Only frontend is an "active" role → flat
        assert roots["frontend"] == tmp_path

    def test_three_roles(self, tmp_path):
        stacks = [
            _stack("sveltekit", "frontend"),
            _stack("go-beego", "backend"),
            _stack("kotlin-android", "mobile"),
        ]
        roots = _compute_roots(stacks, tmp_path)
        assert roots["frontend"] == tmp_path / "frontend"
        assert roots["backend"] == tmp_path / "backend"
        assert roots["mobile"] == tmp_path / "mobile"


# ---------------------------------------------------------------------------
# _load_ddd_dirs
# ---------------------------------------------------------------------------

class TestLoadDddDirs:
    def test_sveltekit_contains_domain(self):
        dirs = _load_ddd_dirs("frontend/sveltekit")
        assert "src/lib/domain" in dirs

    def test_sveltekit_contains_events(self):
        dirs = _load_ddd_dirs("frontend/sveltekit")
        assert "src/lib/events" in dirs

    def test_sveltekit_contains_tests(self):
        dirs = _load_ddd_dirs("frontend/sveltekit")
        assert "tests" in dirs

    def test_go_beego_contains_domain(self):
        dirs = _load_ddd_dirs("backend/go-beego")
        assert "domain/aggregates" in dirs

    def test_go_beego_contains_infrastructure(self):
        dirs = _load_ddd_dirs("backend/go-beego")
        assert "infrastructure/repositories" in dirs

    def test_go_beego_contains_presentation(self):
        dirs = _load_ddd_dirs("backend/go-beego")
        assert "presentation/controllers" in dirs

    def test_android_kotlin_contains_domain(self):
        dirs = _load_ddd_dirs("mobile/android-kotlin")
        # dirs contain Jinja2 placeholders; check structural presence
        assert any("domain" in d for d in dirs)

    def test_android_kotlin_contains_presentation(self):
        dirs = _load_ddd_dirs("mobile/android-kotlin")
        assert any("presentation" in d for d in dirs)

    def test_android_kotlin_uses_kotlin_source_dir(self):
        dirs = _load_ddd_dirs("mobile/android-kotlin")
        assert all("/java/" not in d for d in dirs)
        assert any("/kotlin/" in d for d in dirs)

    def test_unknown_key_falls_back_to_base(self):
        dirs = _load_ddd_dirs("nonexistent/stack")
        assert "domain" in dirs


# ---------------------------------------------------------------------------
# _parse_project_structure
# ---------------------------------------------------------------------------

class TestParseProjectStructure:
    BLUEPRINT_STRUCTURE = """\
```
src/
  lib/
    db/         # Dexie.js DB setup
    domain/     # Aggregates, Entities
    events/
  routes/
    +page.svelte
tests/
```"""

    def test_top_level_dirs_detected(self):
        dirs = _parse_project_structure(self.BLUEPRINT_STRUCTURE)
        assert "src" in dirs
        assert "tests" in dirs

    def test_nested_dirs_detected(self):
        dirs = _parse_project_structure(self.BLUEPRINT_STRUCTURE)
        assert "src/lib" in dirs
        assert "src/lib/db" in dirs
        assert "src/lib/domain" in dirs

    def test_file_references_excluded(self):
        dirs = _parse_project_structure(self.BLUEPRINT_STRUCTURE)
        assert not any("+page.svelte" in d for d in dirs)

    def test_comments_stripped(self):
        dirs = _parse_project_structure(self.BLUEPRINT_STRUCTURE)
        assert not any("#" in d for d in dirs)

    def test_no_code_fence_markers(self):
        dirs = _parse_project_structure(self.BLUEPRINT_STRUCTURE)
        assert not any("```" in d for d in dirs)


# ---------------------------------------------------------------------------
# _build_template_vars
# ---------------------------------------------------------------------------

class TestBuildTemplateVars:
    def test_project_slug_is_kebab_case(self):
        stacks = [_stack("sveltekit", "frontend")]
        v = _build_template_vars("LocalTaskManager", stacks)
        assert v["project_slug"] == "localtaskmanager"

    def test_app_package_derived_from_slug(self):
        stacks = [_stack("kotlin-android", "mobile")]
        v = _build_template_vars("MyApp", stacks)
        assert v["app_package"] == "com.example.myapp"

    def test_go_module_derived_from_slug(self):
        stacks = [_stack("go-beego", "backend")]
        v = _build_template_vars("Pigiste", stacks)
        assert v["go_module"] == "github.com/example/pigiste"

    def test_monorepo_flags_single_frontend(self):
        stacks = [_stack("sveltekit", "frontend")]
        v = _build_template_vars("App", stacks)
        assert v["has_frontend"] is True
        assert v["has_backend"] is False
        assert v["has_mobile"] is False

    def test_monorepo_flags_full_stack(self):
        stacks = [
            _stack("sveltekit", "frontend"),
            _stack("go-beego", "backend"),
        ]
        v = _build_template_vars("App", stacks)
        assert v["has_frontend"] is True
        assert v["has_backend"] is True

    def test_stack_vars_merged(self):
        stacks = [_stack("sveltekit", "frontend", vars_={"sveltekit_version": "2.x"})]
        v = _build_template_vars("App", stacks)
        assert v["sveltekit_version"] == "2.x"


# ---------------------------------------------------------------------------
# Full scaffold() integration
# ---------------------------------------------------------------------------

SVELTEKIT_SPEC = """\
# Initialize project

## Project Name
LocalTaskManager

## Technical Stack
- SvelteKit (frontend framework)
- Dexie.js (IndexedDB wrapper)
- Vitest (test runner)

## Technical Constraints
- Frontend only, no backend.

## Branch Name
init_project
"""

MONOREPO_SPEC = """\
# Initialize project

## Project Name
Pigiste

## Technical Stack
- SvelteKit 2.x (frontend framework)
- Beego (Go web framework, backend)
- PostgreSQL 16 (database)
- Vitest (frontend tests)

## Branch Name
init_project
"""

ANDROID_SPEC = """\
# Initialize project

## Project Name
MyAndroidApp

## Technical Stack
- Kotlin (Android native)
- Room (local database)
- JUnit5 + Mockk (test runner)

## Branch Name
init_project
"""


class TestScaffoldSvelteKitOnly:
    def test_ddd_dirs_created(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        assert (tmp_path / "src" / "lib" / "domain").is_dir()
        assert (tmp_path / "src" / "lib" / "events").is_dir()
        assert (tmp_path / "tests").is_dir()

    def test_keep_files_in_empty_dirs(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        assert (tmp_path / "src" / "lib" / "domain" / ".keep").exists()

    def test_package_json_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        pkg = tmp_path / "package.json"
        assert pkg.exists()
        assert "localtaskmanager" in pkg.read_text()

    def test_svelte_config_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        assert (tmp_path / "svelte.config.js").exists()

    def test_vite_config_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        assert (tmp_path / "vite.config.ts").exists()

    def test_gitignore_created(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        gi = tmp_path / ".gitignore"
        assert gi.exists()
        assert "SovereignSpecAI" in gi.read_text()

    def test_no_makefile_single_stack(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        assert not (tmp_path / "Makefile").exists()

    def test_no_frontend_subdirectory(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        assert not (tmp_path / "frontend").exists()

    def test_idempotent(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
            scaffold(SVELTEKIT_SPEC)   # second run must not raise
        assert (tmp_path / "src" / "lib" / "domain").is_dir()

    def test_keep_not_added_to_non_empty_dir(self, tmp_path):
        (tmp_path / "src" / "lib" / "domain").mkdir(parents=True)
        (tmp_path / "src" / "lib" / "domain" / "task.ts").write_text("// existing")
        with _patch_root(tmp_path), _offline():
            scaffold(SVELTEKIT_SPEC)
        assert not (tmp_path / "src" / "lib" / "domain" / ".keep").exists()


class TestScaffoldMonorepoSvelteKitBeego:
    def test_frontend_subdir_created(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        assert (tmp_path / "frontend").is_dir()

    def test_backend_subdir_created(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        assert (tmp_path / "backend").is_dir()

    def test_frontend_ddd_under_frontend(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        assert (tmp_path / "frontend" / "src" / "lib" / "domain").is_dir()

    def test_backend_ddd_under_backend(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        assert (tmp_path / "backend" / "domain" / "aggregates").is_dir()

    def test_go_beego_templates_in_backend(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        assert (tmp_path / "backend" / "go.mod").exists()

    def test_sveltekit_templates_in_frontend(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        assert (tmp_path / "frontend" / "package.json").exists()

    def test_makefile_created_at_root(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        assert (tmp_path / "Makefile").exists()

    def test_makefile_contains_frontend_and_backend(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        mk = (tmp_path / "Makefile").read_text()
        assert "frontend" in mk
        assert "backend" in mk

    def test_go_module_slug_in_go_mod(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(MONOREPO_SPEC)
        gomod = (tmp_path / "backend" / "go.mod").read_text()
        assert "pigiste" in gomod


class TestScaffoldAndroidKotlin:
    def test_app_module_created(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        assert (tmp_path / "app").is_dir()

    def test_domain_dir_created(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        assert any(
            "domain" in str(p)
            for p in tmp_path.rglob(".keep")
        )

    def test_presentation_dir_created(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        assert any(
            "presentation" in str(p)
            for p in tmp_path.rglob(".keep")
        )

    def test_build_gradle_kts_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        assert (tmp_path / "build.gradle.kts").exists()

    def test_settings_gradle_kts_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        settings = tmp_path / "settings.gradle.kts"
        assert settings.exists()
        assert "MyAndroidApp" in settings.read_text()

    def test_libs_versions_toml_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        assert (tmp_path / "gradle" / "libs.versions.toml").exists()

    def test_app_build_gradle_kts_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        assert (tmp_path / "app" / "build.gradle.kts").exists()

    def test_no_makefile_single_stack(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(ANDROID_SPEC)
        assert not (tmp_path / "Makefile").exists()


class TestMergeGitignore:
    from scaffolding.engine import _merge_gitignore

    def test_creates_file_when_absent(self, tmp_path):
        from scaffolding.engine import _merge_gitignore
        path = tmp_path / ".gitignore"
        _merge_gitignore(path, "### Node ###\nnode_modules/\n")
        assert "node_modules/" in path.read_text()

    def test_appends_new_sections(self, tmp_path):
        from scaffolding.engine import _merge_gitignore
        path = tmp_path / ".gitignore"
        path.write_text("# SovereignSpecAI Tooling\nsovereign-spec-ai/\n")
        _merge_gitignore(path, "### Node ###\nnode_modules/\n")
        content = path.read_text()
        assert "sovereign-spec-ai/" in content
        assert "node_modules/" in content

    def test_does_not_duplicate_existing_section(self, tmp_path):
        from scaffolding.engine import _merge_gitignore
        path = tmp_path / ".gitignore"
        path.write_text("### Node ###\nnode_modules/\n")
        _merge_gitignore(path, "### Node ###\nnode_modules/\n")
        assert path.read_text().count("node_modules/") == 1

    def test_sovereign_init_entries_preserved(self, tmp_path):
        """Simulates the sovereign init → sovereign scaffold sequence."""
        from scaffolding.engine import _merge_gitignore
        path = tmp_path / ".gitignore"
        # sovereign init writes the sidecar entry first
        path.write_text("# SovereignSpecAI Tooling\nsovereign-spec-ai/\n.aider*\n")
        # sovereign scaffold merges Node + Svelte sections
        _merge_gitignore(
            path,
            "### Node ###\nnode_modules/\n\n### SovereignSpecAI tooling ###\n.aider*\n",
        )
        content = path.read_text()
        assert "sovereign-spec-ai/" in content
        assert "node_modules/" in content


class TestScaffoldBlueprintStructureOverride:
    SPEC_WITH_STRUCTURE = """\
# Initialize project

## Project Name
CustomApp

## Technical Stack
- SvelteKit (frontend framework)
- Vitest

## Project Structure
```
src/
  custom/
    override/
tests/
```

## Branch Name
init_project
"""

    def test_blueprint_structure_used(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(self.SPEC_WITH_STRUCTURE)
        assert (tmp_path / "src" / "custom" / "override").is_dir()

    def test_default_ddd_not_applied_when_overridden(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(self.SPEC_WITH_STRUCTURE)
        # The default sveltekit DDD has src/lib/domain — should NOT be created
        assert not (tmp_path / "src" / "lib" / "domain").exists()

    def test_config_templates_still_rendered(self, tmp_path):
        with _patch_root(tmp_path), _offline():
            scaffold(self.SPEC_WITH_STRUCTURE)
        assert (tmp_path / "package.json").exists()