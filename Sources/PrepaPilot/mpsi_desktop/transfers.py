"""Versioned portable backups, validated staging and recoverable replacement."""
from __future__ import annotations
from .i18n import tr
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile
from mpsi_core.storage import GRADE_COMPARISON_COLUMNS, grade_comparison_values

FORMAT, VERSION = "prepapilot", 1
MAX_FILES = 10000
MAX_TOTAL = 2 * 1024 ** 3
MAX_FILE = 512 * 1024 ** 2
MAX_DATABASE = 128 * 1024 ** 2
MAX_MANIFEST = 2 * 1024 ** 2
BLOCK = 1024 * 1024


class _IncompleteDocumentError(ValueError):
    """Only a missing/truncated attachment may use the incomplete recovery path."""


def _busy(ctx):
    if ctx.busy:
        raise ValueError(tr('Attends la fin du traitement en cours avant de transférer tes données.'))


def _safe_name(name):
    if not isinstance(name, str) or not name or any(ord(char) < 32 or char in '\\:*?"<>|' for char in name):
        raise ValueError(tr('L’archive contient un chemin de fichier invalide.'))
    path = PurePosixPath(name)
    if path.is_absolute() or path.as_posix() != name or any(
        part in {".", ".."} or part.endswith((".", " ")) or
        re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)
        for part in path.parts
    ):
        raise ValueError(tr('L’archive contient un chemin de fichier invalide.'))
    if name not in {"manifest.json", "data.sqlite3"} and not (len(path.parts) > 1 and path.parts[0] == "documents"):
        raise ValueError(tr('L’archive contient un fichier inattendu.'))
    return path


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(BLOCK), b""):
            result.update(block)
    return result.hexdigest()


def _snapshot(source, target):
    with closing(sqlite3.connect(Path(source).resolve().as_uri() + "?mode=ro", uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(tr('La base de données n’a pas pu être vérifiée.'))
            dst.execute("PRAGMA journal_mode=DELETE")


def _document_files(data):
    folder = Path(data) / "documents"
    if folder.is_symlink():
        raise ValueError(tr('Le dossier des documents ne peut pas être un lien symbolique.'))
    for path in sorted(folder.rglob("*")) if folder.exists() else []:
        if path.is_symlink():
            raise ValueError(tr('Un document lié à un autre dossier ne peut pas être transféré.'))
        if path.is_file():
            relative = path.relative_to(data).as_posix()
            _safe_name(relative)
            yield relative, path


def _signatures(folder):
    paths = [("data.sqlite3", Path(folder) / "data.sqlite3"), *_document_files(folder)]
    return {name: {"size": path.stat().st_size, "sha256": _digest(path)} for name, path in paths}


def _check_document_attachment(folder, relative, size):
    from .document_store import ALLOWED_EXTENSIONS
    parsed = _safe_name(relative)
    if len(parsed.parts) != 2 or parsed.parts[0] != "documents" or parsed.suffix.lower() not in ALLOWED_EXTENSIONS or type(size) is not int or size < 0:
        raise ValueError(tr('Un document de l’archive est invalide.'))
    attachment = Path(folder).joinpath(*parsed.parts)
    if not attachment.is_file() or attachment.stat().st_size != size:
        raise _IncompleteDocumentError(tr('Un document est absent ou incomplet dans l’archive.'))


def _check_settings(connection):
    from .time_store import validate_timetable
    from .subject_store import validate_subjects, restore_legacy_grade_subjects
    from .study_profile import validate_program, validate_schedule_labels
    from .progression import validate_targets, validate_acknowledgements
    from .focus_session import validate_focus_session
    from .achievements import SETTING as ACHIEVEMENTS_SETTING, validate_state as validate_achievements
    from .catalog import FIXED_CATEGORIES, default_subjects
    raw_subjects = connection.execute("SELECT value FROM settings WHERE key='desktop_subjects'").fetchone()
    try:
        subjects = validate_subjects(json.loads(raw_subjects[0]) if raw_subjects else default_subjects())
    except (ValueError, TypeError, RecursionError):
        raise ValueError(tr('La liste des matières de l’archive est invalide.')) from None
    recovered = restore_legacy_grade_subjects(subjects, [row[0] for row in connection.execute("SELECT DISTINCT subject FROM grades")])
    repaired_subjects = recovered if recovered != subjects else None
    subjects = recovered
    subject_labels = {subject['id']: subject['name'] for subject in subjects}
    categories = {**FIXED_CATEGORIES, **subject_labels}
    for table in ("settings", "memories"):
        for key, raw in connection.execute(f'SELECT key,value FROM "{table}"'):
            if not isinstance(key, str) or not isinstance(raw, str):
                raise ValueError(tr('Les réglages de l’archive sont invalides.'))
            try:
                value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            except (ValueError, RecursionError):
                raise ValueError(tr('Les réglages de l’archive sont invalides.')) from None
            if table != "settings":
                continue
            if key in {"school_year", "school_year_start"} and (type(value) is not int or not 2000 <= value <= 2200):
                raise ValueError(tr('L’année scolaire de l’archive est invalide.'))
            if key == "school_years":
                if not isinstance(value, list) or any(type(year) is not int or not 2000 <= year <= 2200 for year in value) or value != sorted(set(value)):
                    raise ValueError(tr('La liste des années scolaires de l’archive est invalide.'))
            if key == "time_holidays":
                from .time_store import validate_holidays
                validate_holidays(value)
            if key == "desktop_theme" and value not in ("light", "dark"):
                raise ValueError(tr('Le thème de l’archive est invalide.'))
            if key == "desktop_name" and (not isinstance(value, str) or len(value) > 40):
                raise ValueError(tr('Le prénom de l’archive est invalide.'))
            if key == "desktop_program":
                validate_program(value)
            if key == "desktop_schedule_labels":
                validate_schedule_labels(value)
            if key == "desktop_progression_targets":
                validate_targets(value)
            if key == "desktop_progression_acknowledgements":
                validate_acknowledgements(value)
            if key == "desktop_focus_session":
                validate_focus_session(value, categories={**subject_labels, "permanence": FIXED_CATEGORIES["permanence"]})
            if key == ACHIEVEMENTS_SETTING:
                validate_achievements(value)
            if key in {"desktop_reduced_motion", "desktop_welcomed", "setup_completed"} and type(value) is not bool:
                raise ValueError(tr('Les préférences de l’archive sont invalides.'))
            if key == "desktop_tutorial_version" and (type(value) is not int or not 0 <= value <= 10000):
                raise ValueError(tr('La version du tutoriel de l’archive est invalide.'))
            if key == "desktop_timetable":
                validate_timetable(value, categories=categories)
            if key == "time_semester_transitions":
                from datetime import date
                if not isinstance(value, list):
                    raise ValueError(tr('Les changements de planning sont invalides.'))
                for transition in value:
                    if not isinstance(transition, dict) or transition.get("semester") not in {"S1", "S2"}:
                        raise ValueError(tr('Les changements de planning sont invalides.'))
                    try:
                        date.fromisoformat(transition["effective_date"])
                    except (TypeError, ValueError, KeyError):
                        raise ValueError(tr('Une date de changement de planning est invalide.')) from None
    return subject_labels, categories, repaired_subjects


def _schema(connection):
    entries = connection.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    if any(kind not in {"table", "index"} or (sql and "VIRTUAL TABLE" in sql.upper()) or not re.fullmatch(r"[a-z_]+", name) for kind, name, sql in entries):
        raise ValueError(tr('La base contient une structure non prise en charge.'))
    return {name: tuple(row[1] for row in connection.execute(f'PRAGMA table_info("{name}")'))
            for kind, name, _ in entries if kind == "table"}


def _clear_organization_sessions(connection):
    """Local exchange folders are device state, never transferable authority."""
    connection.execute("DELETE FROM settings WHERE key GLOB 'document_organization_session_*' "
                       "OR key='documents_organization_workspace'")


def _canonical_database(source, target, store_type, folder):
    """Copy values into our schema; never install executable imported SQL."""
    canonical = store_type(target)
    canonical.close()
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.execute("PRAGMA trusted_schema=OFF")
        src.execute("PRAGMA query_only=ON")
        expected, actual = _schema(dst), _schema(src)
        if not _compatible_schema(expected, actual):
            raise ValueError(tr('La structure des données est incompatible avec cette version de PrépaPilot.'))
        if src.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError(tr('La base de l’archive est endommagée.'))
        subjects, categories, repaired_subjects = _check_settings(src)
        _check_grades(src, subjects)
        _check_document_folders(src)
        with dst:
            for table, columns in expected.items():
                dst.execute(f'DELETE FROM "{table}"')
                if table not in actual:
                    continue  # Archives created before document folders.
                names = ",".join(f'"{column}"' for column in columns)
                query = f'INSERT INTO "{table}" ({names}) VALUES ({",".join("?" for _ in columns)})'
                selected = ",".join(f'"{column}"' if column in actual[table] else "NULL" for column in columns)
                rows = src.execute(f'SELECT {selected} FROM "{table}"')
                for row in rows:
                    dst.execute(query, row)
            _clear_organization_sessions(dst)
            if repaired_subjects is not None:
                # The archive stays read-only; the preview and installed copy share
                # the recovered catalogue, including inactive historical subjects.
                dst.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
                            ("desktop_subjects", json.dumps(repaired_subjects, ensure_ascii=False)))
        if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or dst.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError(tr('Les données de l’archive sont incohérentes.'))
        if "documents" in expected:
            from .catalog import DOCUMENT_KINDS
            for relative, size, original, title, subject, kind, description in dst.execute("SELECT stored_path,size_bytes,original_name,title,subject,kind,description FROM documents"):
                _check_document_attachment(folder, relative, size)
                if not isinstance(original, str) or not original or any(char in original for char in '/\\:') or not isinstance(title, str) or not title.strip() or len(title) > 240 or subject not in subjects or kind not in DOCUMENT_KINDS or not isinstance(description, str) or len(description) > 10000:
                    raise ValueError(tr('Les informations d’un document sont invalides.'))
        _check_time_rows(dst, categories)
        counts = {table: dst.execute(f'SELECT count(*) FROM "{table}"' + (" WHERE deleted=0" if table == "time_entries" else "")).fetchone()[0]
                  for table in ("grades", "memories", "documents", "time_entries") if table in expected}
        dst.execute("PRAGMA journal_mode=DELETE")
    return counts


def _compatible_schema(expected, actual):
    """Only accept complete, known historical schema variants."""
    for old_grades in (False, True):
        for old_folders in (False, True):
            candidate = dict(expected)
            if old_grades:
                candidate["grades"] = tuple(column for column in expected["grades"]
                                            if column not in GRADE_COMPARISON_COLUMNS)
            if old_folders:
                candidate.pop("document_folders", None)
                candidate["documents"] = tuple(column for column in expected["documents"] if column != "folder_id")
            if actual == candidate:
                return True
    return False


def _validate_document_folders(folders, documents):
    """Check references and raw types before SQLite can coerce cloud values."""
    from .document_store import MAX_DOCUMENT_FOLDERS, normalize_document_folder_name
    if len(folders) > MAX_DOCUMENT_FOLDERS:
        raise ValueError(tr('La sauvegarde contient trop de dossiers de documents.'))
    identities, names = set(), set()
    for row in folders:
        identity, name = row.get("id"), row.get("name")
        if type(identity) is not int or not 0 < identity <= 9223372036854775807 or identity in identities:
            raise ValueError(tr('Un identifiant de dossier est invalide ou dupliqué.'))
        if normalize_document_folder_name(name) != name or name.casefold() in names:
            raise ValueError(tr('Le nom d’un dossier est invalide ou dupliqué.'))
        created = row.get("created_at")
        try:
            valid_date = isinstance(created, str) and len(created) <= 40 and datetime.fromisoformat(created).tzinfo is None
        except (TypeError, ValueError):
            valid_date = False
        if not valid_date:
            raise ValueError(tr('La date de création d’un dossier est invalide.'))
        identities.add(identity)
        names.add(name.casefold())
    for row in documents:
        identity = row.get("folder_id")
        if identity is not None and (type(identity) is not int or identity not in identities):
            raise ValueError(tr('Un document fait référence à un dossier absent ou invalide.'))


def _check_document_folders(connection):
    schema = _schema(connection)
    if "document_folders" not in schema:
        return
    folders = [dict(zip(schema["document_folders"], row)) for row in connection.execute("SELECT * FROM document_folders")]
    documents = [{"folder_id": row[0]} for row in connection.execute("SELECT folder_id FROM documents")]
    _validate_document_folders(folders, documents)


def _check_grades(connection, subjects):
    from datetime import date
    import math
    from mpsi_core.grades import normalize_kind
    columns = {row[1] for row in connection.execute("PRAGMA table_info(grades)")}
    comparisons = ",".join(f'"{column}"' if column in columns else "NULL" for column in GRADE_COMPARISON_COLUMNS)
    for subject, kind, score, scale, coefficient, graded_on, label, average, rank, size in connection.execute(
            "SELECT subject,kind,score,scale,coefficient,graded_on,label," + comparisons + " FROM grades"):
        if subject not in subjects or any(type(number) not in (int, float) or not math.isfinite(number) for number in (score, scale, coefficient)):
            raise ValueError(tr('Une note de l’archive est invalide.'))
        if not 0 <= score <= scale or scale <= 0 or coefficient <= 0:
            raise ValueError(tr('Le barème ou le coefficient d’une note est invalide.'))
        _check_grade_comparison(scale, average, rank, size)
        normalize_kind(kind)
        if not isinstance(label, str) or len(label.strip()) > 240 or any(ord(char) < 32 or ord(char) == 127 for char in label):
            raise ValueError(tr('Le titre d’une note de l’archive est invalide.'))
        try:
            valid_date = date.fromisoformat(graded_on).isoformat() == graded_on
        except (TypeError, ValueError):
            valid_date = False
        if not valid_date:
            raise ValueError(tr('La date d’une note de l’archive est invalide.'))


def _check_grade_comparison(scale, average, rank, size):
    """Reject malformed imported values before SQLite can coerce their types."""
    if ((average is not None and type(average) not in (int, float))
            or (rank is not None and type(rank) is not int)
            or (size is not None and type(size) is not int)):
        raise ValueError(tr('La moyenne ou le classement d’une note de l’archive est invalide.'))
    grade_comparison_values(scale, average, rank, size)


def _check_time_rows(connection, categories):
    from datetime import date, timedelta
    from .time_store import local_stamp, validate_timetable
    latest_end = None
    for category, title, start, end, override, deleted, status in connection.execute("SELECT category,title,start_at,end_at,manual_override,deleted,status FROM time_entries ORDER BY start_at"):
        duration = local_stamp(end) - local_stamp(start)
        if category not in categories or not isinstance(title, str) or len(title) > 250 or not timedelta() < duration <= timedelta(days=7) or override not in (0, 1) or deleted not in (0, 1):
            raise ValueError(tr('Une activité de l’archive est invalide.'))
        if local_stamp(start).isoformat(timespec="minutes") != start or local_stamp(end).isoformat(timespec="minutes") != end or (status == "completed" and local_stamp(end) > datetime.now()):
            raise ValueError(tr('Les dates ou le statut d’une activité sont invalides.'))
        if not deleted:
            if latest_end is not None and start < latest_end:
                raise ValueError(tr('Des activités de l’archive se chevauchent.'))
            latest_end = end
    for day, semester, raw in connection.execute("SELECT day,semester,slots_json FROM time_day_templates"):
        try:
            parsed = date.fromisoformat(day)
            slots = json.loads(raw)
            if parsed.isoformat() != day or semester not in {"S1", "S2"}:
                raise ValueError
            validate_timetable({"semesters": {"S1": slots if semester == "S1" else [], "S2": slots if semester == "S2" else []}}, categories=categories)
        except (ValueError, TypeError):
            raise ValueError(tr('L’historique de l’emploi du temps est invalide.')) from None


@dataclass
class ImportPlan:
    temporary: tempfile.TemporaryDirectory
    folder: Path
    counts: dict
    created_at: str
    signatures: dict
    closed: bool = False

    def close(self):
        if not self.closed:
            self.temporary.cleanup()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def summary(self):
        labels = {"grades": tr("notes"), "memories": tr('repères personnels'), "documents": "documents", "time_entries": tr('activités')}
        return "\n".join(f"• {count} {labels[name]}" for name, count in self.counts.items())


def export_archive(ctx, destination, *, reconcile_achievements=True, _incomplete_recovery=False):
    _busy(ctx)
    destination = Path(destination).resolve()
    data = Path(ctx.data_dir).resolve()
    if destination == data / "mpsi.sqlite3" or (data / "documents") == destination or (data / "documents") in destination.parents:
        raise ValueError(tr('Choisis un emplacement extérieur aux documents gérés par l’application.'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_archive = destination.with_name(destination.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with tempfile.TemporaryDirectory(prefix="prepapilot-export-") as temporary:
            folder = Path(temporary)
            with ctx.db._lock:
                if reconcile_achievements:
                    from .achievements import reconcile
                    reconcile(ctx.db)
                _snapshot(data / "mpsi.sqlite3", folder / "data.sqlite3")
                for relative, source in _document_files(data):
                    target = folder / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
            # A valid ZIP can still be unrestorable when an original was removed
            # or truncated externally. Verify the copied files against the same
            # database snapshot before replacing any previous safety copy.
            incomplete_documents = []
            with closing(sqlite3.connect(folder / "data.sqlite3")) as connection:
                with connection:
                    _clear_organization_sessions(connection)
                for relative, size in connection.execute("SELECT stored_path,size_bytes FROM documents"):
                    try:
                        _check_document_attachment(folder, relative, size)
                    except _IncompleteDocumentError:
                        if not _incomplete_recovery:
                            raise
                        incomplete_documents.append(relative)
            files = _signatures(folder)
            if len(files) > MAX_FILES or sum(item["size"] for item in files.values()) > MAX_TOTAL or any(item["size"] > MAX_FILE for item in files.values()) or files["data.sqlite3"]["size"] > MAX_DATABASE:
                raise ValueError(tr('La sauvegarde dépasse la limite de 2 Go ou contient un fichier de plus de 512 Mo.'))
            manifest = {"format": FORMAT, "version": VERSION, "created_at": datetime.now(timezone.utc).isoformat(), "files": files}
            if _incomplete_recovery:
                # This preserves the exact available pre-import state, including
                # metadata for already lost originals. It must never masquerade
                # as a complete archive accepted by inspect_archive.
                manifest.update(format="prepapilot-incomplete", incomplete_documents=incomplete_documents)
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            if len(manifest_bytes) > MAX_MANIFEST or sum(item["size"] for item in files.values()) + len(manifest_bytes) > MAX_TOTAL:
                raise ValueError(tr('La sauvegarde dépasse les limites de taille du format.'))
            # Level 1 keeps extreme repetition below our import compression-ratio limit.
            with ZipFile(temporary_archive, "w", ZIP_DEFLATED, compresslevel=1) as archive:
                archive.writestr("manifest.json", manifest_bytes)
                for name in files:
                    archive.write(folder / name, name)
            with ZipFile(temporary_archive) as archive:
                if archive.testzip():
                    raise ValueError(tr('La sauvegarde n’a pas pu être vérifiée.'))
            os.replace(temporary_archive, destination)
            return manifest
    finally:
        temporary_archive.unlink(missing_ok=True)


def inspect_archive(path, store_type):
    temporary = tempfile.TemporaryDirectory(prefix="prepapilot-import-")
    folder = Path(temporary.name)
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            if not 1 < len(entries) <= MAX_FILES + 1:
                raise ValueError(tr('L’archive contient trop de fichiers ou est vide.'))
            seen, total = set(), 0
            for entry in entries:
                _safe_name(entry.filename)
                key = entry.filename.casefold()
                if key in seen or entry.is_dir() or stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise ValueError(tr('L’archive contient des entrées non autorisées ou dupliquées.'))
                seen.add(key)
                limit = MAX_MANIFEST if entry.filename == "manifest.json" else MAX_DATABASE if entry.filename == "data.sqlite3" else MAX_FILE
                if entry.file_size > limit or (entry.file_size > BLOCK and entry.file_size > max(1, entry.compress_size) * 1000):
                    raise ValueError(tr('Un fichier de l’archive dépasse la limite autorisée.'))
                total += entry.file_size
            if total > MAX_TOTAL or "manifest.json" not in seen or "data.sqlite3" not in seen:
                raise ValueError(tr('L’archive est incomplète ou trop volumineuse.'))
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict) or manifest.get("format") != FORMAT or type(manifest.get("version")) is not int or manifest["version"] != VERSION:
                raise ValueError(tr('Cette archive ne correspond pas à une version prise en charge de PrépaPilot.'))
            files = manifest.get("files")
            if not isinstance(files, dict) or set(files) != {entry.filename for entry in entries if entry.filename != "manifest.json"}:
                raise ValueError(tr('La liste des fichiers de l’archive est incohérente.'))
            for entry in entries:
                if entry.filename == "manifest.json":
                    continue
                expected = files[entry.filename]
                if not isinstance(expected, dict) or type(expected.get("size")) is not int or expected["size"] != entry.file_size or not isinstance(expected.get("sha256"), str) or not re.fullmatch(r"[a-f0-9]{64}", expected["sha256"]):
                    raise ValueError(tr('Les empreintes de l’archive sont invalides.'))
                target = folder.joinpath(*PurePosixPath(entry.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                digest, size = hashlib.sha256(), 0
                with archive.open(entry) as source, target.open("wb") as output:
                    for block in iter(lambda: source.read(BLOCK), b""):
                        size += len(block)
                        if size > expected["size"]:
                            raise ValueError(tr('Un fichier de l’archive dépasse la taille annoncée.'))
                        digest.update(block)
                        output.write(block)
                if size != expected["size"] or digest.hexdigest() != expected["sha256"]:
                    raise ValueError(tr('L’archive est incomplète ou a été modifiée.'))
        validated = folder / "validated.sqlite3"
        counts = _canonical_database(folder / "data.sqlite3", validated, store_type, folder)
        os.replace(validated, folder / "data.sqlite3")
        return ImportPlan(temporary, folder, counts, str(manifest.get("created_at", "")), _signatures(folder))
    except (BadZipFile, sqlite3.Error, ValueError, KeyError, TypeError, RecursionError) as exc:
        temporary.cleanup()
        if isinstance(exc, ValueError):
            raise
        raise ValueError(tr('Ce fichier n’est pas une sauvegarde PrépaPilot valide.')) from exc
    except BaseException:
        temporary.cleanup()
        raise


def apply_import(ctx, plan):
    """Caller confirms the staged counts first. Return the automatic backup path."""
    _busy(ctx)
    if plan.closed or _signatures(plan.folder) != plan.signatures:
        raise ValueError(tr('La sauvegarde préparée a changé. Sélectionne de nouveau le fichier.'))
    # Language belongs to the current installation, even when importing a full
    # archive created on another device with a different interface language.
    current_language = ctx.db.get_setting('desktop_language')
    if current_language not in {'fr', 'en'}:
        current_language = None
    data = Path(ctx.data_dir).resolve()
    backup = data / "backups" / f"avant-import-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}.prepapilot"
    # The safety copy must describe the exact pre-import state, including when
    # an import fails later. Ordinary user exports reconcile pending rewards.
    try:
        export_archive(ctx, backup, reconcile_achievements=False)
    except _IncompleteDocumentError:
        backup = backup.with_name("etat-incomplet-" + backup.stem + ".zip")
        export_archive(ctx, backup, reconcile_achievements=False, _incomplete_recovery=True)
    staging = Path(tempfile.mkdtemp(prefix=".restore-", dir=data))
    old, new = staging / "original", staging / "new"
    old.mkdir()
    new.mkdir()
    try:
        shutil.copyfile(plan.folder / "data.sqlite3", new / "mpsi.sqlite3")
        with closing(sqlite3.connect(new / "mpsi.sqlite3")) as connection, connection:
            _clear_organization_sessions(connection)
            if current_language is None:
                connection.execute("DELETE FROM settings WHERE key='desktop_language'")
            else:
                connection.execute("INSERT OR REPLACE INTO settings(key,value) VALUES (?,?)",
                                   ('desktop_language', json.dumps(current_language)))
        if (plan.folder / "documents").exists():
            shutil.copytree(plan.folder / "documents", new / "documents")
        else:
            (new / "documents").mkdir()
    except BaseException:
        shutil.rmtree(staging)
        raise
    store_type = type(ctx.db)
    moved, installed = [], []
    restored = False
    try:
        ctx.db.close()
        for name in ("mpsi.sqlite3", "mpsi.sqlite3-wal", "mpsi.sqlite3-shm", "documents"):
            target = data / name
            if target.exists():
                os.replace(target, old / name)
                moved.append(name)
        for name in ("mpsi.sqlite3", "documents"):
            os.replace(new / name, data / name)
            installed.append(name)
        ctx.db = store_type(data / "mpsi.sqlite3")
        # Reload can write derived settings and refresh the UI. Keep the original
        # files available until that entire step succeeds as well.
        ctx.reload_data()
        restored = True
    except BaseException:
        # Paths are owned by this operation. Never discard originals if rollback fails.
        # In particular, release the imported database and its WAL/SHM handles
        # before moving files back on Windows after a failed reload.
        ctx.db.close()
        for name in ("mpsi.sqlite3-wal", "mpsi.sqlite3-shm"):
            current = data / name
            if current.exists():
                os.replace(current, new / name)
        for name in installed:
            current = data / name
            if current.exists():
                os.replace(current, new / name)
        for name in moved:
            os.replace(old / name, data / name)
        ctx.db = store_type(data / "mpsi.sqlite3")
        restored = True
        try:
            ctx.reload_data()
        except Exception:
            # The original data is back even if the same I/O error prevents a
            # second refresh. Preserve the initial import error for the caller.
            pass
        raise
    finally:
        if restored:
            shutil.rmtree(staging)
    return backup
