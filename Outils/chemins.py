"""Shared paths: the current project is separate from local working files."""
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]


def local_root(workspace=WORKSPACE):
    workspace = Path(workspace).resolve()
    return workspace.parent / (workspace.name + " - fichiers locaux")
