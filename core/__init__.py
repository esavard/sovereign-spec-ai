import os

# Absolute path to the tool directory (sovereign-spec-ai/)
TOOL_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Absolute path to the parent repository (the project being built).
# SovereignSpecAI is always used as a sidecar: cloned inside the target project.
# PROJECT_ROOT is unconditionally the parent directory of the tool.
PROJECT_ROOT: str = os.path.abspath(os.path.join(TOOL_DIR, ".."))