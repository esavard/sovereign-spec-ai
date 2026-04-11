"""Unit tests for scaffolding/gitignore.py."""

import urllib.error
from pathlib import Path
from unittest.mock import MagicMock, patch

from scaffolding.gitignore import GitignoreFetcher
from scaffolding.registry import Stack


def _make_stack(id_: str, gitignore: list[str]) -> Stack:
    return Stack(id=id_, role="frontend", templates=[], ddd="", gitignore=gitignore)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _http_mock(content: str):
    """Return a context-manager mock that yields a response with *content*."""
    resp = MagicMock()
    resp.read.return_value = content.encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ---------------------------------------------------------------------------
# fetch()
# ---------------------------------------------------------------------------

class TestFetch:
    def test_fetches_and_caches(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)
        mock_resp = _http_mock("node_modules/\n.env\n")

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = fetcher.fetch("Node")

        assert "node_modules/" in result
        assert (tmp_path / "Node.gitignore").exists()

    def test_cache_hit_skips_network(self, tmp_path):
        cache_file = tmp_path / "Node.gitignore"
        cache_file.write_text("node_modules/\n")
        fetcher = GitignoreFetcher(cache_dir=tmp_path)

        with patch("urllib.request.urlopen") as mock_open:
            result = fetcher.fetch("Node")

        mock_open.assert_not_called()
        assert result == "node_modules/\n"

    def test_offline_returns_empty_string(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = fetcher.fetch("Go")

        assert result == ""

    def test_oserror_returns_empty_string(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)

        with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
            result = fetcher.fetch("Python")

        assert result == ""

    def test_cache_file_written_after_fetch(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)

        with patch("urllib.request.urlopen", return_value=_http_mock("*.pyc\n")):
            fetcher.fetch("Python")

        assert (tmp_path / "Python.gitignore").read_text() == "*.pyc\n"

    def test_second_fetch_uses_cache(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)

        with patch("urllib.request.urlopen", return_value=_http_mock("*.class\n")) as m:
            fetcher.fetch("Java")
            fetcher.fetch("Java")   # second call

        assert m.call_count == 1    # network called exactly once


# ---------------------------------------------------------------------------
# build()
# ---------------------------------------------------------------------------

class TestBuild:
    def _fetcher_with_files(self, tmp_path: Path, files: dict[str, str]) -> GitignoreFetcher:
        for name, content in files.items():
            (tmp_path / f"{name}.gitignore").write_text(content)
        return GitignoreFetcher(cache_dir=tmp_path)

    def test_concatenates_sections(self, tmp_path):
        fetcher = self._fetcher_with_files(tmp_path, {
            "Node": "node_modules/\n",
            "Svelte": ".svelte-kit/\n",
        })
        stacks = [_make_stack("sveltekit", ["Node", "Svelte"])]
        result = fetcher.build(stacks)

        assert "node_modules/" in result
        assert ".svelte-kit/" in result

    def test_section_headers_present(self, tmp_path):
        fetcher = self._fetcher_with_files(tmp_path, {"Node": "node_modules/\n"})
        stacks = [_make_stack("sveltekit", ["Node"])]
        result = fetcher.build(stacks)

        assert "### Node ###" in result

    def test_deduplicates_across_stacks(self, tmp_path):
        fetcher = self._fetcher_with_files(tmp_path, {"Node": "node_modules/\n"})
        stacks = [
            _make_stack("sveltekit", ["Node"]),
            _make_stack("nest", ["Node"]),
        ]
        result = fetcher.build(stacks)

        assert result.count("node_modules/") == 1

    def test_sovereign_entries_always_present(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)
        stacks: list[Stack] = []   # no stacks

        result = fetcher.build(stacks)

        assert "### SovereignSpecAI tooling ###" in result
        assert ".aider*" in result

    def test_offline_stack_still_gets_sovereign_block(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)
        stacks = [_make_stack("sveltekit", ["Node"])]

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            result = fetcher.build(stacks)

        assert "### SovereignSpecAI tooling ###" in result

    def test_multiple_stacks_correct_order(self, tmp_path):
        fetcher = self._fetcher_with_files(tmp_path, {
            "Node": "node_modules/\n",
            "Go": "*.exe\n",
        })
        stacks = [
            _make_stack("sveltekit", ["Node"]),
            _make_stack("go-beego", ["Go"]),
        ]
        result = fetcher.build(stacks)
        node_pos = result.index("### Node ###")
        go_pos = result.index("### Go ###")

        assert node_pos < go_pos

    def test_ends_with_newline(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)
        result = fetcher.build([])
        assert result.endswith("\n")

    def test_sidecar_dir_included_when_provided(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)
        result = fetcher.build([], sidecar_dir="sovereign-spec-ai")
        assert "sovereign-spec-ai/" in result

    def test_sidecar_dir_absent_when_not_provided(self, tmp_path):
        fetcher = GitignoreFetcher(cache_dir=tmp_path)
        result = fetcher.build([])
        assert "sovereign-spec-ai/" not in result