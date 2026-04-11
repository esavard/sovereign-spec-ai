"""Unit tests for scaffolding/registry.py — stack detection from blueprint text."""

from scaffolding.registry import Stack, detect_stacks

# ---------------------------------------------------------------------------
# Fixtures — representative Technical Stack sections from real blueprints
# ---------------------------------------------------------------------------

SVELTEKIT_ONLY = """\
- SvelteKit (frontend framework)
- Dexie.js (IndexedDB wrapper)
- Vitest (test runner)
"""

SVELTEKIT_BEEGO_PG = """\
- SvelteKit 2.x (frontend framework)
- Beego (Go web framework, backend)
- PostgreSQL 16 (database)
- Vitest (frontend tests)
- Testify (Go test library)
"""

ANDROID_KOTLIN = """\
- Kotlin (Android native)
- Room (local database)
- JUnit5 + Mockk (test runner)
"""

ANDROID_KOTLIN_VERBOSE = """\
- Kotlin 2.1.0 (Android native)
- Room 2.6 (local persistence)
- JUnit 5 (unit tests)
- Mockk (mocking)
- Minimum SDK 28
"""

# ---------------------------------------------------------------------------
# SvelteKit-only blueprint
# ---------------------------------------------------------------------------

class TestSvelteKitOnly:
    def test_detects_one_stack(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert len(stacks) == 1

    def test_stack_id(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert stacks[0].id == "sveltekit"

    def test_role_is_frontend(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert stacks[0].role == "frontend"

    def test_ddd_key(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert stacks[0].ddd == "frontend/sveltekit"

    def test_gitignore_entries(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert "Node" in stacks[0].gitignore
        assert "Svelte" in stacks[0].gitignore

    def test_default_node_version(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert stacks[0].vars["node_version"] == "22"

    def test_default_sveltekit_version(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert stacks[0].vars["sveltekit_version"] == "latest"

    def test_test_runner_detected(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert stacks[0].vars["test_runner"] == "vitest"

    def test_default_package_manager(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert stacks[0].vars["package_manager"] == "npm"

    def test_package_manager_pnpm(self):
        stacks = detect_stacks(SVELTEKIT_ONLY + "- pnpm\n")
        assert stacks[0].vars["package_manager"] == "pnpm"


# ---------------------------------------------------------------------------
# SvelteKit + Beego + PostgreSQL blueprint
# ---------------------------------------------------------------------------

class TestSvelteKitBeegoPostgres:
    def setup_method(self):
        self.stacks = detect_stacks(SVELTEKIT_BEEGO_PG)
        self.by_id = {s.id: s for s in self.stacks}

    def test_three_stacks_detected(self):
        assert len(self.stacks) == 3

    def test_sveltekit_present(self):
        assert "sveltekit" in self.by_id

    def test_go_beego_present(self):
        assert "go-beego" in self.by_id

    def test_postgresql_present(self):
        assert "postgresql" in self.by_id

    def test_roles(self):
        assert self.by_id["sveltekit"].role == "frontend"
        assert self.by_id["go-beego"].role == "backend"
        assert self.by_id["postgresql"].role == "database"

    def test_sveltekit_version_extracted(self):
        assert self.by_id["sveltekit"].vars["sveltekit_version"] == "2.x"

    def test_go_version_default(self):
        # "Beego" text has no explicit Go version → falls back to default
        assert self.by_id["go-beego"].vars["go_version"] == "1.24"

    def test_go_version_explicit(self):
        stacks = detect_stacks("- Beego Go 1.22 (backend)")
        go = next(s for s in stacks if s.id == "go-beego")
        assert go.vars["go_version"] == "1.22"

    def test_postgres_version_extracted(self):
        assert self.by_id["postgresql"].vars["postgres_version"] == "16"

    def test_frontend_before_backend_in_order(self):
        ids = [s.id for s in self.stacks]
        assert ids.index("sveltekit") < ids.index("go-beego")


# ---------------------------------------------------------------------------
# Android Kotlin blueprint
# ---------------------------------------------------------------------------

class TestAndroidKotlin:
    def setup_method(self):
        self.stacks = detect_stacks(ANDROID_KOTLIN)

    def test_one_stack_detected(self):
        assert len(self.stacks) == 1

    def test_stack_id(self):
        assert self.stacks[0].id == "kotlin-android"

    def test_role_is_mobile(self):
        assert self.stacks[0].role == "mobile"

    def test_ddd_key(self):
        assert self.stacks[0].ddd == "mobile/android-kotlin"

    def test_gitignore_entries(self):
        gi = self.stacks[0].gitignore
        assert "Android" in gi
        assert "Kotlin" in gi

    def test_default_kotlin_version(self):
        assert self.stacks[0].vars["kotlin_version"] == "2.1.0"

    def test_default_compile_sdk(self):
        assert self.stacks[0].vars["compile_sdk"] == "35"

    def test_default_min_sdk(self):
        assert self.stacks[0].vars["min_sdk"] == "26"

    def test_test_runner_junit5(self):
        assert self.stacks[0].vars["test_runner"] == "junit5"


class TestAndroidKotlinVerbose:
    def setup_method(self):
        self.stacks = detect_stacks(ANDROID_KOTLIN_VERBOSE)
        self.stack = self.stacks[0]

    def test_kotlin_version_extracted(self):
        assert self.stack.vars["kotlin_version"] == "2.1.0"

    def test_min_sdk_extracted(self):
        assert self.stack.vars["min_sdk"] == "28"

    def test_junit5_with_space(self):
        # "JUnit 5" (with space) should normalise to "junit5"
        assert self.stack.vars["test_runner"] == "junit5"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unknown_stack_returns_empty(self):
        assert detect_stacks("- COBOL (mainframe legacy)") == []

    def test_empty_string_returns_empty(self):
        assert detect_stacks("") == []

    def test_detection_is_case_insensitive(self):
        stacks = detect_stacks("- SVELTEKIT")
        assert any(s.id == "sveltekit" for s in stacks)

    def test_no_false_positive_go_alone(self):
        # Plain "Go" without "beego" should NOT detect go-beego
        stacks = detect_stacks("- Go 1.22 (backend, REST API)")
        assert not any(s.id == "go-beego" for s in stacks)

    def test_postgres_shorthand(self):
        stacks = detect_stacks("- Postgres 15 (database)")
        assert any(s.id == "postgresql" for s in stacks)

    def test_returns_list_of_stack_instances(self):
        stacks = detect_stacks(SVELTEKIT_ONLY)
        assert all(isinstance(s, Stack) for s in stacks)

    def test_html_comments_ignored(self):
        # Example patterns inside <!-- --> must not trigger detection.
        text = """\
- SvelteKit (frontend framework)
- Dexie.js (IndexedDB wrapper)
<!--
Examples:
  - SvelteKit + Beego (Go backend) + PostgreSQL
  - Kotlin (Android native) + Room + JUnit5
-->
"""
        stacks = detect_stacks(text)
        ids = {s.id for s in stacks}
        assert ids == {"sveltekit"}