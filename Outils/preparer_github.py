"""Copy only public sources into the dedicated GitHub delivery folder.

The installer, workflows and publication guides live in that folder and are
preserved. Application binaries and personal data are never traversed here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from chemins import WORKSPACE
from partager_application import copy_file, is_link, safe_name
from preparer_projet import DOCUMENTATION, OPTIONAL_ASSETS, source_files


def prepare_github_sources(workspace=WORKSPACE):
    workspace = Path(workspace).resolve(strict=True)
    if (workspace / "scripts" / "build_release.py").is_file():
        raise ValueError("Ce dossier est déjà le dépôt GitHub. Modifie directement ses sources.")
    destination = workspace / "PrepaPilot-GitHub"
    if is_link(destination) or destination.resolve() != destination:
        raise ValueError("PrepaPilot-GitHub doit être un dossier ordinaire dans le projet.")
    destination.mkdir(exist_ok=True)
    files = []
    for path, name in source_files(workspace / "Sources" / "PrepaPilot"):
        # OAuth configuration is a separate, deliberate publisher operation.
        if name in {"assets/" + asset for asset in OPTIONAL_ASSETS}:
            continue
        files.append((path, "Sources/PrepaPilot/" + name))
    for name in sorted(DOCUMENTATION):
        files.append((workspace / "Documentation" / name, "Documentation/" + name))
    tools = workspace / "Outils"
    if is_link(tools):
        raise ValueError("Les outils ne doivent pas être un lien.")
    for path in sorted(tools.iterdir()):
        if path.suffix in {".py", ".md"}:
            files.append((path, "Outils/" + path.name))
    for source, name in files:
        safe_name(name)
        target = destination / name
        if any(is_link(parent) for parent in [target, *target.parents] if parent.is_relative_to(destination)):
            raise ValueError("Un fichier de destination ne doit pas rediriger vers un autre dossier.")
        copy_file(source, target)
    manifest = {
        "description": "Sources publiques copiées depuis le projet de travail, sans données ni configuration Google.",
        "files": {
            name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
            for _, name in sorted(files, key=lambda item: item[1])
        },
    }
    marker = destination / "SOURCES-SHA256.json"
    if is_link(marker):
        raise ValueError("Le manifeste ne doit pas être un lien.")
    marker.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination, len(files)


if __name__ == "__main__":
    folder, count = prepare_github_sources()
    print(f"{count} fichiers publics préparés dans {folder}")
    print("Les installateurs sont générés séparément ; aucune donnée personnelle n’a été copiée.")
