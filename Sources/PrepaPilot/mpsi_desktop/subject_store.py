"""Stable subject identities and personal labels, with archival preservation."""
from __future__ import annotations

import copy
import json
import re

from .i18n import tr

from .catalog import SUBJECTS, FIXED_CATEGORIES, ACTIVITY_COLORS, default_subjects


def validate_subjects(data):
    if not isinstance(data, list) or len(data) > 200:
        raise ValueError(tr('La liste peut contenir au plus 200 matières.'))
    clean, identities, names = [], set(), set()
    for row in data:
        if not isinstance(row, dict):
            raise ValueError(tr('Une matière est invalide.'))
        identity, name, color, active = (row.get(key) for key in ('id', 'name', 'color', 'active'))
        if (not isinstance(identity, str) or
                (identity not in SUBJECTS and not re.fullmatch(r'subject_[0-9a-f]{32}', identity))):
            raise ValueError(tr('L’identifiant d’une matière est invalide.'))
        if identity in identities:
            raise ValueError(tr('Chaque matière doit avoir un identifiant unique.'))
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 60 or any(ord(char) < 32 for char in name):
            raise ValueError(tr('Le nom d’une matière doit contenir entre 1 et 60 caractères.'))
        name = name.strip()
        if name.casefold() in names:
            raise ValueError(tr('Deux matières ne peuvent pas porter le même nom.'))
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError(tr('Choisis une couleur valide pour chaque matière.'))
        if type(active) is not bool:
            raise ValueError(tr('Indique si chaque matière est active ou archivée.'))
        clean.append(dict(id=identity, name=name, color=color.upper(), active=active))
        identities.add(identity)
        names.add(name.casefold())
    return clean


def restore_legacy_grade_subjects(subjects, referenced_ids):
    """Recover the former fixed note subjects removed by an older empty setup.

    Only the three historically supported grade IDs can be recovered without a
    catalogue entry. Unknown custom IDs remain invalid instead of being invented.
    """
    cleaned = validate_subjects(subjects)
    identities = {row['id'] for row in cleaned}
    names = {row['name'].casefold() for row in cleaned}
    defaults = {row['id']: row for row in default_subjects()}
    for identity in sorted((set(referenced_ids) & {'maths', 'physique', 'anglais'}) - identities):
        original = defaults[identity]
        name = original['name']
        suffix = ' (archives)'
        attempt = 1
        while name.casefold() in names:
            name = original['name'][:60-len(suffix)] + suffix
            attempt += 1
            suffix = f' (archives {attempt})'
        cleaned.append({**original, 'name': name, 'active': False})
        names.add(name.casefold())
    return validate_subjects(cleaned)


class SubjectStoreMixin:
    def init_subjects(self):
        subjects = self.get_setting('desktop_subjects')
        references = [row['subject'] for row in self._rows('SELECT DISTINCT subject FROM grades')]
        cleaned = restore_legacy_grade_subjects(default_subjects() if subjects is None else subjects, references)
        if cleaned != subjects:
            self.set_setting('desktop_subjects', cleaned)

    def get_subjects(self, include_archived=True):
        rows = validate_subjects(self.get_setting('desktop_subjects', default_subjects()))
        return copy.deepcopy([row for row in rows if include_archived or row['active']])

    def subject_labels(self, include_archived=False):
        return {row['id']: row['name'] for row in self.get_subjects(include_archived)}

    def category_labels(self, include_archived=False):
        return {**{key: tr(label) for key, label in FIXED_CATEGORIES.items()}, **self.subject_labels(include_archived)}

    def category_color(self, key):
        subject = next((row for row in self.get_subjects() if row['id'] == key), None)
        return subject['color'] if subject else ACTIVITY_COLORS.get(key, '#68717D')

    def study_categories(self):
        # An archived subject's earlier work must remain in historical totals.
        return set(self.subject_labels(include_archived=True)) - {'eps', 'autre'}

    def _preserved_subjects(self, subjects, *, initial_setup=False):
        cleaned = validate_subjects(subjects)
        if initial_setup and self.get_setting('setup_completed') is False:
            tables = {row['name'] for row in self._rows("SELECT name FROM sqlite_master WHERE type='table'")}
            referenced = any(table in tables and self._rows(f'SELECT 1 FROM {table} LIMIT 1')
                             for table in ('grades', 'documents', 'time_entries', 'time_day_templates'))
            if not referenced:
                # These are only first-run suggestions, not the user's subjects.
                # Starting from zero must not reintroduce the example catalogue.
                return cleaned
        identities = {row['id'] for row in cleaned}
        cleaned.extend({**row, 'active': False} for row in self.get_subjects() if row['id'] not in identities)
        return validate_subjects(cleaned)

    def save_subjects(self, subjects):
        with self._atomic():
            cleaned = self._preserved_subjects(subjects)
            self.set_setting('desktop_subjects', cleaned)
            self._refresh_future_days()
        return copy.deepcopy(cleaned)

    def save_setup(self, subjects, timetable, *, schedule_labels=None):
        from .time_store import validate_timetable
        with self._atomic():
            cleaned = self._preserved_subjects(subjects, initial_setup=True)
            categories = {**{key: tr(label) for key, label in FIXED_CATEGORIES.items()},
                          **{row['id']: row['name'] for row in cleaned}}
            schedule = validate_timetable(timetable, categories=categories)
            settings = {'desktop_subjects': cleaned, 'desktop_timetable': schedule, 'setup_completed': True}
            if schedule_labels is not None:
                from .study_profile import validate_schedule_labels
                settings['desktop_schedule_labels'] = validate_schedule_labels(schedule_labels)
            for key, value in settings.items():
                self._connection.execute('INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                         (key, json.dumps(value, ensure_ascii=False)))
            self._refresh_future_days()
        return copy.deepcopy(schedule)
