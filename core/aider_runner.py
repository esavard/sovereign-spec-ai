import os
import subprocess
import sys

from core import PROJECT_ROOT


def run_aider(
    message: str,
    model: str,
    extra_args: list[str] | None = None,
    cwd: str | None = None,
) -> tuple[int, str]:
    command = [
        sys.executable, "-m", "aider",
        "--model", model,
        "--edit-format", "whole",
        "--message", message,
        "--yes",
        *(extra_args or []),
    ]

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["AIDER_NO_COLORS"] = "1"
    env["OLLAMA_API_BASE"] = "http://localhost:11434"

    print(f"> {' '.join(command)}\n", flush=True)

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            cwd=cwd or PROJECT_ROOT,
        )

        lines = []
        for line in process.stdout:
            print(line, end="", flush=True)
            lines.append(line)

        process.wait()
        return process.returncode, "".join(lines)

    except FileNotFoundError as e:
        print(f"\n[ERROR] Failed to start Aider. Is it installed?\nDetails: {e}", flush=True)
        return 1, ""
