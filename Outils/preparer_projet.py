"""Prepare a portable, clean project folder and its verified ZIP archive."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
import shutil
import uuid

from chemins import WORKSPACE
from partager_application import (
    MANIFEST, copy_application, copy_file, digest_file, is_link, output_directory,
    publish, regular_files, safe_name, verify_folder, verify_zip, write_manifest, write_zip,
)

DOCUMENTATION = {"Guide-PrepaPilot.md", "Verification.md", "Plan-du-projet.md", "Developpement.md", "Google-Drive.md", "Rangement-IA.md", "Audit-2026-10-25.md"}
SOURCE_FILES = {"README.md", "VERIFICATION.md", "requirements.txt", "requirements-dev.txt", "build_windows.py", "lancer.py"}
ASSETS = {"app.ico", "app.png", "app.svg", "check.svg", "down.svg", "up.svg", "timetable.json"}
OPTIONAL_ASSETS = {"google-oauth-client.json"}
PUBLIC_OPTIONAL_ASSETS = {"update-channel.json"}
ROOT_FILES = {"LIRE-MOI.md", "Ouvrir PrepaPilot.cmd", ".gitignore"}
CODE_DIRS = {"mpsi_core", "mpsi_desktop", "tests"}


def project_allowed(name: str) -> bool:
    parts = PurePosixPath(name).parts
    if len(parts) == 1:
        return name in ROOT_FILES
    if parts[0] == "Documentation":
        return len(parts) == 2 and parts[1] in DOCUMENTATION
    if parts[0] == "Outils":
        return len(parts) == 2 and Path(parts[1]).suffix in {".py", ".md"}
    if parts[:2] == ("Application", "PrepaPilot"):
        return len(parts) == 3 and parts[2] in {"PrepaPilot.exe", "GUIDE.md", "GUIDE.en.md", "VERIFICATION.md"} or len(parts) > 3 and parts[2] == "_internal"
    if parts[:2] != ("Sources", "PrepaPilot"):
        return False
    remaining = parts[2:]
    if len(remaining) == 1:
        return remaining[0] in SOURCE_FILES
    if not remaining:
        return False
    if remaining[0] in CODE_DIRS:
        return Path(remaining[-1]).suffix == ".py"
    if remaining[0] == "assets":
        return len(remaining) == 2 and remaining[1] in ASSETS | OPTIONAL_ASSETS | PUBLIC_OPTIONAL_ASSETS
    if remaining[0] == "licenses":
        return Path(remaining[-1]).suffix.casefold() in {"", ".txt", ".md"}
    return False


def require_project_files(folder: Path) -> None:
    required = ROOT_FILES | {
        "Application/PrepaPilot/PrepaPilot.exe", "Application/PrepaPilot/GUIDE.md",
        "Application/PrepaPilot/VERIFICATION.md", "Sources/PrepaPilot/lancer.py",
        "Sources/PrepaPilot/requirements.txt", "Outils/chemins.py", "Outils/preparer_projet.py",
        "Outils/partager_application.py",
    } | {"Documentation/" + name for name in DOCUMENTATION}
    missing = [name for name in sorted(required) if not (folder / name).is_file()]
    if missing:
        raise ValueError("Projet incomplet : " + ", ".join(missing))
    if not any((folder / "Application" / "PrepaPilot" / "_internal").iterdir()):
        raise ValueError("Les bibliothèques de l’application manquent.")
    launcher = (folder / "Ouvrir PrepaPilot.cmd").read_text(encoding="utf-8-sig")
    if "%~dp0Application\\PrepaPilot\\PrepaPilot.exe" not in launcher:
        raise ValueError("Le lanceur doit ouvrir l’application relativement au dossier du projet.")


def source_files(source: Path):
    if is_link(source) or is_link(source.parent):
        raise ValueError("Le dossier des sources ne doit pas être un lien.")
    for name in sorted(SOURCE_FILES):
        yield source / name, name
    for directory in sorted(CODE_DIRS | {"licenses"}):
        # Cache and unrelated data directories are never traversed.
        def visit(folder):
            if is_link(folder):
                raise ValueError(f"Dossier source lié refusé : {folder.name}")
            for path in sorted(folder.iterdir()):
                if path.name.casefold() in {"__pycache__", "data", "backups", ".git", ".venv", "build"}:
                    continue
                relative = path.relative_to(source).as_posix()
                if is_link(path):
                    raise ValueError(f"Lien source refusé : {relative}")
                if path.is_dir():
                    yield from visit(path)
                elif path.is_file() and project_allowed("Sources/PrepaPilot/" + relative):
                    safe_name(relative)
                    yield path, relative
        yield from visit(source / directory)
    if is_link(source / "assets"):
        raise ValueError("Le dossier des ressources ne doit pas être un lien.")
    for name in sorted(ASSETS):
        yield source / "assets" / name, "assets/" + name
    for name in sorted(OPTIONAL_ASSETS | PUBLIC_OPTIONAL_ASSETS):
        if (source / "assets" / name).exists():
            yield source / "assets" / name, "assets/" + name


def prepare_project(workspace: Path = WORKSPACE, destination: Path | None = None) -> Path:
    workspace = Path(workspace).resolve(strict=True)
    output = output_directory(workspace)
    expected = output / "PrepaPilot-Projet"
    destination = expected if destination is None else Path(destination)
    if is_link(destination) or destination.resolve() != expected.resolve():
        raise ValueError("La destination doit être Partage/PrepaPilot-Projet, sans lien vers un autre dossier.")
    temporary = output / (".projet-" + uuid.uuid4().hex)
    temporary.mkdir()
    folder = temporary / "PrepaPilot-Projet"
    folder.mkdir()
    try:
        for name in sorted(ROOT_FILES):
            copy_file(workspace / name, folder / name)
        copy_application(workspace / "Application" / "PrepaPilot", folder / "Application" / "PrepaPilot")
        for path, name in source_files(workspace / "Sources" / "PrepaPilot"):
            copy_file(path, folder / "Sources" / "PrepaPilot" / name)
        if is_link(workspace / "Documentation") or is_link(workspace / "Outils"):
            raise ValueError("Les outils et la documentation ne doivent pas être des liens.")
        for name in sorted(DOCUMENTATION):
            copy_file(workspace / "Documentation" / name, folder / "Documentation" / name)
        for path in sorted((workspace / "Outils").iterdir()):
            if path.suffix in {".py", ".md"}:
                copy_file(path, folder / "Outils" / path.name)
        require_project_files(folder)
        write_manifest(folder, "project", project_allowed)
        verify_folder(folder, "project", project_allowed)
        archive = temporary / "PrepaPilot-Projet.zip"
        write_zip(folder, archive, "PrepaPilot-Projet", "project", project_allowed)
        checksum = temporary / "PrepaPilot-Projet.zip.sha256"
        checksum.write_text(f"{digest_file(archive)}  {archive.name}\n", encoding="ascii")
        publish(workspace, [(folder, destination), (archive, output / archive.name), (checksum, output / checksum.name)])
        return destination
    finally:
        if temporary.resolve().parent == output.resolve() and temporary.name.startswith(".projet-"):
            shutil.rmtree(temporary)


if __name__ == "__main__":
    result = prepare_project()
    manifest = verify_folder(result, "project", project_allowed)
    print(f"Projet complet vérifié : {result}")
    print(f"{manifest['file_count']} fichiers et leurs empreintes SHA-256.")
    print(result.with_suffix(".zip"))
