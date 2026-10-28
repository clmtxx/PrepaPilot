"""Build and verify allowlisted distributions, excluding personal data."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile
import hashlib
import json
import shutil
import stat
import uuid
from chemins import WORKSPACE, local_root

MANIFEST = "MANIFESTE-SHA256.json"
PRIVATE_DIRS = {"data", "backups", "archives", "__pycache__", ".git", ".venv", "venv", "build", "livraison", "apercus", "validation-native"}
PRIVATE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".prepapilot", ".pyc", ".pyo"}
APP_GUIDE = """# PrépaPilot — application Windows

PrépaPilot organise tes études avec tes propres matières, tes notes, tes documents et tes plannings.

Décompresse entièrement cette archive, puis ouvre **PrepaPilot.exe** dans le dossier **PrepaPilot**. Garde le dossier `_internal` à côté de l’exécutable.

La première ouverture propose de configurer ton prénom, ton parcours facultatif, tes matières et ton emploi du temps. Tu peux partir de zéro ou utiliser un exemple modifiable. Tes données sont ensuite enregistrées dans le dossier `data`, créé à côté de l’application.

Dans Notes, ajoute ou renomme tes matières, choisis leurs couleurs et saisis tes évaluations avec leurs types, barèmes et coefficients. Dans Gestion du temps, configure deux plannings renommables, les semaines A/B et tes vacances ou pauses.

Dans **Documents**, crée des dossiers libres et choisis un dossier à l’import ou dans la fiche d’un fichier. Sélectionne plusieurs documents avec **Ctrl** ou **Maj**, puis clique sur **Ranger** pour les déplacer ensemble. Supprimer un dossier conserve ses fichiers dans **Sans dossier**. La barre de recherche retrouve le titre, le nom d’origine ou les mots-clés dans toute la bibliothèque avec **Rechercher partout**, coché par défaut ; décoche cette option pour limiter la recherche aux filtres choisis. Le classement est conservé dans l’export complet et les sauvegardes Google Drive incluant les documents.

Depuis **Aujourd’hui → Démarrer**, lance une séance de 1 à 240 minutes avec une matière ou le travail autonome et un objectif facultatif. Le minuteur libre reste disponible. Les pauses sont exclues ; **Terminer** ou **Voir le bilan** permet de vérifier et corriger chaque période, puis de l’ajouter au journal. Rien n’est enregistré automatiquement : **Plus tard** conserve le bilan, **Ignorer la séance** le supprime après confirmation. Le journal retient les minutes entières de chaque période ; vérifie les horaires proposés. Après une interruption, la séance revient en pause. Son état est inclus dans l’export complet et dans la catégorie **Travail, sport et autres activités** de Google Drive.

Dans la version **2.20**, **Ctrl+F** recherche dans les informations des documents, les évaluations de l’année sélectionnée et les repères personnels. **Ctrl+K** ouvre les actions rapides et **F1** donne accès à l’aide hors connexion. Une barre de séance reste disponible lorsque tu changes d’espace, pour faire une pause, reprendre ou retrouver le bilan. L’accueil présente ton prochain pas, les étapes de découverte et les durées réalisées sur sept jours.

Le formulaire de note propose un onglet **Classe · facultatif** : moyenne sur le même barème et classement position/effectif peuvent être renseignés indépendamment. Le graphique ajoute les moyennes connues en pointillés ; le bouton **Classement** suit la position, avec la première place en haut et le détail x/y au survol. Les champs inconnus restent vides et ces repères ne changent pas ta moyenne personnelle. Les exports et sauvegardes comprenant les notes les conservent.

Dans Progression, consulte les bilans de la semaine, du mois ou de trois mois, compare le temps réalisé et suis son évolution annuelle. Mes objectifs permet de personnaliser les scores sur 100 ; aucun objectif n’est imposé. Aucun problème rend neutre une baisse assumée pour la période, sans modifier tes statistiques. Ces préférences sont incluses dans le transfert complet.

Pour transférer tes données, utilise l’export puis l’import complet dans les réglages. Pour partager uniquement l’application, envoie l’archive Windows d’origine : elle ne contient aucune donnée personnelle.

Le fichier MANIFESTE-SHA256.json décrit les fichiers et leurs empreintes. VERIFICATION.md présente les vérifications réalisées.
"""


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if not name or "\\" in name or ":" in name or path.is_absolute() or path.as_posix() != name or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Nom de fichier dangereux : {name}")
    for part in path.parts:
        lower = part.casefold()
        devices = {"con", "prn", "aux", "nul"} | {f"{prefix}{number}" for prefix in ("com", "lpt") for number in range(1, 10)}
        if lower in PRIVATE_DIRS or lower == ".env" or lower.startswith(".env.") or "self-test" in lower or any(ord(char) < 32 for char in part) or part.endswith((" ", ".")) or lower.split(".")[0] in devices:
            raise ValueError(f"Fichier local ou privé refusé : {name}")
    if path.suffix.casefold() in PRIVATE_SUFFIXES:
        raise ValueError(f"Fichier local ou privé refusé : {name}")


def is_link(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def regular_files(directory: Path):
    if is_link(directory):
        raise ValueError(f"Dossier lié refusé : {directory.name}")
    for path in sorted(directory.iterdir()):
        if is_link(path):
            raise ValueError(f"Lien refusé : {path.name}")
        if path.is_dir():
            yield from regular_files(path)
        elif path.is_file():
            yield path
        else:
            raise ValueError(f"Fichier non ordinaire : {path.name}")


def copy_file(source: Path, destination: Path) -> None:
    if is_link(source) or not source.is_file():
        raise ValueError(f"Fichier source absent ou lié : {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_application(application: Path, destination: Path) -> None:
    if is_link(application) or is_link(application.parent):
        raise ValueError("Le dossier de l’application ne doit pas être un lien.")
    if not (application / "PrepaPilot.exe").is_file() or not (application / "_internal").is_dir():
        raise ValueError("Compile et installe d’abord une application Windows validée.")
    copy_file(application / "PrepaPilot.exe", destination / "PrepaPilot.exe")
    for path in regular_files(application / "_internal"):
        name = path.relative_to(application).as_posix()
        safe_name(name)
        copy_file(path, destination / name)
    copy_file(application / "VERIFICATION.md", destination / "VERIFICATION.md")
    (destination / "GUIDE.md").write_text(APP_GUIDE, encoding="utf-8")
    if (application / "GUIDE.en.md").exists():
        copy_file(application / "GUIDE.en.md", destination / "GUIDE.en.md")


def manifest_for(folder: Path, kind: str, allowed) -> dict:
    files, seen = {}, set()
    for path in regular_files(folder):
        name = path.relative_to(folder).as_posix()
        if name == MANIFEST:
            continue
        safe_name(name)
        if not allowed(name) or name.casefold() in seen:
            raise ValueError(f"Fichier non autorisé ou en double : {name}")
        seen.add(name.casefold())
        files[name] = {"size": path.stat().st_size, "sha256": digest_file(path)}
    return {"format": "PrepaPilot-distribution", "version": 1, "kind": kind, "file_count": len(files), "files": files}


def write_manifest(folder: Path, kind: str, allowed) -> dict:
    manifest = manifest_for(folder, kind, allowed)
    (folder / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_folder(folder: Path, kind: str, allowed) -> dict:
    expected = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
    actual = manifest_for(folder, kind, allowed)
    if expected != actual:
        raise ValueError("Le dossier ne correspond pas au manifeste SHA-256.")
    return actual


def write_zip(folder: Path, archive: Path, prefix: str, kind: str, allowed) -> dict:
    manifest = verify_folder(folder, kind, allowed)
    with ZipFile(archive, "w", ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in regular_files(folder):
            bundle.write(path, f"{prefix}/{path.relative_to(folder).as_posix()}")
    verify_zip(archive, prefix, kind, allowed)
    return manifest


def verify_zip(archive: Path, prefix: str, kind: str, allowed) -> dict:
    with ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(name.casefold() for name in names)) or bundle.testzip() is not None:
            raise ValueError("Archive corrompue ou noms en double.")
        manifest = json.loads(bundle.read(f"{prefix}/{MANIFEST}"))
        if manifest.get("format") != "PrepaPilot-distribution" or manifest.get("version") != 1 or manifest.get("kind") != kind:
            raise ValueError("Manifeste de distribution invalide.")
        files = manifest["files"]
        expected = {f"{prefix}/{name}" for name in files} | {f"{prefix}/{MANIFEST}"}
        if set(names) != expected or manifest["file_count"] != len(files):
            raise ValueError("La liste des fichiers de l’archive est incohérente.")
        for name, metadata in files.items():
            safe_name(name)
            if not allowed(name):
                raise ValueError(f"Fichier non autorisé : {name}")
            info = bundle.getinfo(f"{prefix}/{name}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise ValueError(f"Lien refusé dans l’archive : {name}")
            digest = hashlib.sha256()
            with bundle.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            if info.file_size != metadata["size"] or digest.hexdigest() != metadata["sha256"]:
                raise ValueError(f"Empreinte incorrecte : {name}")
    return manifest


def archive_directory(workspace: Path, label: str) -> Path:
    root = local_root(workspace).resolve()
    if root == workspace or root.is_relative_to(workspace):
        raise ValueError("Les anciennes distributions doivent rester hors du projet.")
    archive = root / "Archives" / "Distributions" / f"{label}-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}"
    if not archive.resolve().is_relative_to(root):
        raise ValueError("Chemin d’archive hors des fichiers locaux.")
    archive.mkdir(parents=True, exist_ok=False)
    return archive


def publish(workspace: Path, replacements: list[tuple[Path, Path]]) -> None:
    """Preserve all former outputs and roll back the entire set on failure."""
    old, installed = [], []
    history = archive_directory(workspace, "partage") if any(target.exists() for _, target in replacements) else None
    try:
        for source, target in replacements:
            if is_link(target):
                raise ValueError("La destination ne doit pas être un lien.")
            if target.exists():
                saved = history / target.name
                target.rename(saved)
                old.append((saved, target))
            source.rename(target)
            installed.append(target)
    except Exception:
        failed = archive_directory(workspace, "partage-incomplet")
        for target in reversed(installed):
            if target.exists():
                target.rename(failed / target.name)
        for saved, target in reversed(old):
            saved.rename(target)
        raise


def output_directory(workspace: Path) -> Path:
    workspace = workspace.resolve(strict=True)
    output = workspace / "Partage"
    if is_link(output) or output.resolve().parent != workspace:
        raise ValueError("Partage doit être un dossier ordinaire à la racine du projet.")
    output.mkdir(exist_ok=True)
    return output


def app_allowed(name: str) -> bool:
    return name in {"PrepaPilot.exe", "GUIDE.md", "GUIDE.en.md", "VERIFICATION.md"} or name.startswith("_internal/")


def create_distribution(workspace: Path = WORKSPACE) -> Path:
    workspace = Path(workspace).resolve(strict=True)
    output = output_directory(workspace)
    temporary = output / (".windows-" + uuid.uuid4().hex)
    temporary.mkdir()
    folder = temporary / "PrepaPilot"
    folder.mkdir()
    try:
        copy_application(workspace / "Application" / "PrepaPilot", folder)
        write_manifest(folder, "windows", app_allowed)
        archive = temporary / "PrepaPilot-Windows.zip"
        write_zip(folder, archive, "PrepaPilot", "windows", app_allowed)
        checksum = temporary / "PrepaPilot-Windows.zip.sha256"
        checksum.write_text(f"{digest_file(archive)}  {archive.name}\n", encoding="ascii")
        publish(workspace, [(archive, output / archive.name), (checksum, output / checksum.name)])
        return output / archive.name
    finally:
        if temporary.resolve().parent == output.resolve() and temporary.name.startswith(".windows-"):
            shutil.rmtree(temporary)


if __name__ == "__main__":
    result = create_distribution()
    print(f"Application seule, archive vérifiée : {result}")
    print(f"SHA-256 : {digest_file(result)}")

