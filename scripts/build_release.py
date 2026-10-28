"""Build clean Windows releases, without touching an existing installation.

Run from any directory with Python 3.12 x64. Only the standard library is needed
when --app-dir points to a previously frozen application. Inno Setup 6.3+ is
required for the installer; --portable-only deliberately builds only the ZIP.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile


REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "Sources" / "PrepaPilot"
sys.path.insert(0, str(SOURCE))
from mpsi_desktop.google_oauth_config import (GOOGLE_OAUTH_ASSET,
    select_google_oauth_client, write_google_oauth_client)
VERSION_PATTERN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+\Z")
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}\Z")
UPDATE_CHANNEL = "update-channel.json"
INSTALLATION_MARKER = {"data_mode": "localappdata"}
PRIVATE_DIRS = {"data", "cloud", "documents", "backups", "sauvegardes", "archives", ".git", ".venv"}
PRIVATE_FILES = {"installation.json", "self-test.log", "self-test-ok.txt", "credentials.json", "token.json", "tokens.json", ".env"}
PRIVATE_SUFFIXES = {".sqlite", ".sqlite3", ".db", ".pem", ".key", ".pfx", ".p12", ".log"}
EXCLUDED_MODULES = ["telegram", "matplotlib", "numpy", "pandas", "scipy", "tkinter", "pytest", "IPython", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"]
LANGUAGE_MODULES = ["mpsi_desktop.i18n", "mpsi_desktop.language_choice",
                    "mpsi_desktop.translations_shell", "mpsi_desktop.translations_study",
                    "mpsi_desktop.translations_schedule", "mpsi_desktop.translations_progress",
                    "mpsi_desktop.translations_cloud", "mpsi_desktop.translations_updates",
                    "mpsi_desktop.translations_experience", "mpsi_desktop.translations_engagement",
                    "mpsi_desktop.translations_quick_actions", "mpsi_desktop.translations_search",
                    "mpsi_desktop.translations_focus_bar", "mpsi_desktop.translations_help",
                    "mpsi_desktop.translations_launch", "mpsi_desktop.translations_organization"]


def validate_repository(value: str) -> str:
    """Accept a GitHub owner/repository, never a URL, token or shell argument."""
    if (not isinstance(value, str) or not REPOSITORY_PATTERN.fullmatch(value)
            or value.split("/")[1] in {".", ".."} or value.endswith('.git')):
        raise ValueError("Le dépôt de mises à jour doit respecter propriétaire/dépôt (GitHub public), sans URL ni jeton.")
    return value


def read_update_repository(channel: Path) -> str | None:
    ensure_plain_path(channel)
    if not channel.exists():
        return None
    if not channel.is_file() or channel.stat().st_size > 4096:
        raise ValueError("La configuration publique des mises à jour est invalide.")
    try:
        content = json.loads(channel.read_text(encoding="utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("La configuration publique des mises à jour doit être un JSON valide.") from exc
    if not isinstance(content, dict) or set(content) != {"repository"}:
        raise ValueError("La configuration publique des mises à jour accepte uniquement la clé repository, sans jeton.")
    return validate_repository(content["repository"])


def write_update_repository(assets: Path, repository: str) -> None:
    assets.mkdir(parents=True, exist_ok=True)
    (assets / UPDATE_CHANNEL).write_text(json.dumps({"repository": validate_repository(repository)}) + "\n", encoding="utf-8")


def stage_assets(source: Path, destination: Path, repository: str | None = None,
                 google_oauth_client: Path | None = None, require_google_drive: bool = False) -> Path:
    """Inject public release identity into a copy; source configuration is immutable."""
    ensure_plain_path(source)
    selected = validate_repository(repository) if repository is not None else read_update_repository(source / UPDATE_CHANNEL)
    google = select_google_oauth_client(source, google_oauth_client, require_google_drive)
    # Links in assets must not cause the builder to follow an unrelated folder.
    for parent, directories, names in os.walk(source, followlinks=False):
        for name in directories + names:
            if is_redirect(Path(parent) / name):
                raise ValueError("Une ressource de construction ne doit pas être un lien.")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(UPDATE_CHANNEL, GOOGLE_OAUTH_ASSET))
    if selected is not None:
        write_update_repository(destination, selected)
    write_google_oauth_client(destination, google)
    return destination


def read_version(source: Path = SOURCE) -> str:
    """Read the version without importing Qt or executing application code."""
    tree = ast.parse((source / "mpsi_desktop" / "__init__.py").read_text(encoding="utf-8-sig"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets):
            version = ast.literal_eval(node.value)
            if isinstance(version, str) and VERSION_PATTERN.fullmatch(version):
                if any(int(part) > 65535 for part in version.split(".")):
                    break
                return version
    raise ValueError("La version doit être une chaîne X.Y.Z, avec des nombres entre 0 et 65535.")


def check_expected_version(version: str, expected: str | None) -> None:
    if expected is not None and expected != version:
        raise ValueError(f"Version incohérente : les sources annoncent {version}, la publication demande {expected}.")


def is_redirect(path: Path) -> bool:
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def ensure_plain_path(path: Path) -> Path:
    """Reject links and Windows junctions, including in existing ancestors."""
    absolute = Path(os.path.abspath(path.expanduser()))
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and is_redirect(candidate):
            raise ValueError(f"Un lien ou une redirection est interdit pour la construction : {candidate}")
    return absolute


def checked_runtime_files(internal: Path) -> list[Path]:
    """Never follow redirects, and refuse recognizable user data in the runtime."""
    ensure_plain_path(internal)
    if not internal.is_dir():
        raise ValueError(f"Le dossier PyInstaller _internal est absent : {internal}")
    files: list[Path] = []
    for parent, directories, names in os.walk(internal, followlinks=False):
        for name in directories + names:
            path = Path(parent) / name
            relative = path.relative_to(internal)
            if is_redirect(path):
                raise ValueError(f"Le programme contient une redirection : {relative}")
            lowered = name.casefold()
            if lowered in PRIVATE_DIRS or lowered in PRIVATE_FILES or path.suffix.casefold() in PRIVATE_SUFFIXES:
                raise ValueError(f"Le programme contient des données privées ou de diagnostic : {relative}")
            if path.is_file():
                files.append(path)
    if not files:
        raise ValueError("Le dossier _internal est vide.")
    return sorted(files)


def check_x64_executable(executable: Path) -> None:
    ensure_plain_path(executable)
    try:
        with executable.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise ValueError("L'exécutable n'est pas un programme Windows.")
            stream.seek(0x3C)
            offset = struct.unpack("<I", stream.read(4))[0]
            stream.seek(offset)
            if stream.read(4) != b"PE\0\0" or stream.read(2) != b"\x64\x86":
                raise ValueError("Le programme doit être une version Windows x64.")
    except (OSError, struct.error) as exc:
        raise ValueError(f"Impossible de lire l'exécutable Windows : {executable}") from exc


def stage_payload(app_dir: Path, destination: Path, guide: Path, english_guide: Path | None = None,
                  google_oauth_client: Path | None = None, require_google_drive: bool = False) -> Path:
    """Copy an explicit allowlist; root data, old markers and logs stay behind."""
    app_dir = ensure_plain_path(app_dir)
    executable = app_dir / "PrepaPilot.exe"
    check_x64_executable(executable)
    runtime = app_dir / "_internal"
    files = checked_runtime_files(runtime)
    read_update_repository(runtime / "assets" / UPDATE_CHANNEL)
    google = select_google_oauth_client(runtime / 'assets', google_oauth_client, require_google_drive)
    ensure_plain_path(guide)
    if not guide.is_file():
        raise ValueError(f"Le guide de l'application est absent : {guide}")
    if english_guide is not None:
        ensure_plain_path(english_guide)
        if not english_guide.is_file():
            raise ValueError(f"Le guide anglais de l'application est absent : {english_guide}")
    if destination.exists():
        raise ValueError("Le dossier de préparation doit être nouveau.")
    destination.mkdir(parents=True)
    shutil.copy2(executable, destination / executable.name)
    for source in files:
        if source.relative_to(runtime).as_posix() == 'assets/' + GOOGLE_OAUTH_ASSET:
            continue  # Replaced by the validated, minimal desktop identity below.
        target = destination / "_internal" / source.relative_to(runtime)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    write_google_oauth_client(destination / '_internal' / 'assets', google)
    shutil.copy2(guide, destination / "GUIDE.md")
    if english_guide is not None:
        shutil.copy2(english_guide, destination / "GUIDE.en.md")
    return destination


def write_portable_zip(payload: Path, target: Path) -> None:
    if (payload / "installation.json").exists() or (payload / "data").exists():
        raise ValueError("Une archive portable ne doit contenir ni marqueur d'installation, ni données.")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for file in sorted(payload.rglob("*")):
            if file.is_file():
                archive.write(file, str(Path("PrepaPilot") / file.relative_to(payload)))


def write_checksums(artifacts: list[Path], target: Path) -> None:
    lines = []
    for artifact in artifacts:
        with artifact.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(f"{digest}  {artifact.name}\n")
    target.write_text("".join(lines), encoding="ascii")


def find_iscc(explicit: str | None = None) -> Path:
    candidates = [explicit] if explicit else [shutil.which("ISCC.exe"), shutil.which("ISCC")]
    if not explicit:
        for environment in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            if base := os.environ.get(environment):
                for folder in ("Inno Setup 6", "Inno Setup 7", "Programs/Inno Setup 6", "Programs/Inno Setup 7"):
                    candidates.append(str(Path(base) / folder / "ISCC.exe"))
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise ValueError("Inno Setup est introuvable. Installe Inno Setup 6.3+ ou fournis --iscc C:\\chemin\\ISCC.exe.")


def build_frozen(source: Path, work: Path, version: str, repository: str | None = None,
                  google_oauth_client: Path | None = None, require_google_drive: bool = False) -> Path:
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise ValueError("La compilation nécessite Python 3.12 x64 sous Windows.")
    if sys.version_info[:2] != (3, 12):
        raise ValueError("Utilise Python 3.12 x64 pour construire cette version.")
    numeric_version = ", ".join(version.split(".") + ["0"])
    version_file = work / "version_info.txt"
    version_file.write_text(
        "VSVersionInfo(ffi=FixedFileInfo(filevers=(" + numeric_version + "), prodvers=(" + numeric_version + "), "
        "mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), "
        "kids=[StringFileInfo([StringTable('040C04B0', [StringStruct('CompanyName', 'PrépaPilot'), "
        f"StringStruct('FileDescription', 'PrépaPilot'), StringStruct('FileVersion', '{version}'), "
        f"StringStruct('ProductName', 'PrépaPilot'), StringStruct('ProductVersion', '{version}'), "
        "StringStruct('OriginalFilename', 'PrepaPilot.exe')])]), VarFileInfo([VarStruct('Translation', [1036, 1200])])])",
        encoding="utf-8",
    )
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir",
               "--name", "PrepaPilot", "--distpath", str(work / "frozen"), "--workpath", str(work / "pyinstaller"),
               "--specpath", str(work), "--paths", str(source), "--icon", str(source / "assets" / "app.ico"),
               "--version-file", str(version_file)]
    assets = stage_assets(source / "assets", work / "assets", repository, google_oauth_client, require_google_drive)
    command.extend(["--add-data", f"{assets};assets"])
    for resource, target in (("licenses", "licenses"), ("README.md", ".")):
        command.extend(["--add-data", f"{source / resource};{target}"])
    for module in EXCLUDED_MODULES:
        command.extend(["--exclude-module", module])
    for module in LANGUAGE_MODULES:
        command.extend(["--hidden-import", module])
    command.append(str(source / "lancer.py"))
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    system = Path(environment.get("SystemRoot", "C:/Windows"))
    environment["PATH"] = os.pathsep.join([str(Path(sys.executable).parent), str(Path(sys.base_prefix)), str(system / "System32"), str(system)])
    subprocess.run(command, cwd=source, env=environment, check=True)
    return work / "frozen" / "PrepaPilot"


def smoke_test(payload: Path) -> None:
    """Check both languages on the disposable copy, without touching --app-dir."""
    log = payload / "self-test.log"
    marker = payload / "self-test-ok.txt"
    for language in ("fr", "en"):
        # A previous success must never mask a missing result in the other language.
        for diagnostic in (log, marker):
            diagnostic.unlink(missing_ok=True)
        process = subprocess.run([str(payload / "PrepaPilot.exe"), "--self-test", "--language", language],
                                 cwd=payload, timeout=180, check=False)
        if process.returncode or not marker.is_file():
            detail = log.read_text(encoding="utf-8", errors="replace")[-6000:] if log.exists() else "Aucun journal disponible."
            raise ValueError(f"Le test de l'application compilée en {language} a échoué (code {process.returncode}).\n{detail}")
        # Only these two known diagnostics are removed; persistent data is forbidden.
        for diagnostic in (log, marker):
            diagnostic.unlink(missing_ok=True)
        if (payload / "data").exists():
            raise ValueError("Le diagnostic a créé des données persistantes dans la distribution.")


def compile_installer(iscc: Path, payload: Path, target_dir: Path, version: str, repo: Path = REPO) -> Path:
    (payload / "installation.json").write_text(json.dumps(INSTALLATION_MARKER) + "\n", encoding="utf-8")
    command = [str(iscc), "/Qp", f"/DAppVersion={version}", f"/DAppDir={payload}",
               f"/DReleaseDir={target_dir}", f"/DAppIcon={repo / 'Sources/PrepaPilot/assets/app.ico'}",
               str(repo / "packaging" / "PrepaPilot.iss")]
    subprocess.run(command, cwd=repo, check=True)
    target = target_dir / f"PrepaPilot-{version}-Setup.exe"
    if not target.is_file():
        raise ValueError("Inno Setup n'a pas produit l'installateur attendu.")
    return target


def safe_remove_work(work: Path, build_root: Path) -> None:
    """Delete only one verified temporary directory created by this builder."""
    root = ensure_plain_path(build_root)
    target = ensure_plain_path(work)
    if target.parent != root or not target.name.startswith("release-") or target.resolve() != target:
        raise ValueError(f"Nettoyage refusé en dehors du dossier temporaire de construction : {target}")
    shutil.rmtree(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Construire l'installateur Windows et l'archive portable propres de PrépaPilot.")
    parser.add_argument("--app-dir", type=Path, help="Bundle PyInstaller existant à réutiliser (jamais modifié).")
    parser.add_argument("--iscc", help="Chemin vers ISCC.exe, compilateur Inno Setup 6.3 ou plus récent.")
    parser.add_argument("--expect-version", help="Version X.Y.Z attendue, par exemple celle d'un tag GitHub.")
    parser.add_argument("--repository", help="Dépôt public GitHub propriétaire/dépôt utilisé pour les mises à jour, sans URL ni jeton.")
    parser.add_argument("--google-oauth-client", type=Path, help="JSON du client OAuth de bureau commun à intégrer, sans connexion personnelle.")
    parser.add_argument("--require-google-drive", action="store_true", help="Refuser la distribution sans client OAuth Google commun valide.")
    parser.add_argument("--portable-only", action="store_true", help="Créer seulement le ZIP portable, sans Inno Setup.")
    parser.add_argument("--skip-self-test", action="store_true", help="Ignorer le test fonctionnel du programme compilé (diagnostic local uniquement).")
    options = parser.parse_args(argv)
    work = None
    try:
        version = read_version()
        check_expected_version(version, options.expect_version)
        if options.repository is not None:
            validate_repository(options.repository)
            if options.app_dir is not None:
                raise ValueError("--repository nécessite une nouvelle compilation ; le dépôt d’un bundle --app-dir existant est déjà défini.")
        client_assets = options.app_dir / '_internal' / 'assets' if options.app_dir else SOURCE / 'assets'
        select_google_oauth_client(client_assets, options.google_oauth_client, options.require_google_drive)
        compiler = None if options.portable_only else find_iscc(options.iscc)
        output = ensure_plain_path(REPO / "dist")
        build_root = ensure_plain_path(REPO / ".build" / "release")
        output.mkdir(parents=True, exist_ok=True)
        build_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="release-", dir=build_root))
        app = options.app_dir if options.app_dir else build_frozen(SOURCE, work, version, options.repository,
                                                                 options.google_oauth_client, options.require_google_drive)
        payload = stage_payload(app, work / "payload", REPO / "INSTALLER.md", REPO / "INSTALL.en.md",
                                options.google_oauth_client, options.require_google_drive)
        if not options.skip_self_test:
            if sys.platform != "win32":
                raise ValueError("Le test du programme Windows nécessite Windows ; --skip-self-test est réservé aux diagnostics.")
            smoke_test(payload)
        artifacts_dir = work / "artifacts"
        artifacts_dir.mkdir()
        portable = artifacts_dir / f"PrepaPilot-{version}-Windows-portable.zip"
        write_portable_zip(payload, portable)
        artifacts = [portable]
        if compiler is not None:
            artifacts.insert(0, compile_installer(compiler, payload, artifacts_dir, version))
        checksums = artifacts_dir / "SHA256SUMS.txt"
        write_checksums(artifacts, checksums)
        # Commit completed files individually. Existing unrelated files are never deleted.
        for artifact in artifacts + [checksums]:
            destination = output / artifact.name
            ensure_plain_path(destination)
            os.replace(artifact, destination)
            print(destination)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"Construction impossible : {exc}", file=sys.stderr)
        return 1
    finally:
        if work is not None:
            safe_remove_work(work, REPO / ".build" / "release")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
