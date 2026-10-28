"""Install a tested staged build; preserve data and retain the previous binaries."""
from __future__ import annotations
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from chemins import WORKSPACE, local_root
NAMES = ("PrepaPilot.exe", "_internal", "GUIDE.md", "GUIDE.en.md", "VERIFICATION.md")


def _digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def _files(folder):
    for name in NAMES:
        path = folder / name
        if not path.exists():
            continue
        for item in sorted(path.rglob("*")) if path.is_dir() else [path]:
            if item.is_symlink():
                raise ValueError("La livraison contient un lien symbolique ; utilise une construction locale complète.")
            if item.is_file():
                yield item


def _manifest(folder):
    return {path.relative_to(folder).as_posix(): {"size": path.stat().st_size, "sha256": _digest(path)} for path in _files(folder)}


def _copy(source, target):
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy2(source, target)


def _local_directory(workspace, name):
    root = local_root(workspace)
    folder = root / name
    if root.resolve() != root or folder.resolve() != folder or folder.resolve().parent != root:
        raise ValueError("Les fichiers locaux doivent rester dans le dossier voisin prévu, sans redirection.")
    return folder


def _reserve_archive(workspace, label):
    archives = _local_directory(workspace, "Archives")
    if not re.fullmatch(r"PrepaPilot-v[0-9]+(?:\.[0-9]+){0,3}", label):
        raise ValueError("Le nom de l’archive doit être une version, par exemple PrepaPilot-v2.1.")
    archives.mkdir(parents=True, exist_ok=True)
    for attempt in range(20):
        suffix = "" if attempt == 0 else f"-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
        archive = archives / (label + suffix)
        if archive.resolve().parent != archives or not archive.resolve().is_relative_to(local_root(workspace)):
            raise ValueError("Le dossier d’archive est situé hors du dossier prévu.")
        try:
            archive.mkdir()
        except FileExistsError:
            continue
        return archive
    raise ValueError("Impossible de réserver un nouveau dossier d’archive.")


def install_update(staging, *, workspace=WORKSPACE, lock_factory=None, archive_label="PrepaPilot-v2.1"):
    workspace = Path(workspace).resolve()
    staging = Path(staging).resolve()
    application = workspace / "Application" / "PrepaPilot"
    archives = _local_directory(workspace, "Archives")
    transactions = _local_directory(workspace, "Transactions")
    archive = None
    # Only the named build tree may be installed; never move arbitrary supplied directories.
    allowed_staging = _local_directory(workspace, "Livraison") / "PrepaPilot"
    if staging != allowed_staging or allowed_staging.resolve() != allowed_staging or application.resolve() != application:
        raise ValueError("La livraison doit être dans Livraison/PrepaPilot du dossier local voisin, séparée de l’application.")
    if any((staging / name).is_symlink() for name in NAMES) or not (staging / "PrepaPilot.exe").is_file() or not (staging / "_internal").is_dir() or (staging / "data").exists():
        raise ValueError("La livraison doit contenir l’exécutable et _internal, sans données personnelles.")
    marker = staging / "self-test-ok.txt"
    if not marker.is_file() or marker.stat().st_mtime_ns < (staging / "PrepaPilot.exe").stat().st_mtime_ns:
        raise ValueError("Valide d’abord cette livraison avec PrepaPilot.exe --self-test.")
    if not (application / "PrepaPilot.exe").is_file() or not (application / "data").is_dir():
        raise ValueError("L’installation actuelle ou son dossier data est introuvable.")
    if archives.is_symlink() or (application / "data").is_symlink() or any((application / name).is_symlink() for name in NAMES):
        raise ValueError("Les dossiers d’installation et d’archive ne doivent pas être des liens symboliques.")
    if not re.fullmatch(r"PrepaPilot-v[0-9]+(?:\.[0-9]+){0,3}", archive_label):
        raise ValueError("Le nom de l’archive doit être une version, par exemple PrepaPilot-v2.1.")
    if lock_factory is None:
        from PySide6.QtCore import QLockFile
        lock_factory = QLockFile
    lock = lock_factory(str(application / "data" / "application.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        raise ValueError("PrépaPilot est ouvert. Ferme sa fenêtre, puis relance la mise à jour. Aucune application n’a été fermée automatiquement.")
    prepared = None
    moved, installed = [], []
    successful = False
    rollback_complete = False
    try:
        # Copy and hash everything before touching the installed binaries.
        transactions.mkdir(parents=True, exist_ok=True)
        prepared = Path(tempfile.mkdtemp(prefix=".update-", dir=transactions))
        if prepared.resolve().parent != transactions or not prepared.name.startswith(".update-"):
            raise RuntimeError("Le dossier temporaire de mise à jour est inattendu ; il a été conservé.")
        new = prepared / "new"
        new.mkdir()
        for name in NAMES:
            if (staging / name).exists():
                _copy(staging / name, new / name)
        if _manifest(staging) != _manifest(new):
            raise ValueError("La copie de la livraison n’a pas pu être vérifiée.")
        for filename, source_name in (("GUIDE.md", "README.md"), ("VERIFICATION.md", "VERIFICATION.md")):
            source = workspace / "Sources" / "PrepaPilot" / source_name
            if not (new / filename).exists() and source.is_file():
                shutil.copy2(source, new / filename)
        old_manifest = _manifest(application)
        new_manifest = _manifest(new)
        archive = _reserve_archive(workspace, archive_label)
        (archive / "mise-a-jour.json").write_text(json.dumps({"previous": old_manifest, "installed": new_manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            for name in NAMES:
                current = application / name
                if current.exists():
                    os.replace(current, archive / name)
                    moved.append(name)
            for name in NAMES:
                if (new / name).exists():
                    os.replace(new / name, application / name)
                    installed.append(name)
            if _manifest(application) != new_manifest:
                raise ValueError("La version installée n’a pas pu être vérifiée.")
            successful = True
        except BaseException:
            rejected = prepared / "rejected"
            rejected.mkdir(exist_ok=True)
            for name in reversed(installed):
                os.replace(application / name, rejected / name)
            for name in reversed(moved):
                os.replace(archive / name, application / name)
            if _manifest(application) != old_manifest:
                raise RuntimeError(f"Restauration incomplète : conserve {archive} et {prepared} pour récupérer les fichiers.")
            rollback_complete = True
            raise
        return archive
    finally:
        # data is never moved, overwritten or recursively enumerated by this script.
        try:
            if prepared is not None and (successful or rollback_complete or not moved):
                if prepared.resolve().parent != _local_directory(workspace, "Transactions") or not prepared.name.startswith(".update-"):
                    raise RuntimeError("Le dossier temporaire de mise à jour est inattendu ; il a été conservé.")
                shutil.rmtree(prepared)
            if rollback_complete and archive.exists():
                if archive.resolve().parent != _local_directory(workspace, "Archives"):
                    raise RuntimeError("Le dossier d’archive est inattendu ; il a été conservé.")
                # Only our transaction marker remains after all original files were returned.
                (archive / "mise-a-jour.json").unlink()
                archive.rmdir()
        finally:
            lock.unlock()


def main():
    parser = argparse.ArgumentParser(description="Installer une livraison testée sans déplacer les données personnelles.")
    parser.add_argument("--staging", default=str(local_root(WORKSPACE) / "Livraison" / "PrepaPilot"))
    parser.add_argument("--archive-label", default="PrepaPilot-v2.1", help="Version remplacée ; un suffixe unique est ajouté si cette archive existe déjà.")
    options = parser.parse_args()
    try:
        archive = install_update(options.staging, archive_label=options.archive_label)
    except (ValueError, OSError, RuntimeError) as exc:
        parser.exit(2, f"Mise à jour interrompue : {exc}\n")
    print(f"Mise à jour vérifiée. Ancienne version conservée dans {archive}.")
    print("Les données sont restées dans Application/PrepaPilot/data.")


if __name__ == "__main__":
    main()
