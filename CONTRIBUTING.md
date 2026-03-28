# Contributing to SovereignSpecAI

Thank you for your interest in contributing to SovereignSpecAI — a local-first, privacy-preserving AI coding orchestrator. Contributions of all kinds are welcome: bug reports, documentation improvements, feature proposals, and code.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [License](#license)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features](#suggesting-features)
  - [Submitting Code](#submitting-code)
- [Development Setup](#development-setup)
- [Branching and Commit Conventions](#branching-and-commit-conventions)
- [Pull Request Process](#pull-request-process)
- [AI-Generated Code Policy](#ai-generated-code-policy)
- [Style Guide](#style-guide)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating, you agree to uphold a welcoming and respectful environment for everyone.

---

## License

By contributing to SovereignSpecAI, you agree that your contributions will be licensed under the same license as this project: the [MIT License](./LICENSE).

---

## How to Contribute

### Reporting Bugs

1. **Search existing issues** before opening a new one to avoid duplicates.
2. Open a new issue with a clear title and the following information:
   - Steps to reproduce
   - Expected vs. actual behavior
   - Your environment (OS, Python version, Ollama model, GPU/VRAM)
   - Relevant logs or screenshots

### Suggesting Features

Open an issue tagged `enhancement` and describe:
- The problem you are trying to solve
- Your proposed solution
- Any alternatives you considered

Features that preserve local-first operation and data privacy are prioritised.

### Submitting Code

1. Fork the repository.
2. Create a feature branch (see [Branching Conventions](#branching-and-commit-conventions)).
3. Make your changes with focused, atomic commits.
4. Open a pull request against `main`.

---

## Development Setup

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/sovereign-spec-ai.git
cd sovereign-spec-ai

# 2. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Sync dependencies and create virtual environment
uv sync

# 4. Run the dashboard locally
uv run streamlit run dashboard.py
```

**Prerequisites:** Linux, Python 3.10+, Ollama, Aider (`pip install aider-chat`).

---

## Branching and Commit Conventions

### Branches

| Prefix | Purpose |
|---|---|
| `feat/` | New feature |
| `fix/` | Bug fix |
| `docs/` | Documentation only |
| `refactor/` | Code restructuring without behaviour change |
| `chore/` | Tooling, CI, dependencies |

Example: `feat/kanban-auto-assign`

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(scope): short imperative description

Optional longer explanation.
```

Examples:
```
feat(dashboard): add Icebox drag-and-drop support
fix(aider): handle missing model fallback gracefully
docs(readme): clarify VRAM requirements
```

---

## Pull Request Process

1. Ensure your branch is up to date with `main` before opening a PR.
2. Fill in the PR template with a summary, motivation, and testing notes.
3. PRs require at least one approving review before merging.
4. All CI checks must pass.
5. Squash-merge is preferred to keep history clean.

---

## AI-Generated Code Policy

SovereignSpecAI is, by design, a project built *with* and *for* AI-assisted development. AI-generated code is explicitly welcome in contributions.

However, **vibe-coding is not acceptable.** Submitting code you have not fully understood and verified is a disservice to every contributor and user who depends on this codebase.

Before submitting AI-generated code, you are expected to:

- **Read every line** of the generated output and understand what it does.
- **Verify correctness** — trace the logic, check edge cases, and confirm it solves the stated problem without introducing new ones.
- **Run it locally** and validate the behaviour against your intent.
- **Own it** — once you submit, you are the author of record, regardless of what tool produced the first draft.

In short: use your local models, use Aider, use whatever helps you build faster — but ship only code you would be comfortable defending line by line in a review.

---

## Style Guide

- **Python:** Follow [PEP 8](https://peps.python.org/pep-0008/). Use `ruff` for linting (`uv run ruff check .`).
- **Type hints:** Add type annotations to all new functions.
- **Docstrings:** Use Google-style docstrings for public functions and classes.
- **Tests:** Add or update tests for any changed behaviour. Run with `uv run pytest`.
- **Mermaid diagrams:** For architectural changes, update the relevant diagram in `architecture-example/`.

---

*SovereignSpecAI — your business logic belongs to you.*
