"""Recoverable focus timer; only explicitly reviewed work enters the journal.

Ticks remain in memory. A checkpoint records trusted activity every 15 seconds;
neither a suspended computer nor time spent with the app closed counts as work.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
import math
import re
import time
import uuid
from .i18n import tr

SETTING = "desktop_focus_session"
CHECKPOINT_SECONDS = 15
MAX_TICK_GAP = 5
_UNCHANGED = object()


def _stamp(value, *, minute=False):
    if not isinstance(value, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}" if minute else
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?", value):
        raise ValueError(tr("Une date de la séance est invalide."))
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(tr("Une date de la séance est invalide.")) from None
    if result.tzinfo is not None:
        raise ValueError(tr("Les horaires de la séance doivent être locaux."))
    return result


def _segments(values, *, minute=False):
    if not isinstance(values, list) or len(values) > 1000:
        raise ValueError(tr("Une séance peut contenir au plus 1 000 périodes de travail."))
    cleaned, previous = [], None
    for row in values:
        if not isinstance(row, dict) or set(row) != {"start_at", "end_at"}:
            raise ValueError(tr("Une période de travail est incomplète."))
        start, end = (_stamp(row[key], minute=minute) for key in ("start_at", "end_at"))
        if end < start or (minute and end == start) or (previous is not None and start < previous):
            raise ValueError(tr("Les périodes de travail doivent se suivre sans se chevaucher."))
        if end - start > timedelta(days=7 if minute else 1):
            raise ValueError(tr("Une période de travail est trop longue."))
        cleaned.append(dict(start_at=start.isoformat(timespec="minutes" if minute else "microseconds"),
                            end_at=end.isoformat(timespec="minutes" if minute else "microseconds")))
        previous = end
    return cleaned


def validate_focus_session(value, categories=None):
    """Strict, deterministic validation shared by local and cloud imports."""
    if value is None:
        return None
    required = {"version", "id", "status", "category", "title", "target_minutes",
                "segments", "interrupted", "entry_ids"}
    if (not isinstance(value, dict) or not required <= set(value)
            or set(value) - required - {"review_segments"}):
        raise ValueError(tr("Le brouillon de séance est invalide."))
    if (type(value["version"]) is not int or value["version"] != 1
            or not isinstance(value["id"], str) or not re.fullmatch(r"[0-9a-f]{32}", value["id"])
            or value["status"] not in ("running", "paused", "review", "saved")
            or type(value["interrupted"]) is not bool):
        raise ValueError(tr("Le brouillon de séance est invalide."))
    category = value["category"]
    if category is not None and (not isinstance(category, str) or not category or len(category) > 100
                                 or (categories is not None and category not in categories)):
        raise ValueError(tr("La matière de la séance est inconnue."))
    if not isinstance(value["title"], str) or len(value["title"]) > 250:
        raise ValueError(tr("L’objectif de la séance doit contenir au plus 250 caractères."))
    if type(value["target_minutes"]) is not int or not 1 <= value["target_minutes"] <= 240:
        raise ValueError(tr("Choisis une durée de 1 à 240 minutes."))
    segments = _segments(value["segments"])
    if not segments:
        raise ValueError(tr("La séance doit contenir sa période de travail initiale."))
    elapsed = sum((_stamp(row["end_at"]) - _stamp(row["start_at"])).total_seconds() for row in segments)
    if elapsed > value["target_minutes"] * 60 + 0.00001:
        raise ValueError(tr("Le temps mesuré dépasse la durée de la séance."))
    ids = value["entry_ids"]
    if (not isinstance(ids, list) or len(ids) > 1000 or
            any(type(item) is not int or not 0 < item <= 2**63 - 1 for item in ids)
            or len(ids) != len(set(ids)) or (bool(ids) != (value["status"] == "saved"))):
        raise ValueError(tr("Les références du journal sont invalides."))
    review = value.get("review_segments")
    if review is not None:
        review = _segments(review, minute=True)
        if value["status"] not in ("review", "saved"):
            raise ValueError(tr("La correction des horaires nécessite le récapitulatif."))
    return {**deepcopy(value), "segments": segments, "review_segments": review}


class FocusSession:
    def __init__(self, db, now=datetime.now, monotonic=time.monotonic):
        self.db, self._now, self._monotonic = db, now, monotonic
        self._state = None
        self._persisted_id = None
        self._persisted_snapshot = None
        self._last_wall = self._last_mono = self._checkpoint_mono = None
        self.reload()

    @property
    def state(self):
        return deepcopy(self._state) if self._state else {}

    @property
    def status(self):
        return self._state["status"] if self._state else "idle"

    @property
    def active(self):
        return self.status in ("running", "paused", "review")

    @property
    def elapsed_seconds(self):
        return sum((_stamp(row["end_at"]) - _stamp(row["start_at"])).total_seconds()
                   for row in (self._state or {}).get("segments", []))

    @property
    def remaining_seconds(self):
        return max(0, (self._state or {}).get("target_minutes", 25) * 60 - self.elapsed_seconds)

    def reload(self):
        """Drop the old in-memory draft after an import, without writing it back."""
        self._state = validate_focus_session(self.db.get_setting(SETTING),
                                            {*self.db.subject_labels(include_archived=True), "permanence"})
        self._persisted_id = self._state["id"] if self._state else None
        self._persisted_snapshot = deepcopy(self._state)
        self._last_wall = self._last_mono = self._checkpoint_mono = None
        if self.status == "running":
            self._state.update(status="paused", interrupted=True)
        return self.status

    def _check_current(self, *, allow_saved=False):
        stored = validate_focus_session(self.db.get_setting(SETTING))
        identity = stored["id"] if stored else None
        if identity != self._persisted_id:
            raise ValueError(tr("Les données ont changé. Recharge la séance avant de continuer."))
        if allow_saved and stored and stored["status"] == "saved":
            return stored
        if stored != self._persisted_snapshot:
            raise ValueError(tr("Les données ont changé. Recharge la séance avant de continuer."))
        return stored

    def _write(self, value):
        self.db._connection.execute(
            "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (SETTING, json.dumps(value, ensure_ascii=False, allow_nan=False)))

    def _persist(self):
        clean = validate_focus_session(self._state)
        try:
            with self.db._lock, self.db._connection:
                self.db._connection.execute("BEGIN IMMEDIATE")
                self._check_current()
                self._write(clean)
        except Exception:
            # A storage failure must not silently leave an unsaved timer running.
            # Keep captured work in memory so retrying or reviewing remains possible.
            if self.status == "running":
                self._state.update(status="paused", interrupted=True)
            raise
        self._persisted_id = clean["id"] if clean else None
        self._persisted_snapshot = deepcopy(clean)
        self._checkpoint_mono = self._monotonic()

    def start(self, category=None, minutes=25, title=""):
        if self.active:
            raise ValueError(tr("Termine ou ignore la séance en cours avant d’en commencer une autre."))
        if category is not None and category not in {*self.db.subject_labels(), "permanence"}:
            raise ValueError(tr("Choisis une matière active pour cette séance."))
        stamp = self._now()
        previous = self._state
        self._state = validate_focus_session(dict(version=1, id=uuid.uuid4().hex, status="running",
            category=category, title=title, target_minutes=minutes,
            segments=[dict(start_at=stamp.isoformat(timespec="microseconds"), end_at=stamp.isoformat(timespec="microseconds"))],
            interrupted=False, entry_ids=[], review_segments=None))
        self._last_wall, self._last_mono = stamp, self._monotonic()
        try:
            self._persist()
        except Exception:
            self._state = previous
            self._last_wall = self._last_mono = None
            raise
        return self.status

    def tick(self):
        if self.status != "running":
            return self.status
        now, mono = self._now(), self._monotonic()
        wall_delta = (now - self._last_wall).total_seconds()
        delta = mono - self._last_mono
        if (not math.isfinite(delta) or delta < 0 or delta > MAX_TICK_GAP
                or wall_delta < 0 or abs(wall_delta - delta) > 2):
            self._state.update(status="paused", interrupted=True)
            self._persist()
            return self.status
        # Count only the lesser trusted duration. Small clock corrections cannot
        # inflate work or put an interval in the future.
        amount = min(delta, wall_delta, self.remaining_seconds)
        row = self._state["segments"][-1]
        row["end_at"] = (_stamp(row["end_at"]) + timedelta(seconds=amount)).isoformat(timespec="microseconds")
        self._last_wall, self._last_mono = now, mono
        if self.remaining_seconds <= 0.00001:
            self._state["status"] = "review"
            self._persist()
        elif self._checkpoint_mono is None or mono - self._checkpoint_mono >= CHECKPOINT_SECONDS:
            self._persist()
        return self.status

    def pause(self):
        self.tick()
        if self.status == "running":
            self._state["status"] = "paused"
            self._persist()
        return self.status

    def resume(self):
        if self.status != "paused":
            raise ValueError(tr("Cette séance ne peut pas être reprise."))
        now = self._now()
        if self._state["segments"] and now < _stamp(self._state["segments"][-1]["end_at"]):
            raise ValueError(tr("L’horloge a reculé. Corrige les horaires dans le récapitulatif avant d’enregistrer."))
        if len(self._state["segments"]) >= 1000:
            raise ValueError(tr("Cette séance comporte trop de pauses. Termine-la avant d’en commencer une autre."))
        previous = deepcopy(self._state)
        stamp = now.isoformat(timespec="microseconds")
        self._state["segments"].append(dict(start_at=stamp, end_at=stamp))
        self._state.update(status="running", interrupted=False)
        self._last_wall, self._last_mono = now, self._monotonic()
        try:
            self._persist()
        except Exception:
            self._state = previous
            self._last_wall = self._last_mono = None
            raise
        return self.status

    def finish(self):
        self.tick()
        if self.status in ("running", "paused"):
            self._state["status"] = "review"
            self._persist()
        return self.status

    def checkpoint(self):
        self.tick()
        if self.active:
            self._persist()
        return self.status

    def shutdown(self):
        self.tick()
        if self.status == "running":
            self._state.update(status="paused", interrupted=True)
        if self.active:
            self._persist()
        return self.status

    def discard(self):
        with self.db._lock, self.db._connection:
            self.db._connection.execute("BEGIN IMMEDIATE")
            self._check_current()
            self._write(None)
        self._state = None
        self._persisted_id = None
        self._persisted_snapshot = None
        self._last_wall = self._last_mono = self._checkpoint_mono = None

    def review_entries(self):
        if not self._state:
            return []
        if self._state.get("review_segments") is not None:
            return deepcopy(self._state["review_segments"])
        result = []
        for row in self._state["segments"]:
            start, end = _stamp(row["start_at"]), _stamp(row["end_at"])
            lower = start.replace(second=0, microsecond=0)
            if lower < start:
                lower += timedelta(minutes=1)
            upper = end.replace(second=0, microsecond=0)
            if upper > lower:
                result.append(dict(start_at=lower.isoformat(timespec="minutes"), end_at=upper.isoformat(timespec="minutes")))
        return result

    def _review_values(self, category, title, segments):
        if category is not None and category not in {*self.db.subject_labels(), "permanence"}:
            raise ValueError(tr("Choisis une matière active pour enregistrer la séance."))
        if not isinstance(title, str) or len(title) > 250:
            raise ValueError(tr("L’objectif doit contenir au plus 250 caractères."))
        cleaned = _segments(segments, minute=True)
        if any(_stamp(row["end_at"]) > self._now() for row in cleaned):
            raise ValueError(tr("Les horaires réalisés ne peuvent pas se terminer dans le futur."))
        return category, title.strip(), cleaned

    def update_review(self, category, title, segments):
        if self.status != "review":
            raise ValueError(tr("Termine la séance avant de corriger son récapitulatif."))
        category, title, segments = self._review_values(category, title, segments)
        previous = self._state
        self._state = {**previous, "category": category, "title": title, "review_segments": segments}
        try:
            self._persist()
        except Exception:
            self._state = previous
            raise

    def save(self, category=_UNCHANGED, title=None, segments=None):
        if self.status not in ("review", "saved"):
            raise ValueError(tr("Termine la séance avant de l’enregistrer dans le journal."))
        with self.db._lock, self.db._connection:
            self.db._connection.execute("BEGIN IMMEDIATE")
            stored = self._check_current(allow_saved=True)
            if stored and stored["status"] == "saved":
                self._state = stored
                self._persisted_snapshot = deepcopy(stored)
                return list(stored["entry_ids"])
            category = self._state["category"] if category is _UNCHANGED else category
            title = self._state["title"] if title is None else title
            segments = self.review_entries() if segments is None else segments
            category, title, segments = self._review_values(category, title, segments)
            if category is None:
                raise ValueError(tr("Choisis une matière pour enregistrer le temps travaillé."))
            if not segments:
                raise ValueError(tr("La séance ne contient pas encore une minute complète à enregistrer."))
            rows = [self.db._validated_entry(category, row["start_at"], row["end_at"], title, "completed")
                    for row in segments]
            for row in rows:
                self.db._check_time_overlap(row["start_at"], row["end_at"])
            ids = []
            for row in rows:
                cursor = self.db._connection.execute(
                    "INSERT INTO time_entries(category,title,start_at,end_at,status,source,manual_override) "
                    "VALUES (?,?,?,?,?,'manual',1)",
                    tuple(row[key] for key in ("category", "title", "start_at", "end_at", "status")))
                ids.append(int(cursor.lastrowid))
            saved = {**self._state, "status": "saved", "category": category, "title": title,
                     "review_segments": segments, "entry_ids": ids}
            self._write(validate_focus_session(saved))
        self._state = saved
        self._persisted_snapshot = deepcopy(saved)
        return list(ids)
