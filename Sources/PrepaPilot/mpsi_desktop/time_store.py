"""Local activity journal and dated, editable timetable templates."""
from __future__ import annotations

from .i18n import tr
from datetime import date, datetime, time, timedelta
import copy
import json
from pathlib import Path
import re
import sys

from .catalog import CATEGORIES, default_subjects


def local_stamp(value):
    try:
        result = datetime.fromisoformat(str(value))
        if result.tzinfo is not None:
            raise ValueError
        return result.replace(second=0, microsecond=0)
    except (TypeError, ValueError):
        raise ValueError(tr('Choisis une date et une heure locales valides.')) from None


def period_bounds(start=None, end=None):
    lower = datetime.min if start is None else local_stamp(str(start) + "T00:00" if len(str(start)) == 10 else start)
    if end is None:
        upper = datetime.max
    elif len(str(end)) == 10:
        last_day = date.fromisoformat(str(end))
        upper = datetime.max if last_day == date.max else datetime.combine(last_day + timedelta(days=1), time())
    else:
        upper = local_stamp(end)
    if upper <= lower:
        raise ValueError(tr('La fin de la période doit suivre son début.'))
    return lower, upper


DEFAULT_WEEK_ANCHOR = '2026-08-31'


def validate_timetable(data, categories=None):
    if not isinstance(data, dict) or not isinstance(data.get("semesters"), dict):
        raise ValueError(tr('L’emploi du temps doit contenir les deux modèles de planning.'))
    categories = CATEGORIES if categories is None else categories
    if data.get('version', 1) not in (1, 2):
        raise ValueError(tr('Cette version de l’emploi du temps n’est pas prise en charge.'))
    try:
        anchor = date.fromisoformat(data.get('week_anchor', DEFAULT_WEEK_ANCHOR))
    except (TypeError, ValueError):
        raise ValueError(tr('Choisis un lundi de référence pour la semaine A.')) from None
    if anchor.weekday() != 0 or anchor.isoformat() != data.get('week_anchor', DEFAULT_WEEK_ANCHOR):
        raise ValueError(tr('La référence de semaine A doit être un lundi.'))
    result = {"version": 2, "week_anchor": anchor.isoformat(), "semesters": {}}
    for semester in ("S1", "S2"):
        rows = data["semesters"].get(semester)
        if not isinstance(rows, list) or len(rows) > 300:
            raise ValueError(tr('Chaque planning doit contenir au plus 300 créneaux.'))
        clean, identities = [], set()
        for row in rows:
            try:
                identity = row["id"].strip()
                weekday = row["weekday"]
                if type(weekday) is not int:
                    raise ValueError
                if not all(isinstance(row[key], str) and re.fullmatch(r'\d{2}:\d{2}', row[key]) for key in ('start', 'end')):
                    raise ValueError
                start, end = time.fromisoformat(row["start"]), time.fromisoformat(row["end"])
                category = row["category"]
                fallback = categories[category] if isinstance(categories, dict) else CATEGORIES.get(category, category)
                title = str(row.get("title") or fallback).strip()
                week = row.get('week', 'all')
            except (KeyError, ValueError, TypeError, AttributeError):
                raise ValueError(tr('Un créneau de l’emploi du temps est incomplet ou invalide.')) from None
            if not identity or len(identity) > 100 or identity in identities:
                raise ValueError(tr('Chaque créneau doit avoir un identifiant unique dans son planning.'))
            if weekday not in range(7) or category not in categories or start >= end or start.tzinfo or end.tzinfo or week not in ('all', 'A', 'B'):
                raise ValueError(tr('Vérifie le jour, la catégorie et les heures de chaque créneau.'))
            identities.add(identity)
            slot = dict(id=identity, weekday=weekday, start=start.strftime("%H:%M"), end=end.strftime("%H:%M"),
                        category=category, title=title[:250], week=week)
            for other in clean:
                same_week = week == 'all' or other['week'] == 'all' or week == other['week']
                if same_week and weekday == other["weekday"] and slot["start"] < other["end"] and slot["end"] > other["start"]:
                    raise ValueError(tr('Deux créneaux se chevauchent en {value0} : {value1} et {value2}.', value0=semester, value1=title, value2=other['title']))
            clean.append(slot)
        result["semesters"][semester] = sorted(clean, key=lambda x: (x["weekday"], x["start"]))
    return result


def validate_holidays(data):
    """Validate explicit inclusive dates; never infer a school zone or calendar."""
    if not isinstance(data, list):
        raise ValueError(tr('Les vacances doivent être une liste de périodes.'))
    cleaned = []
    for item in data:
        if not isinstance(item, dict):
            raise ValueError(tr('Une période de vacances est invalide.'))
        try:
            start, end = date.fromisoformat(item["start"]), date.fromisoformat(item["end"])
        except (TypeError, ValueError, KeyError):
            raise ValueError(tr('Choisis les dates de début et de fin des vacances.')) from None
        if start.isoformat() != item["start"] or end.isoformat() != item["end"]:
            raise ValueError(tr('Les dates des vacances doivent être au format AAAA-MM-JJ.'))
        if end < start:
            raise ValueError(tr('La fin des vacances doit être le même jour que le début, ou après.'))
        title = item.get("label", tr('Vacances scolaires'))
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            raise ValueError(tr('Le nom des vacances doit contenir entre 1 et 120 caractères.'))
        cleaned.append(dict(start=start.isoformat(), end=end.isoformat(), label=title.strip()))
    cleaned.sort(key=lambda item: item["start"])
    for previous, current in zip(cleaned, cleaned[1:]):
        if current["start"] <= previous["end"]:
            raise ValueError(tr('Cette période chevauche des vacances déjà enregistrées. Choisis une période distincte.'))
    return cleaned


class TimeStoreMixin:
    def init_time_tables(self):
        with self._lock, self._connection:
            self._connection.executescript("""
                CREATE TABLE IF NOT EXISTS time_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL, title TEXT NOT NULL,
                    start_at TEXT NOT NULL, end_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('planned','completed')),
                    source TEXT NOT NULL CHECK(source IN ('manual','timetable')),
                    template_key TEXT UNIQUE,
                    manual_override INTEGER NOT NULL DEFAULT 0,
                    deleted INTEGER NOT NULL DEFAULT 0,
                    CHECK(end_at > start_at)
                );
                CREATE INDEX IF NOT EXISTS time_entries_dates ON time_entries(start_at,end_at);
                CREATE TABLE IF NOT EXISTS time_day_templates (
                    day TEXT PRIMARY KEY, semester TEXT NOT NULL, slots_json TEXT NOT NULL
                );
            """)
        if self.get_setting("desktop_timetable") is None:
            if self.get_subjects() != default_subjects():
                # A personal catalogue without a schedule must not acquire an
                # unrelated legacy timetable (or references to absent subjects).
                today = self._time_now().date()
                timetable = dict(version=2, week_anchor=(today - timedelta(days=today.weekday())).isoformat(),
                                 semesters={"S1": [], "S2": []})
            else:
                root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
                timetable = json.loads((root / "assets" / "timetable.json").read_text(encoding="utf-8"))
            self.set_setting("desktop_timetable", validate_timetable(timetable, self.category_labels(include_archived=True)))
        else:
            previous = self.get_setting('desktop_timetable')
            normalized = validate_timetable(previous, self.category_labels(include_archived=True))
            if normalized != previous:
                self.set_setting('desktop_timetable', normalized)

    def _time_now(self):
        return datetime.now()

    def get_timetable(self):
        return copy.deepcopy(self.get_setting("desktop_timetable"))

    def save_timetable(self, data):
        with self._atomic():
            self.set_setting("desktop_timetable", validate_timetable(data, self.category_labels(include_archived=True)))
            self._refresh_future_days()

    def week_for_day(self, day):
        current = date.fromisoformat(str(day))
        anchor = date.fromisoformat(self.get_timetable().get('week_anchor', DEFAULT_WEEK_ANCHOR))
        return 'A' if ((current - anchor).days // 7) % 2 == 0 else 'B'

    def semester_for_day(self, day):
        day = date.fromisoformat(str(day)).isoformat()
        applicable = [item for item in self.get_setting("time_semester_transitions", []) if item["effective_date"] <= day]
        return max(applicable, key=lambda item: item["effective_date"])["semester"] if applicable else "S1"

    def set_semester(self, semester, effective_date):
        if semester not in {"S1", "S2"}:
            raise ValueError(tr('Choisis l’un des deux plannings.'))
        effective_date = date.fromisoformat(str(effective_date)).isoformat()
        with self._atomic():
            transitions = [item for item in self.get_setting("time_semester_transitions", []) if item["effective_date"] != effective_date]
            transitions.append(dict(effective_date=effective_date, semester=semester))
            self.set_setting("time_semester_transitions", sorted(transitions, key=lambda item: item["effective_date"]))
            self._refresh_future_days()

    def holiday_for_day(self, day):
        day = date.fromisoformat(str(day)).isoformat()
        return next((item for item in validate_holidays(self.get_setting("time_holidays", []))
                     if item["start"] <= day <= item["end"]), None)

    def add_holiday(self, start, end, label=None):
        if label is None:
            label = tr("Vacances scolaires")
        holiday = validate_holidays([dict(start=start, end=end, label=label)])[0]
        with self._atomic():
            holidays = validate_holidays(self.get_setting("time_holidays", []))
            # Saving the same period again is harmless; its label may be corrected.
            holidays = [item for item in holidays if (item["start"], item["end"]) != (holiday["start"], holiday["end"])]
            holidays = validate_holidays(holidays + [holiday])
            self.set_setting("time_holidays", holidays)
            self._refresh_future_days()
        return holiday

    def end_holiday(self, day):
        resume = date.fromisoformat(str(day))
        if resume < self._time_now().date():
            raise ValueError(tr('Choisis une reprise aujourd’hui ou plus tard pour conserver ton historique.'))
        holidays = validate_holidays(self.get_setting("time_holidays", []))
        found = False
        updated = []
        for item in holidays:
            if item["start"] <= resume.isoformat() <= item["end"]:
                found = True
                if item["start"] < resume.isoformat():
                    updated.append({**item, "end": (resume - timedelta(days=1)).isoformat()})
            else:
                updated.append(item)
        if found:
            with self._atomic():
                self.set_setting("time_holidays", updated)
                self._refresh_future_days()
        return found

    def _refresh_future_days(self):
        # Empty holiday snapshots matter too: their lessons must return on resumption.
        days = self._rows("SELECT day FROM time_day_templates WHERE day >= ? UNION SELECT substr(start_at,1,10) AS day FROM time_entries WHERE source='timetable' AND end_at > ?",
                          (self._time_now().date().isoformat(), self._time_now().isoformat(timespec="minutes")))
        for row in days:
            self.ensure_day(row["day"])

    def _validated_entry(self, category, start_at, end_at, title, status):
        categories = self.category_labels(include_archived=True)
        if category not in categories:
            raise ValueError(tr('Choisis une catégorie dans la liste.'))
        if status not in {"planned", "completed"}:
            raise ValueError(tr('Choisis le statut Prévu ou Réalisé.'))
        start, end = local_stamp(start_at), local_stamp(end_at)
        if end <= start:
            raise ValueError(tr('La fin doit suivre le début. Pour une nuit, choisis la date du lendemain.'))
        if end - start > timedelta(days=7):
            raise ValueError(tr('Une activité doit durer au plus sept jours.'))
        if status == "completed" and end > self._time_now():
            raise ValueError(tr('Cette activité n’est pas encore terminée. Garde le statut Prévu jusqu’à sa fin.'))
        if not isinstance(title, str) or len(title) > 250:
            raise ValueError(tr('Le titre doit contenir au plus 250 caractères.'))
        return dict(category=category, title=title.strip() or categories[category],
                    start_at=start.isoformat(timespec="minutes"), end_at=end.isoformat(timespec="minutes"), status=status)

    def _check_time_overlap(self, start_at, end_at, exclude_id=None):
        conflicts = self._rows("SELECT id,title,start_at,end_at FROM time_entries WHERE deleted=0 AND start_at < ? AND end_at > ? AND id != ? LIMIT 1",
                               (end_at, start_at, exclude_id or -1))
        if conflicts:
            row = conflicts[0]
            raise ValueError(tr('Ce créneau chevauche « {value0} » ({value1}–{value2}). Modifie ou supprime d’abord cette activité pour éviter de compter le temps deux fois.', value0=row['title'], value1=row['start_at'][11:], value2=row['end_at'][11:]))

    def add_time_entry(self, category, start_at, end_at, title="", status="completed", source="manual"):
        if source != "manual":
            raise ValueError(tr('Les cours prévus sont ajoutés depuis l’emploi du temps.'))
        if category not in self.category_labels():
            raise ValueError(tr('Cette matière est archivée. Réactive-la pour ajouter une activité.'))
        values = self._validated_entry(category, start_at, end_at, title, status)
        with self._atomic():
            self._check_time_overlap(values["start_at"], values["end_at"])
            cursor = self._connection.execute(
                "INSERT INTO time_entries(category,title,start_at,end_at,status,source,manual_override) VALUES (?,?,?,?,?,'manual',1)",
                tuple(values[key] for key in ("category", "title", "start_at", "end_at", "status")))
            return int(cursor.lastrowid)

    def update_time_entry(self, identity, **fields):
        with self._atomic():
            rows = self._rows("SELECT * FROM time_entries WHERE id=? AND deleted=0", (identity,))
            if not rows:
                raise ValueError(tr('Cette activité n’existe plus.'))
            allowed = {"category", "title", "start_at", "end_at", "status"}
            if set(fields) - allowed:
                raise ValueError(tr('Un champ de l’activité n’est pas modifiable.'))
            row = rows[0]
            if fields.get('category', row['category']) != row['category'] and fields['category'] not in self.category_labels():
                raise ValueError(tr('Choisis une matière active pour reclasser cette activité.'))
            values = self._validated_entry(**{key: fields.get(key, row[key]) for key in allowed})
            self._check_time_overlap(values["start_at"], values["end_at"], identity)
            self._connection.execute("UPDATE time_entries SET category=?,title=?,start_at=?,end_at=?,status=?,manual_override=1 WHERE id=?",
                                     tuple(values[key] for key in ("category", "title", "start_at", "end_at", "status")) + (identity,))
        return True

    def delete_time_entry(self, identity):
        # Keep cancellations tied to their date so autofill never resurrects them.
        return self._change("UPDATE time_entries SET deleted=1,manual_override=1 WHERE id=? AND deleted=0", (identity,))

    def list_time_entries(self, start=None, end=None):
        lower, upper = period_bounds(start, end)
        rows = self._rows("SELECT * FROM time_entries WHERE deleted=0 AND start_at < ? AND end_at > ? ORDER BY start_at,id",
                          (upper.isoformat(timespec="minutes"), lower.isoformat(timespec="minutes")))
        for row in rows:
            row["minutes"] = int((local_stamp(row["end_at"]) - local_stamp(row["start_at"])).total_seconds() // 60)
        return rows

    def time_totals(self, start=None, end=None, status="completed"):
        if status not in {"completed", "planned"}:
            raise ValueError(tr('Statut de total invalide.'))
        lower, upper = period_bounds(start, end)
        totals = {}
        for row in self.list_time_entries(start, end):
            if row["status"] != status:
                continue
            # A future timestamp can never become completed work through import.
            if status == "completed" and local_stamp(row["end_at"]) > self._time_now():
                continue
            minutes = int((min(upper, local_stamp(row["end_at"])) - max(lower, local_stamp(row["start_at"]))).total_seconds() // 60)
            totals[row["category"]] = totals.get(row["category"], 0) + minutes
        return totals

    def complete_day(self, day):
        day = date.fromisoformat(str(day)).isoformat()
        cutoff = self._time_now().isoformat(timespec="minutes")
        lower, upper = period_bounds(day, day)
        with self._atomic():
            result = self._connection.execute("UPDATE time_entries SET status='completed',manual_override=1 WHERE deleted=0 AND status='planned' AND start_at<? AND end_at>? AND end_at<=?", (upper.isoformat(timespec="minutes"), lower.isoformat(timespec="minutes"), cutoff))
            return result.rowcount

    def ensure_day(self, day):
        current = date.fromisoformat(str(day))
        day = current.isoformat()
        semester = self.semester_for_day(day)
        week = self.week_for_day(day)
        active_categories = self.category_labels()
        slots = [slot for slot in self.get_timetable()["semesters"][semester]
                 if slot["weekday"] == current.weekday() and slot.get('week', 'all') in ('all', week)
                 and slot['category'] in active_categories]
        if self.holiday_for_day(day):
            slots = []
        snapshots = self._rows("SELECT * FROM time_day_templates WHERE day=?", (day,))
        current_time = self._time_now()
        if snapshots and current < current_time.date():
            slots = json.loads(snapshots[0]["slots_json"])
            semester = snapshots[0]["semester"]
        elif snapshots and current == current_time.date():
            # Keep this morning as it was recorded, even after resuming courses
            # at midday. Only the remaining part of today follows new settings.
            old_slots = json.loads(snapshots[0]["slots_json"])
            ended = [slot for slot in old_slots if local_stamp(f"{day}T{slot['end']}") <= current_time]
            old_ids = {slot["id"] for slot in ended}
            upcoming = [slot for slot in slots if local_stamp(f"{day}T{slot['end']}") > current_time and slot["id"] not in old_ids]
            slots = ended + upcoming
        desired = {f"{day}|{slot['id']}": slot for slot in slots}
        now = current_time.isoformat(timespec="minutes")
        created, conflicts = 0, []
        with self._atomic():
            self._connection.execute("INSERT INTO time_day_templates(day,semester,slots_json) VALUES (?,?,?) ON CONFLICT(day) DO UPDATE SET semester=excluded.semester,slots_json=excluded.slots_json",
                                     (day, semester, json.dumps(slots, ensure_ascii=False)))
            existing = self._rows("SELECT * FROM time_entries WHERE template_key LIKE ?", (day + "|%",))
            previous_ids = {row["template_key"]: row["id"] for row in existing}
            # Preserve past sessions, confirmations and exceptions; only reconcile upcoming automatic slots.
            for row in existing:
                if row["manual_override"] or row["deleted"] or row["end_at"] <= now:
                    continue
                slot = desired.get(row["template_key"])
                unchanged = slot and (row["category"],row["title"],row["start_at"],row["end_at"]) == (slot["category"],slot["title"],f"{day}T{slot['start']}",f"{day}T{slot['end']}")
                if not unchanged and row["status"] == "planned":
                    self._connection.execute("DELETE FROM time_entries WHERE id=?", (row["id"],))
            for key, slot in desired.items():
                if self._rows("SELECT id FROM time_entries WHERE template_key=?", (key,)):
                    continue
                start_at, end_at = f"{day}T{slot['start']}", f"{day}T{slot['end']}"
                try:
                    self._check_time_overlap(start_at, end_at)
                except ValueError as exc:
                    conflicts.append(str(exc))
                    continue
                self._connection.execute("INSERT INTO time_entries(id,category,title,start_at,end_at,status,source,template_key) VALUES (?,?,?,?,?,'planned','timetable',?)",
                                         (previous_ids.get(key), slot["category"], slot["title"], start_at, end_at, key))
                created += 1
        return {"created": created, "conflicts": conflicts}

    def ensure_range(self, start, end):
        first, last = date.fromisoformat(str(start)), date.fromisoformat(str(end))
        if last < first or (last - first).days > 366:
            raise ValueError(tr('Choisis une période de 367 jours au maximum.'))
        result = {"created": 0, "conflicts": []}
        with self._atomic():
            for offset in range((last - first).days + 1):
                day = self.ensure_day((first + timedelta(days=offset)).isoformat())
                result["created"] += day["created"]
                result["conflicts"].extend(day["conflicts"])
        return result
