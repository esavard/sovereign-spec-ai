"""Fetches and caches .gitignore templates from github/gitignore, then
concatenates the relevant ones for all detected stacks into a single file.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scaffolding.registry import Stack

_GITHUB_URL = (
    "https://raw.githubusercontent.com/github/gitignore/main/{name}.gitignore"
)
_DEFAULT_CACHE = Path(__file__).parent / "gitignore_cache"

# Entries always appended at the end of the generated .gitignore.
# The sidecar directory name is injected at build time by engine.py.
_SOVEREIGN_HEADER = "### SovereignSpecAI tooling ###"
_SOVEREIGN_ENTRIES = [
    "# aider",
    ".aider*",
    "",
    "# specs & architecture (sidecar)",
    "specs/",
    "architecture*/",
]


class GitignoreFetcher:
    def __init__(self, cache_dir: Path | None = None) -> None:
        self._cache = cache_dir or _DEFAULT_CACHE
        self._cache.mkdir(parents=True, exist_ok=True)

    def fetch(self, name: str) -> str:
        """Return the content of *name*.gitignore, using a local cache.

        Returns an empty string (and emits a warning) on network failure.
        """
        cache_file = self._cache / f"{name}.gitignore"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")

        url = _GITHUB_URL.format(name=name)
        try:
            with urllib.request.urlopen(url, timeout=8) as resp:  # noqa: S310
                content = resp.read().decode("utf-8")
        except (urllib.error.URLError, OSError):
            # Offline or network error — degrade gracefully
            return ""

        cache_file.write_text(content, encoding="utf-8")
        return content

    def build(self, stacks: list[Stack], sidecar_dir: str = "") -> str:
        """Concatenate gitignore sections for all *stacks*, deduplicated.

        Sections are separated by a blank line and prefixed with a header
        comment so the origin is clear. The SovereignSpecAI tooling entries
        are always appended last.

        *sidecar_dir* is the basename of the sovereign-spec-ai directory
        (e.g. ``"sovereign-spec-ai"``). When provided it is added to the
        tooling block so the sidecar itself is never tracked by the project.
        """
        seen: set[str] = set()
        parts: list[str] = []

        for stack in stacks:
            for gi_name in stack.gitignore:
                if gi_name in seen:
                    continue
                seen.add(gi_name)
                content = self.fetch(gi_name)
                if content:
                    parts.append(f"### {gi_name} ###\n{content.rstrip()}")

        sovereign_entries = list(_SOVEREIGN_ENTRIES)
        if sidecar_dir:
            sovereign_entries = [
                "# sovereign-spec-ai sidecar",
                f"{sidecar_dir}/",
                "",
            ] + sovereign_entries

        sovereign_block = "\n".join([_SOVEREIGN_HEADER] + sovereign_entries)
        parts.append(sovereign_block)

        return "\n\n".join(parts) + "\n"