"""Device-local cloud preferences and calendar reminders; never part of exports."""
from .i18n import tr
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import threading
import uuid


CATEGORY_IDS = ('documents', 'grades', 'sleep', 'activities', 'timetable', 'memories', 'preferences')
_LOCK = threading.RLock()


def utc_now():
    return datetime.now(timezone.utc)


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


class CloudPreferences:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'cloud' / 'preferences.json'

    def read(self):
        defaults = dict(selection=list(CATEGORY_IDS), reminder_days=7, reminders=True,
                        first_seen=None, last_success=None, snoozed_until=None,
                        folder_id='', folder_name='', snapshot_id='')
        try:
            if self.path.stat().st_size > 16384:
                return defaults
            saved = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError, RecursionError):
            return defaults
        if not isinstance(saved, dict):
            return defaults
        for key in ('first_seen', 'last_success', 'snoozed_until'):
            if stamp(saved.get(key)) is not None:
                defaults[key] = saved[key]
        selected = saved.get('selection')
        if isinstance(selected, list) and selected and all(isinstance(x, str) and x in CATEGORY_IDS for x in selected):
            defaults['selection'] = list(dict.fromkeys(selected))
        if type(saved.get('reminder_days')) is int and saved['reminder_days'] in (1, 3, 7):
            defaults['reminder_days'] = saved['reminder_days']
        if type(saved.get('reminders')) is bool:
            defaults['reminders'] = saved['reminders']
        for key in ('folder_id', 'snapshot_id'):
            if isinstance(saved.get(key), str) and re.fullmatch(r'[A-Za-z0-9_-]{0,200}', saved[key]):
                defaults[key] = saved[key]
        if isinstance(saved.get('folder_name'), str):
            defaults['folder_name'] = ''.join(c for c in saved['folder_name'] if ord(c) >= 32)[:120]
        return defaults

    def update(self, **changes):
        with _LOCK:
            values = self.read()
            if set(changes) - set(values):
                raise ValueError(tr('Préférence de sauvegarde inconnue.'))
            values.update(changes)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name('.preferences-' + uuid.uuid4().hex + '.tmp')
            try:
                temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(self.path)
            finally:
                temporary.unlink(missing_ok=True)
            return values

    def ensure_started(self, now=None):
        if self.read()['first_seen'] is None:
            self.update(first_seen=(now or utc_now()).isoformat())

    def due(self, now=None):
        now = now or utc_now()
        values = self.read()
        if not values['reminders']:
            return False
        snoozed = stamp(values['snoozed_until'])
        if snoozed is not None and now < snoozed:
            return False
        previous = stamp(values['last_success']) or stamp(values['first_seen'])
        return previous is not None and now - previous >= timedelta(days=values['reminder_days'])

    def snooze(self, now=None):
        self.update(snoozed_until=((now or utc_now()) + timedelta(days=1)).isoformat())

    def record_success(self, result, folder_id, folder_name, selection):
        verified = stamp(result.get('verified_at'))
        if verified is None:
            raise ValueError(tr('La sauvegarde ne dispose pas de confirmation valide.'))
        self.update(last_success=verified.isoformat(), snoozed_until=None,
                    folder_id=folder_id, folder_name=folder_name,
                    selection=list(selection), snapshot_id=result['snapshot_id'])
