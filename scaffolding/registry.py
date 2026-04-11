"""Stack detection from a blueprint's Technical Stack section.

Loads registry.yaml and matches each declared stack against the free-text
Technical Stack content using case-insensitive regex. Also extracts version
variables and detects the package manager / test runner when relevant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


@dataclass
class Stack:
    id: str
    role: str           # frontend | backend | mobile | database
    templates: list[str]
    ddd: str            # relative key into ddd/ (e.g. "frontend/sveltekit"), empty for db
    gitignore: list[str]
    vars: dict[str, str] = field(default_factory=dict)


def load_registry() -> dict:
    with open(_REGISTRY_PATH) as f:
        return yaml.safe_load(f)


def detect_stacks(technical_stack_text: str) -> list[Stack]:
    """Return ordered list of Stack objects detected in *technical_stack_text*.

    Order matches declaration order in registry.yaml so that frontend always
    precedes backend, which precedes mobile, which precedes database.

    HTML comments (<!-- ... -->) are stripped before detection so that
    example patterns embedded in blueprint comment blocks don't trigger
    false positives.
    """
    # Strip HTML comments — multiline, non-greedy
    text = re.sub(r"<!--.*?-->", "", technical_stack_text, flags=re.DOTALL)

    registry = load_registry()
    detected: list[Stack] = []

    for stack_id, cfg in registry["stacks"].items():
        patterns: list[str] = cfg.get("detect", [])
        matched = any(
            re.search(p, text, re.IGNORECASE) for p in patterns
        )
        if not matched:
            continue

        vars_: dict[str, str] = {}
        for spec in cfg.get("version_extract", []):
            m = re.search(spec["pattern"], text, re.IGNORECASE)
            vars_[spec["key"]] = m.group(1) if m else spec["default"]

        pm_cfg = cfg.get("package_manager")
        if pm_cfg:
            pm = pm_cfg["default"]
            for candidate in pm_cfg.get("detect", []):
                if re.search(candidate, text, re.IGNORECASE):
                    pm = candidate
                    break
            vars_["package_manager"] = pm

        tr_cfg = cfg.get("test_runner")
        if tr_cfg:
            tr = tr_cfg["default"]
            for candidate in tr_cfg.get("detect", []):
                if re.search(re.escape(candidate), text, re.IGNORECASE):
                    tr = candidate.replace(" ", "")   # "junit 5" → "junit5"
                    break
            vars_["test_runner"] = tr

        detected.append(Stack(
            id=stack_id,
            role=cfg["role"],
            templates=cfg.get("templates", []),
            ddd=cfg.get("ddd", ""),
            gitignore=cfg.get("gitignore", []),
            vars=vars_,
        ))

    return detected