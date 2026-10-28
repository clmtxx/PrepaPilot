"""Single-owner, durable SQLite storage for the study companion."""

from __future__ import annotations
from mpsi_desktop.i18n import tr

import csv
from contextlib import contextmanager
from datetime import date
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any

from .grades import KIND_LABELS, SUBJECT_LABELS, normalize_kind, normalize_subject


_GRADE_COLUMNS = "id, subject, kind, score, scale, coefficient, graded_on, label, created_at"
GRADE_COMPARISON_COLUMNS = ("class_average", "rank", "class_size")
_GRADE_SCHEMA = """CREATE TABLE {exists}{table} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL,
    kind TEXT NOT NULL,
    score REAL NOT NULL CHECK(score >= 0),
    scale REAL NOT NULL CHECK(scale > 0 AND score <= scale),
    coefficient REAL NOT NULL DEFAULT 1 CHECK(coefficient > 0),
    graded_on TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    class_average REAL CHECK(class_average IS NULL OR (class_average >= 0 AND class_average <= scale)),
    rank INTEGER,
    class_size INTEGER,
    CHECK((rank IS NULL AND class_size IS NULL) OR
          (rank IS NOT NULL AND class_size IS NOT NULL AND
           typeof(rank) = 'integer' AND typeof(class_size) = 'integer' AND
           rank >= 1 AND class_size >= rank AND class_size <= 2147483647))
)"""


def _number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool):
        raise ValueError(tr('{v0} doit être un nombre.', v0=name))
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(tr('{v0} doit être un nombre.', v0=name)) from None
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError(tr('{v0} doit être un nombre fini{v1}.', v0=name, v1=tr(' strictement positif') if positive else ''))
    return number


def _positive_int(value: Any, name: str) -> int:
    number = _number(value, name, positive=True)
    if not number.is_integer() or number > 2_147_483_647:
        raise ValueError(tr('{v0} doit être un entier positif.', v0=name))
    return int(number)


def _date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(tr('Date attendue au format AAAA-MM-JJ.')) from None
    if parsed.isoformat() != value:
        raise ValueError(tr('Date attendue au format AAAA-MM-JJ.'))
    return value


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(tr('{v0} ne peut pas être vide.', v0=name))
    return value.strip()


def grade_comparison_values(scale, class_average=None, rank=None, class_size=None):
    """Validate optional context, retaining the original grade scale and gaps."""
    if class_average is not None:
        class_average = _number(class_average, tr('La moyenne de classe'))
        if not 0 <= class_average <= scale:
            raise ValueError(tr('La moyenne de classe doit être comprise entre 0 et le barème.'))
    if (rank is None) != (class_size is None):
        raise ValueError(tr('Renseigne à la fois ta position et l’effectif de la classe, ou laisse les deux vides.'))
    if rank is not None:
        rank = _positive_int(rank, tr('La position'))
        class_size = _positive_int(class_size, tr('L’effectif de la classe'))
        if rank > class_size:
            raise ValueError(tr('La position ne peut pas dépasser l’effectif de la classe.'))
    return class_average, rank, class_size


def _grade_values(subject, kind, score, scale, graded_on, label="", coefficient=1,
                  *, class_average=None, rank=None, class_size=None):
    subject, kind = normalize_subject(subject), normalize_kind(kind)
    score, scale = _number(score, tr('La note')), _number(scale, tr('Le barème'), positive=True)
    coefficient = _number(coefficient, tr('Le coefficient'), positive=True)
    if not 0 <= score <= scale:
        raise ValueError(tr('La note doit être comprise entre 0 et le barème.'))
    if (not isinstance(label, str) or len(label.strip()) > 240
            or any(ord(char) < 32 or ord(char) == 127 for char in label)):
        raise ValueError(tr('Le titre doit être du texte sur une seule ligne, de 240 caractères au plus.'))
    comparison = grade_comparison_values(scale, class_average, rank, class_size)
    return subject, kind, score, scale, _date(graded_on), label.strip(), coefficient, *comparison


class Store:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._savepoint_number = 0
        self._connection = sqlite3.connect(self.path, timeout=10, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA journal_mode = WAL")
        try:
            self._initialize_schema()
        except BaseException:
            self._connection.close()
            raise

    def _initialize_schema(self):
        # executescript commits pending work implicitly; individual statements keep
        # the table replacement and its indexes in one rollback-able transaction.
        with self._lock, self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            self._migrate_grade_constraints()
            self._connection.execute(_GRADE_SCHEMA.format(exists="IF NOT EXISTS ", table="grades"))
            schema = """
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    deadline TEXT,
                    estimated_minutes INTEGER NOT NULL CHECK(estimated_minutes > 0),
                    difficulty INTEGER NOT NULL DEFAULT 2 CHECK(difficulty BETWEEN 1 AND 3),
                    completed INTEGER NOT NULL DEFAULT 0 CHECK(completed IN (0, 1)),
                    actual_minutes INTEGER CHECK(actual_minutes > 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS memories (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    text TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS grades_subject_date ON grades(subject, graded_on);
                CREATE INDEX IF NOT EXISTS tasks_status_deadline ON tasks(completed, deadline);
            """
            for statement in schema.split(";"):
                if statement.strip():
                    self._connection.execute(statement)

    def _migrate_grade_constraints(self):
        """Upgrade grade columns and historical checks in one durable transaction."""
        existing = self._connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='grades'").fetchone()
        if existing is None:
            return
        columns = tuple(row["name"] for row in self._connection.execute("PRAGMA table_info(grades)"))
        legacy_checks = re.search(r"\bCHECK\s*\(\s*(?:subject|kind)\s*(?:IN\b|!=)", existing["sql"], re.IGNORECASE)
        if not legacy_checks and all(column in columns for column in GRADE_COMPARISON_COLUMNS):
            return
        sequence = self._connection.execute("SELECT seq FROM sqlite_sequence WHERE name='grades'").fetchone()
        associated = self._connection.execute("SELECT sql FROM sqlite_master WHERE tbl_name='grades' AND type IN ('index','trigger') AND sql IS NOT NULL").fetchall()
        self._connection.execute(_GRADE_SCHEMA.format(exists="", table="grades_universal_migration"))
        copied = _GRADE_COLUMNS + "".join(f", {column}" for column in GRADE_COMPARISON_COLUMNS if column in columns)
        self._connection.execute(f"INSERT INTO grades_universal_migration ({copied}) SELECT {copied} FROM grades")
        self._connection.execute("DROP TABLE grades")
        self._connection.execute("ALTER TABLE grades_universal_migration RENAME TO grades")
        if sequence is not None:
            # Deleted notes may have IDs greater than every remaining row.
            self._connection.execute("DELETE FROM sqlite_sequence WHERE name='grades'")
            self._connection.execute("INSERT INTO sqlite_sequence(name,seq) VALUES ('grades',?)", (sequence["seq"],))
        for row in associated:
            self._connection.execute(row["sql"])

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    @contextmanager
    def _atomic(self):
        """Keep nested storage operations in their caller's transaction."""
        with self._lock:
            self._savepoint_number += 1
            name = f"study_atomic_{self._savepoint_number}"
            self._connection.execute(f"SAVEPOINT {name}")
            try:
                yield
                self._connection.execute(f"RELEASE SAVEPOINT {name}")
            except BaseException:
                if self._connection.in_transaction:
                    self._connection.execute(f"ROLLBACK TO SAVEPOINT {name}")
                    self._connection.execute(f"RELEASE SAVEPOINT {name}")
                raise

    def _insert(self, sql: str, parameters: tuple[Any, ...]) -> int:
        with self._atomic():
            cursor = self._connection.execute(sql, parameters)
            return int(cursor.lastrowid)

    def _change(self, sql: str, parameters: tuple[Any, ...]) -> bool:
        with self._atomic():
            return self._connection.execute(sql, parameters).rowcount > 0

    def _rows(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._connection.execute(sql, parameters).fetchall()]

    def add_grade(self, subject: str, kind: str, score: float, scale: float, graded_on: str,
                  label: str = "", coefficient: float = 1, *, class_average=None,
                  rank=None, class_size=None) -> int:
        return self._insert(
            "INSERT INTO grades(subject, kind, score, scale, graded_on, label, coefficient, class_average, rank, class_size) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _grade_values(subject, kind, score, scale, graded_on, label, coefficient,
                          class_average=class_average, rank=rank, class_size=class_size),
        )

    def update_grade(self, id, subject, kind, score, scale, graded_on, label="", coefficient=1,
                     *, class_average=None, rank=None, class_size=None):
        values = _grade_values(subject, kind, score, scale, graded_on, label, coefficient,
                               class_average=class_average, rank=rank, class_size=class_size)
        return self._change("UPDATE grades SET subject=?,kind=?,score=?,scale=?,graded_on=?,label=?,coefficient=?,class_average=?,rank=?,class_size=? WHERE id=?",
                            (*values, id))

    def grade_kind_labels(self):
        labels = {key: tr(label) for key, label in KIND_LABELS.items()}
        for row in self._rows("SELECT DISTINCT kind FROM grades ORDER BY kind COLLATE NOCASE"):
            labels.setdefault(row["kind"], row["kind"])
        return labels

    def subject_labels(self, include_archived=False):
        labels = {key: tr(label) for key, label in SUBJECT_LABELS.items()}
        for row in self._rows("SELECT DISTINCT subject FROM grades ORDER BY subject"):
            labels.setdefault(row["subject"], row["subject"])
        return labels

    def list_grades(self, subject: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT *, score / scale * 20.0 AS normalized_score, class_average / scale * 20.0 AS normalized_class_average FROM grades"
        parameters: tuple[Any, ...] = ()
        if subject is not None:
            sql += " WHERE subject = ?"
            parameters = (normalize_subject(subject),)
        return self._rows(sql + " ORDER BY graded_on, id", parameters)

    def delete_grade(self, id: int) -> bool:
        return self._change("DELETE FROM grades WHERE id = ?", (id,))

    def add_task(self, title: str, subject: str, kind: str, deadline: str | None,
                 estimated_minutes: int, difficulty: int = 2) -> int:
        difficulty = _positive_int(difficulty, tr('La difficulté'))
        if difficulty > 3:
            raise ValueError(tr('La difficulté doit être comprise entre 1 et 3.'))
        return self._insert(
            "INSERT INTO tasks(title, subject, kind, deadline, estimated_minutes, difficulty) VALUES (?, ?, ?, ?, ?, ?)",
            (_text(title, tr('Le titre')), _text(subject, tr('La matière')).lower(), _text(kind, tr('Le type')).lower(),
             _date(deadline) if deadline is not None else None, _positive_int(estimated_minutes, tr('La durée estimée')), difficulty),
        )

    def list_tasks(self, include_done: bool = False) -> list[dict[str, Any]]:
        sql = "SELECT * FROM tasks"
        if not include_done:
            sql += " WHERE completed = 0"
        rows = self._rows(sql + " ORDER BY deadline IS NULL, deadline, id")
        for row in rows:
            row["completed"] = bool(row["completed"])
        return rows

    def complete_task(self, id: int, actual_minutes: int | None) -> bool:
        if actual_minutes is not None:
            actual_minutes = _positive_int(actual_minutes, tr('La durée réelle'))
        return self._change(
            "UPDATE tasks SET completed = 1, actual_minutes = ?, completed_at = CURRENT_TIMESTAMP WHERE id = ? AND completed = 0",
            (actual_minutes, id),
        )

    def delete_task(self, id: int) -> bool:
        return self._change("DELETE FROM tasks WHERE id = ?", (id,))

    def update_task(self, id: int, *, deadline: str | None = None,
                    estimated_minutes: int | None = None) -> bool:
        """Reschedule an unfinished task; None leaves the corresponding value alone."""
        assignments = []
        parameters: list[Any] = []
        if deadline is not None:
            assignments.append("deadline = ?")
            parameters.append(_date(deadline))
        if estimated_minutes is not None:
            assignments.append("estimated_minutes = ?")
            parameters.append(_positive_int(estimated_minutes, tr('La durée estimée')))
        if not assignments:
            return False
        parameters.append(id)
        return self._change("UPDATE tasks SET " + ", ".join(assignments) + " WHERE id = ? AND completed = 0",
                            tuple(parameters))

    def remember(self, key: str, value: Any) -> None:
        serialized = json.dumps(value, ensure_ascii=False, allow_nan=False)
        self._change("INSERT INTO memories(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (_text(key, tr('La clé')), serialized))

    def memories(self) -> dict[str, Any]:
        return {row["key"]: json.loads(row["value"]) for row in self._rows("SELECT key, value FROM memories ORDER BY key")}

    def forget(self, key: str) -> bool:
        return self._change("DELETE FROM memories WHERE key = ?", (key,))

    def get_setting(self, key: str, default: Any = None) -> Any:
        rows = self._rows("SELECT value FROM settings WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set_setting(self, key: str, value: Any) -> None:
        serialized = json.dumps(value, ensure_ascii=False, allow_nan=False)
        self._change("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (_text(key, tr('La clé')), serialized))

    def save_summary(self, title: str, text: str, mode: str) -> int:
        return self._insert("INSERT INTO summaries(title, text, mode) VALUES (?, ?, ?)",
                            (_text(title, tr('Le titre')), _text(text, tr('Le résumé')), _text(mode, tr('Le mode'))))

    def list_summaries(self) -> list[dict[str, Any]]:
        return self._rows("SELECT id, title, mode, created_at FROM summaries ORDER BY id DESC")

    def get_summary(self, id: int) -> dict[str, Any] | None:
        rows = self._rows("SELECT * FROM summaries WHERE id = ?", (id,))
        return rows[0] if rows else None

    def export_grades_csv(self) -> str:
        output = io.StringIO(newline="")
        columns = ["id", "subject", "kind", "graded_on", "label", "score", "scale", "normalized_score", "coefficient",
                   "class_average", "normalized_class_average", "rank", "class_size"]
        writer = csv.DictWriter(output, fieldnames=columns, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        subjects = self.subject_labels(include_archived=True)
        kinds = self.grade_kind_labels()
        for row in self.list_grades():
            row["subject"] = subjects.get(row["subject"], row["subject"])
            row["kind"] = kinds.get(row["kind"], row["kind"])
            # Names and free evaluation types are also user input.
            for column in ("subject", "kind", "label"):
                if row[column].lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
                    row[column] = "'" + row[column]
            writer.writerow(row)
        return output.getvalue()

    def export_data(self) -> dict[str, Any]:
        """Export stored study data only; credentials belong in environment variables."""
        forbidden = ("token", "secret", "password", "api_key", "apikey", "credential")
        def clean(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()
                        if not any(word in str(key).lower() for word in forbidden)}
            if isinstance(value, list):
                return [clean(item) for item in value]
            return value
        settings = {row["key"]: json.loads(row["value"]) for row in self._rows("SELECT key, value FROM settings ORDER BY key")}
        return {
            "schema_version": 1, "grades": self.list_grades(), "tasks": self.list_tasks(include_done=True),
            "memories": self.memories(), "settings": clean(settings),
            "summaries": self._rows("SELECT * FROM summaries ORDER BY id"),
        }
