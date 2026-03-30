# Security Policy

## Supported Versions

Only the latest release on the `main` branch receives security fixes.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report them privately by emailing the maintainers or using [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability) feature on the repository.

Include:
- A description of the vulnerability and its potential impact
- Steps to reproduce
- Any suggested fix or patch (optional)

You can expect an acknowledgement within 72 hours and a resolution timeline within 14 days for confirmed issues.

## Scope

SovereignSpecAI runs entirely locally — it does not transmit data to external services. The primary attack surface is:

- **Shell injection** via malformed blueprint content passed to aider or Ollama
- **Malicious spec files** in the `specs/` Kanban pipeline being executed by the Developer agent
- **Ollama API** availability on localhost (no authentication by default)

Contributions that harden these surfaces are especially welcome.
