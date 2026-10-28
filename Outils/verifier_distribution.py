"""Verify an exported ZIP and run its native self-test from another folder."""
from __future__ import annotations
import argparse
from pathlib import Path
import os
import subprocess
import tempfile
from zipfile import ZipFile
from chemins import WORKSPACE
from partager_application import app_allowed, digest_file, verify_zip
from preparer_projet import project_allowed, require_project_files


def verify_distribution(workspace: Path = WORKSPACE, *, project: bool = False) -> dict:
    workspace = Path(workspace).resolve(strict=True)
    prefix = "PrepaPilot-Projet" if project else "PrepaPilot"
    archive = workspace / "Partage" / ("PrepaPilot-Projet.zip" if project else "PrepaPilot-Windows.zip")
    checksum = archive.with_suffix(".zip.sha256").read_text(encoding="ascii").split()[0]
    if digest_file(archive) != checksum:
        raise ValueError("L’empreinte SHA-256 de l’archive ne correspond pas.")
    manifest = verify_zip(archive, prefix, "project" if project else "windows", project_allowed if project else app_allowed)
    with tempfile.TemporaryDirectory(prefix="prepapilot-portable-") as temporary:
        with ZipFile(archive) as bundle:
            bundle.extractall(temporary)
        root = Path(temporary) / prefix
        if project:
            require_project_files(root)
        application = root / "Application" / "PrepaPilot" if project else root
        if not all((application / name).is_file() for name in ("PrepaPilot.exe", "GUIDE.md", "VERIFICATION.md")):
            raise ValueError("L’application exportée est incomplète.")
        if not (application / "_internal").is_dir() or (application / "data").exists():
            raise ValueError("Les bibliothèques manquent ou l’application contient des données.")
        options = {}
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run([str(application / "PrepaPilot.exe"), "--self-test"], cwd=application, timeout=60, **options)
        if result.returncode != 0 or not (application / "self-test-ok.txt").is_file():
            raise RuntimeError("L’autotest de l’application extraite a échoué.")
        if (application / "data").exists():
            raise RuntimeError("L’autotest a créé des données dans le dossier exporté.")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projet", action="store_true", help="Vérifier le projet complet plutôt que l’application seule.")
    args = parser.parse_args()
    result = verify_distribution(project=args.projet)
    print(f"ZIP vérifié : {result['file_count']} fichiers, SHA-256, absence de données, lancement natif depuis un autre dossier.")

