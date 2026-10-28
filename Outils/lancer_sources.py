"""Start the development app with separate, disposable development data."""
from pathlib import Path
import subprocess
import sys

from chemins import WORKSPACE, local_root


def main():
    # The installed application's personal data are never used by this launcher.
    development_data = local_root() / "Donnees-developpement"
    source = WORKSPACE / "Sources" / "PrepaPilot"
    return subprocess.call([sys.executable, "-B", str(source / "lancer.py"),
                            "--data-dir", str(development_data)], cwd=source)


if __name__ == "__main__":
    raise SystemExit(main())
