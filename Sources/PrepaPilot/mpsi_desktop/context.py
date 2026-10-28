"""Application state and migration of earlier portable installations."""
from __future__ import annotations
from .i18n import tr, language, set_language as select_language, LANGUAGES
from contextlib import closing
from datetime import date
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import uuid
from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool
from mpsi_core.storage import Store
from mpsi_core.grades import normalize_subject
from .document_store import DocumentStoreMixin
from .time_store import TimeStoreMixin
from .subject_store import SubjectStoreMixin


MIN_SCHOOL_YEAR = 2000
MAX_SCHOOL_YEAR = 2200


def current_school_year(day=None):
    """Return the year of the September start, using the local calendar."""
    day = day or date.today()
    return day.year if day.month >= 9 else day.year - 1


def school_year_bounds(year):
    """Calendar boundaries, using actual dates so leap days remain included."""
    if type(year) is not int or not MIN_SCHOOL_YEAR <= year <= MAX_SCHOOL_YEAR:
        raise ValueError(tr('Choisis une année scolaire valide.'))
    return date(year, 9, 1), date(year + 1, 9, 1)


def _valid_school_year(value):
    return type(value) is int and MIN_SCHOOL_YEAR <= value <= MAX_SCHOOL_YEAR


def asset_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"


def app_root():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def _installed_data_directory(base):
    """Opt in to per-user storage only for a recognised installer marker."""
    try:
        marker = json.loads((base / "installation.json").read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(marker, dict) or marker.get("data_mode") != "localappdata":
        return None
    local_app_data = os.environ.get("LOCALAPPDATA")
    local = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return local / "PrepaPilot" / "data"


def snapshot_database(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target:
        raise ValueError(tr("Choisis un fichier différent de la base active."))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst)
                if dst.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError(tr("La copie de la base n’a pas pu être vérifiée."))
        temporary.replace(target)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_data(root=None, *, migrate=True):
    """Prepare portable data, or isolated per-user data for an installed app.

    An explicit root always keeps its portable meaning (including self-tests).
    Installer mode never searches for or imports neighbouring personal data.
    """
    base = Path(root or app_root()).resolve()
    installed_data = _installed_data_directory(base) if root is None else None
    data = installed_data.resolve() if installed_data is not None else base / "data"
    data.mkdir(parents=True, exist_ok=True)
    if installed_data is not None:
        return data, False
    database = data / "mpsi.sqlite3"
    candidates = [base.parent / "PrepaPilot" / "data", base.parent / "CompagnonMPSI" / "data",
                  base.parent / "mpsi-compagnon" / "data"]
    workspace = base.parent.parent
    for archive in (workspace / "Archives" / "Anciennes-versions", workspace / "je-veux-que-tu-me-cr-2"):
        candidates.extend(archive / "outputs" / name / "data" for name in ("PrepaPilot", "CompagnonMPSI", "mpsi-compagnon"))
    migrated = False
    if migrate and not database.exists():
        legacy = next((p for p in candidates if p.resolve() != data.resolve() and (p / "mpsi.sqlite3").is_file()), None)
        if legacy:
            # Publish the database last: a failed copy must remain retryable.
            staging = Path(tempfile.mkdtemp(prefix=".migration-", dir=data))
            installed_documents = False
            moved_documents = False
            cleanup = True
            try:
                snapshot_database(legacy / "mpsi.sqlite3", staging / "mpsi.sqlite3")
                if (legacy / "documents").is_dir():
                    if (data / "documents").exists():
                        shutil.copytree(data / "documents", staging / "documents")
                    shutil.copytree(legacy / "documents", staging / "documents", dirs_exist_ok=True)
                    if (data / "documents").exists():
                        (data / "documents").replace(staging / "previous-documents")
                        moved_documents = True
                    (staging / "documents").replace(data / "documents")
                    installed_documents = True
                (staging / "mpsi.sqlite3").replace(database)
            except BaseException:
                try:
                    if installed_documents:
                        (data / "documents").replace(staging / "documents")
                    if moved_documents:
                        (staging / "previous-documents").replace(data / "documents")
                except OSError:
                    cleanup = False  # Keep recoverable originals if rollback fails.
                    raise
                raise
            finally:
                if cleanup:
                    shutil.rmtree(staging)
            migrated = True
    return data, migrated


class DesktopStore(SubjectStoreMixin, DocumentStoreMixin, TimeStoreMixin, Store):
    def __init__(self, path):
        super().__init__(path)
        try:
            if self.get_setting('setup_completed') is None:
                existing = self.get_setting('desktop_timetable') is not None
                tables = {row['name'] for row in self._rows("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('grades', 'memories', 'summaries', 'documents', 'time_entries'):
                    if table in tables and self._rows(f'SELECT 1 FROM {table} LIMIT 1'):
                        existing = True
                        break
                self.set_setting('setup_completed', existing)
            self.init_subjects()
            self.init_document_tables()
            self.init_time_tables()
            self._change("DELETE FROM settings WHERE key LIKE 'desktop_ai%' OR key IN ('external_paused','desktop_plan','desktop_reminders','desktop_last_reminder','desktop_chat_history')", ())
        except BaseException:
            self.close()
            raise

    def _grade_subject(self, subject, *, retained_subject=None):
        subject = normalize_subject(subject)
        if subject not in self.subject_labels() and subject != retained_subject:
            raise ValueError(tr("Choisis une matière active pour cette note."))
        return subject

    def add_grade(self, subject, kind, score, scale, graded_on, label="", coefficient=1,
                  *, class_average=None, rank=None, class_size=None):
        with self._lock:
            subject = self._grade_subject(subject)
            return super().add_grade(subject, kind, score, scale, graded_on, label, coefficient,
                                     class_average=class_average, rank=rank, class_size=class_size)

    def update_grade(self, id, subject, kind, score, scale, graded_on, label="", coefficient=1,
                     *, class_average=None, rank=None, class_size=None):
        with self._lock:
            previous = self._rows("SELECT subject FROM grades WHERE id=?", (id,))
            if not previous:
                return False
            subject = self._grade_subject(subject, retained_subject=previous[0]["subject"])
            return super().update_grade(id, subject, kind, score, scale, graded_on, label, coefficient,
                                        class_average=class_average, rank=rank, class_size=class_size)


class _JobSignals(QObject):
    success = Signal(object)
    failure = Signal(str)
    finished = Signal()


class _Job(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = _JobSignals()

    @Slot()
    def run(self):
        try:
            result = self.work()
        except ValueError as exc:
            self.signals.failure.emit(str(exc))
        except Exception as exc:
            self.signals.failure.emit(tr("Le traitement n’a pas abouti ({error}). Vérifie le fichier et l’espace disponible.", error=type(exc).__name__))
        else:
            self.signals.success.emit(result)
        finally:
            self.signals.finished.emit()


class _DataWatch(QObject):
    """A scoped connection whose lifetime follows its page, not the context."""
    def __init__(self, ctx, callback, domains):
        owner = getattr(callback, '__self__', None)
        super().__init__(owner if isinstance(owner, QObject) else ctx)
        self.ctx, self.callback, self.domains = ctx, callback, frozenset(domains)

    @Slot()
    def dispatch(self):
        changed = self.ctx.change_domains
        if changed is None or not self.domains or self.domains.intersection(changed):
            self.callback()


class AppContext(QObject):
    data_changed = Signal()
    data_replaced = Signal()
    theme_changed = Signal(str)
    language_changed = Signal(str)
    notice = Signal(str)
    jobs_changed = Signal(int)
    achievements_unlocked = Signal(object)

    def __init__(self, data_dir, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = DesktopStore(self.data_dir / "mpsi.sqlite3")
        self.language = self.db.get_setting("desktop_language", "fr")
        if self.language not in LANGUAGES:
            self.language = "fr"
        select_language(self.language)
        self.change_domains = None
        self.sync_school_years(emit=False)
        self.theme = self.db.get_setting("desktop_theme", "light")
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(2)
        self._jobs = set()
        self._achievement_key = None
        self._achievement_report = None
        self.achievement_report()
        # Device update preferences and downloaded programs stay outside school
        # exports. Constructing the controller never makes a network request.
        from .app_updates import read_channel, UpdateError
        from .update_panel import UpdateController
        try:
            repository = read_channel(asset_root())
        except UpdateError:
            repository = None
        self.updates = UpdateController(self, repository=repository,
            installed=_installed_data_directory(app_root()) is not None)
        self.update_checks_enabled = False
        self.pending_installer = None

    def achievement_report(self):
        """Reconcile once per journal revision, sharing the result with the UI."""
        from .achievements import reconcile
        with self.db._lock:
            now = self.db._time_now().replace(second=0, microsecond=0)
            key = (self.db, self.db._connection.total_changes, now)
            if key != self._achievement_key:
                self._achievement_report = reconcile(self.db, now=now)
                self._achievement_key = (self.db, self.db._connection.total_changes, now)
            return self._achievement_report

    @property
    def year(self):
        return self.db.get_setting("school_year", current_school_year())

    @property
    def available_years(self):
        return list(self._available_years)

    def sync_school_years(self, *, emit=True):
        """Normalize old imports without removing historic notes or year records."""
        floor = current_school_year()
        initial = self.db.get_setting('school_year_start')
        if not _valid_school_year(initial) or initial > floor:
            initial = floor
        saved = self.db.get_setting('school_years', [])
        years = {value for value in saved if _valid_school_year(value)} if isinstance(saved, list) else set()
        selected = self.db.get_setting('school_year', floor)
        if _valid_school_year(selected):
            years.add(selected)
        else:
            selected = floor
        years.update((initial, floor))
        selected = max(selected, floor)
        values = {'school_year_start': initial, 'school_years': sorted(years), 'school_year': selected}
        changed = False
        with self.db._lock, self.db._connection:
            for key, value in values.items():
                if self.db.get_setting(key) != value:
                    self.db.set_setting(key, value)
                    changed = True
        available = [year for year in sorted(years) if year >= floor]
        changed = changed or available != getattr(self, '_available_years', [])
        self._available_years = available
        if changed and emit:
            self.mark_changed('year')
        return changed

    def add_school_year(self):
        self.sync_school_years(emit=False)
        year = self._available_years[-1] + 1
        if year > MAX_SCHOOL_YEAR:
            raise ValueError(tr('La dernière année prise en charge est déjà disponible.'))
        years = self.db.get_setting('school_years') + [year]
        with self.db._lock, self.db._connection:
            self.db.set_setting('school_years', years)
            self.db.set_setting('school_year', year)
        self._available_years.append(year)
        self.mark_changed('year')
        return year

    def grades(self, subject=None):
        year = self.year
        return [row for row in self.db.list_grades(subject)
                if f"{year}-08-01" <= row["graded_on"] < f"{year+1}-08-01"]

    def set_year(self, year):
        normalized = self.sync_school_years(emit=False)
        if not _valid_school_year(year) or year not in self._available_years:
            raise ValueError(tr('Choisis une année disponible ou ajoute la suivante.'))
        if year != self.year:
            self.db.set_setting('school_year', year)
            self.mark_changed('year')
        elif normalized:
            self.mark_changed('year')

    def watch_data(self, callback, *domains):
        watcher = _DataWatch(self, callback, domains)
        self.data_changed.connect(watcher.dispatch)
        return watcher.dispatch

    def mark_changed(self, *domains):
        # Existing imports and callers without a scope still refresh everything.
        # Preserve the outer scope if a synchronous receiver emits another change.
        previous = self.change_domains
        awards = []
        if not domains or {'activities', 'subjects', 'timetable'}.intersection(domains):
            previous_key = self._achievement_key
            report = self.achievement_report()
            if self._achievement_key != previous_key:
                awards = report['new_awards']
        self.change_domains = frozenset(domains) if domains else None
        try:
            self.data_changed.emit()
        finally:
            self.change_domains = previous
        if awards:
            self.achievements_unlocked.emit(awards)
            points = sum(item['points'] for item in awards)
            message = "{count} récompense débloquée · +{points} XP. À découvrir dans Progression → Succès." if len(awards) == 1 else "{count} récompenses débloquées · +{points} XP. À découvrir dans Progression → Succès."
            self.notice.emit(tr(message, count=len(awards), points=points))

    def set_theme(self, theme):
        if theme in {"light", "dark"} and theme != self.theme:
            self.theme = theme
            self.db.set_setting("desktop_theme", theme)
            self.theme_changed.emit(theme)

    def set_language(self, value):
        if value not in LANGUAGES:
            raise ValueError("Unsupported language")
        if self.busy:
            raise ValueError(tr("Attends la fin du traitement en cours avant de changer de langue."))
        self.db.set_setting("desktop_language", value)
        changed = value != self.language
        self.language = value
        select_language(value)
        if changed:
            self._achievement_key = None
            self._achievement_report = None
            self.language_changed.emit(value)

    def reload_data(self):
        self._achievement_key = None
        self.achievement_report()
        self.sync_school_years(emit=False)
        self.theme = self.db.get_setting("desktop_theme", "light")
        self.theme_changed.emit(self.theme)
        self.data_replaced.emit()
        self.mark_changed()

    @property
    def busy(self):
        return bool(self._jobs)

    def run_job(self, work_callable, on_success, on_error=None, on_finished=None):
        job = _Job(work_callable)
        self._jobs.add(job)
        job.signals.success.connect(on_success)
        job.signals.failure.connect(on_error or self.notice.emit)
        job.signals.finished.connect(lambda: self._finish_job(job))
        if on_finished is not None:
            job.signals.finished.connect(on_finished)
        self.jobs_changed.emit(len(self._jobs))
        self.pool.start(job)
        return job

    def _finish_job(self, job):
        self._jobs.discard(job)
        self.jobs_changed.emit(len(self._jobs))

    def close(self):
        self.pool.waitForDone()
        self.db.close()
