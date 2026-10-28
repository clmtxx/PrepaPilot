"""Permanent, portable rewards calculated from completed journal activities.

The ledger stores award identities and first-awarded dates only. Requirements
and points always come from this catalog. Reading a snapshot never writes;
reconciling adds missing awards without retracting ones already earned.
"""
from __future__ import annotations
from .i18n import tr, language, format_date

from collections import defaultdict
from contextlib import nullcontext
from datetime import date, datetime, time, timedelta
import re

from .time_store import local_stamp


SETTING = 'desktop_achievements'
MAX_AWARDS = 20000
TIERS = (
    {'name': 'Bronze', 'points': 100},
    {'name': 'Argent', 'points': 200},
    {'name': 'Or', 'points': 400},
    {'name': 'Platine', 'points': 700},
    {'name': 'Diamant', 'points': 1000},
)
# Keep every retired catalog immutable: previously earned medals must not
# masquerade as harder milestones after an update or restoration.
LEGACY_FAMILIES = (
    {'id': 'work_total', 'title': 'Chaque heure compte',
     'description': 'Tout le travail accompli, cours et travail personnel réunis.',
     'unit': 'minutes', 'targets': (300, 1500, 6000, 15000, 30000)},
    {'id': 'work_week', 'title': 'Une semaine qui avance',
     'description': 'Ton meilleur total sur une semaine, du lundi au dimanche.',
     'unit': 'minutes', 'targets': (300, 600, 1200, 1800, 2400)},
    {'id': 'work_month', 'title': 'La force de la constance',
     'description': 'Ton meilleur total sur un mois du calendrier.',
     'unit': 'minutes', 'targets': (1200, 2400, 4800, 7200, 9600)},
    {'id': 'work_week', 'award_prefix': 'work_week_v2', 'title': 'Une semaine qui avance',
     'description': 'Ton meilleur total sur une semaine, du lundi au dimanche, cours inclus.',
     'unit': 'minutes', 'targets': (1500, 2100, 2700, 3300, 3600)},
    {'id': 'work_month', 'award_prefix': 'work_month_v2', 'title': 'La force de la constance',
     'description': 'Ton meilleur total sur un mois du calendrier, cours inclus.',
     'unit': 'minutes', 'targets': (6000, 8400, 10800, 13200, 15000)},
)
LEGACY_QUESTS = (
    {'id': 'work_week', 'title': 'Ton cap de la semaine',
     'description': 'Cumule 5 h de cours ou de travail personnel cette semaine.',
     'period': 'week', 'metric': 'work', 'target': 300, 'unit': 'minutes', 'points': 100},
    {'id': 'study_days', 'title': 'Trois rendez-vous',
     'description': 'Travaille au moins 30 min sur trois jours de la semaine.',
     'period': 'week', 'metric': 'study_days', 'target': 3, 'unit': 'days', 'points': 120},
    {'id': 'study_month', 'title': 'Un mois qui avance',
     'description': 'Travaille au moins 30 min sur douze jours de ce mois.',
     'period': 'month', 'metric': 'study_days', 'target': 12, 'unit': 'days', 'points': 300},
)
FAMILIES = (
    {'id': 'work_total', 'award_prefix': 'work_total_v2', 'title': 'Chaque heure compte',
     'description': 'Tout le travail accompli, cours et travail personnel réunis.',
     'unit': 'minutes', 'targets': (3000, 9000, 24000, 48000, 90000)},
    {'id': 'work_week', 'award_prefix': 'work_week_v3', 'title': 'Une semaine qui avance',
     'description': 'Ton meilleur total sur une semaine, du lundi au dimanche, cours inclus.',
     'unit': 'minutes', 'targets': (1500, 2400, 3300, 3900, 4800)},
    {'id': 'work_month', 'award_prefix': 'work_month_v3', 'title': 'La force de la constance',
     'description': 'Ton meilleur total sur un mois du calendrier, cours inclus.',
     'unit': 'minutes', 'targets': (6000, 9600, 13200, 15600, 19200)},
    {'id': 'sleep_streak', 'title': 'Des nuits qui rechargent',
     'description': 'Ta meilleure série de nuits avec au moins 8 h de sommeil.',
     'unit': 'days', 'targets': (3, 7, 14, 21, 30)},
    {'id': 'sport_total', 'title': 'Le plaisir de bouger',
     'description': 'Tout ton temps de sport, séances personnelles et EPS réunies.',
     'unit': 'minutes', 'targets': (60, 300, 900, 1800, 3600)},
    {'id': 'sport_streak', 'title': 'Un rendez-vous avec toi',
     'description': 'Ta meilleure série de semaines avec au moins 1 h de sport, du lundi au dimanche.',
     'unit': 'weeks', 'targets': (2, 4, 8, 12, 24)},
)
QUESTS = (
    {'id': 'work_week_v2', 'title': 'Ton cap de la semaine',
     'description': 'Cumule 25 h de cours ou de travail personnel cette semaine.',
     'period': 'week', 'metric': 'work', 'target': 1500, 'unit': 'minutes', 'points': 100},
    {'id': 'study_days_v2', 'title': 'Cinq rendez-vous',
     'description': 'Consacre au moins 2 h aux cours ou au travail personnel sur cinq jours de la semaine.',
     'period': 'week', 'metric': 'study_days', 'target': 5, 'unit': 'days', 'points': 120},
    {'id': 'sleep_nights', 'title': 'Des nuits régulières',
     'description': 'Enregistre au moins 8 h de sommeil sur trois nuits cette semaine.',
     'period': 'week', 'metric': 'sleep_nights', 'target': 3, 'unit': 'days', 'points': 120},
    {'id': 'study_month_v2', 'title': 'Un mois qui avance',
     'description': 'Consacre au moins 2 h aux cours ou au travail personnel sur vingt jours de ce mois.',
     'period': 'month', 'metric': 'study_days', 'target': 20, 'unit': 'days', 'points': 300},
    {'id': 'sport_week', 'title': 'Une heure pour bouger',
     'description': 'Cumule 1 h de sport ou d’EPS cette semaine, à ton rythme.',
     'period': 'week', 'metric': 'sport', 'target': 60, 'unit': 'minutes', 'points': 120},
    {'id': 'sport_days', 'title': 'Deux pauses actives',
     'description': 'Fais au moins 20 min de sport ou d’EPS sur deux jours de la semaine.',
     'period': 'week', 'metric': 'sport_days', 'target': 2, 'unit': 'days', 'points': 120},
)
_LEGACY_QUESTS = {quest['id']: quest for quest in LEGACY_QUESTS}
_QUESTS = {quest['id']: quest for quest in (*LEGACY_QUESTS, *QUESTS)}
_BADGES = {
    f"{family.get('award_prefix', family['id'])}:{index + 1}": (family, tier, target)
    for family in FAMILIES
    for index, (tier, target) in enumerate(zip(TIERS, family['targets']))
}
_LEGACY_BADGES = {
    f"{family.get('award_prefix', family['id'])}:{index + 1}": (family, tier, target)
    for family in LEGACY_FAMILIES
    for index, (tier, target) in enumerate(zip(TIERS, family['targets']))
}
_ALL_BADGES = _LEGACY_BADGES | _BADGES
_STAMP = re.compile(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?\Z')
_MONTHS = ('janvier', 'février', 'mars', 'avril', 'mai', 'juin',
           'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre')


def _quest_identity(value):
    if not isinstance(value, str):
        raise ValueError(tr('L’identifiant du succès est invalide.'))
    parts = value.split(':')
    if len(parts) != 3 or parts[0] != 'quest' or parts[1] not in _QUESTS:
        raise ValueError(tr('Le succès ou la quête est inconnu.'))
    quest = _QUESTS[parts[1]]
    try:
        first = date.fromisoformat(parts[2])
    except (TypeError, ValueError):
        raise ValueError(tr('La période de la quête est invalide.')) from None
    if (first.isoformat() != parts[2] or not date(1999, 12, 27) <= first <= date(2200, 12, 31)
            or (quest['period'] == 'week' and first.weekday() != 0)
            or (quest['period'] == 'month' and first.day != 1)):
        raise ValueError(tr('La période de la quête est invalide.'))
    return quest, first


def validate_state(value):
    """Return a detached canonical ledger, rejecting unknown IDs and fields."""
    if (not isinstance(value, dict) or set(value) != {'version', 'awards'}
            or type(value['version']) is not int or value['version'] != 1
            or not isinstance(value['awards'], dict) or len(value['awards']) > MAX_AWARDS):
        raise ValueError(tr('Le registre des succès est invalide.'))
    awards = {}
    for identity, award in value['awards'].items():
        if not isinstance(identity, str):
            raise ValueError(tr('L’identifiant du succès est invalide.'))
        period = None
        if identity not in _ALL_BADGES:
            _, period = _quest_identity(identity)
        if not isinstance(award, dict) or set(award) != {'earned_at'}:
            raise ValueError(tr('La récompense doit contenir uniquement sa date d’obtention.'))
        stamp = award['earned_at']
        if not isinstance(stamp, str) or not _STAMP.fullmatch(stamp):
            raise ValueError(tr('La date d’obtention du succès est invalide.'))
        try:
            earned = datetime.fromisoformat(stamp)
        except ValueError:
            raise ValueError(tr('La date d’obtention du succès est invalide.')) from None
        if not 2000 <= earned.year <= 2200 or (period is not None and earned.date() < period):
            raise ValueError(tr('La date d’obtention du succès est incohérente.'))
        awards[identity] = {'earned_at': earned.isoformat(timespec='seconds')}
    return {'version': 1, 'awards': awards}


def _clock(db, now):
    result = now if now is not None else getattr(db, '_time_now', datetime.now)()
    if (not isinstance(result, datetime) or result.tzinfo is not None
            or not 2000 <= result.year <= 2200):
        raise ValueError(tr('Choisis une date et une heure locales valides entre 2000 et 2200.'))
    return result


def _period(day, kind):
    return day - timedelta(days=day.weekday()) if kind == 'week' else day.replace(day=1)


def _merge(intervals):
    """An imported overlapping activity must never award the same minute twice."""
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _daily(intervals, *, sleep=False):
    totals = defaultdict(int)
    for start, end in _merge(intervals):
        cursor = start
        while cursor < end:
            if sleep:
                # [previous noon, wake-day noon): an ordinary 23:00–07:00
                # night belongs entirely to the morning when it finishes.
                day = cursor.date() + timedelta(days=cursor.hour >= 12)
                boundary = datetime.combine(day, time(12))
            else:
                day = cursor.date()
                boundary = datetime.combine(day + timedelta(days=1), time())
            limit = min(end, boundary)
            totals[day] += int((limit - cursor).total_seconds() // 60)
            cursor = limit
    return dict(totals)


def _metrics(db, now):
    study = set(db.study_categories()) | {'ds', 'cpge', 'permanence'}
    intervals = {'work': [], 'sleep': [], 'sport': []}
    for entry in db.list_time_entries():
        if entry.get('deleted') or entry.get('status') != 'completed':
            continue
        category = entry.get('category')
        metric = ('sport' if category in {'sport', 'eps'} else 'sleep' if category == 'sommeil'
                  else 'work' if category in study else None)
        if metric is None:
            continue
        start, end = local_stamp(entry['start_at']), local_stamp(entry['end_at'])
        if (end <= start or end > now or end - start > timedelta(days=7)
                or start.year < 2000 or end.year > 2200):
            continue
        intervals[metric].append((start, end))
    work = _daily(intervals['work'])
    sleep = _daily(intervals['sleep'], sleep=True)
    sport = _daily(intervals['sport'])
    periods = {'week': {}, 'month': {}}
    for kind, buckets in periods.items():
        for day in work.keys() | sleep.keys() | sport.keys():
            # An unfinished noon-to-noon window can already reach its target;
            # a window labelled tomorrow must wait until that calendar day.
            if day > now.date():
                continue
            first = _period(day, kind)
            bucket = buckets.setdefault(first, {'work': 0, 'study_days': 0, 'sleep_nights': 0,
                                                'sport': 0, 'sport_days': 0})
            bucket['work'] += work.get(day, 0)
            bucket['study_days'] += work.get(day, 0) >= 120
            bucket['sleep_nights'] += sleep.get(day, 0) >= 480
            bucket['sport'] += sport.get(day, 0)
            bucket['sport_days'] += sport.get(day, 0) >= 20
    values = {
        'work_total': sum(work.values()),
        'work_week': max((bucket['work'] for bucket in periods['week'].values()), default=0),
        'work_month': max((bucket['work'] for bucket in periods['month'].values()), default=0),
        'sleep_streak': _best_streak((day for day, minutes in sleep.items()
                                     if minutes >= 480 and day <= now.date()), days=1),
        'sport_total': sum(sport.values()),
        'sport_streak': _best_streak((first for first, bucket in periods['week'].items()
                                     if bucket['sport'] >= 60), days=7),
    }
    return values, periods


def _best_streak(periods, *, days):
    best = streak = 0
    previous = None
    for first in sorted(periods):
        streak = streak + 1 if previous is not None and first == previous + timedelta(days=days) else 1
        previous = first
        best = max(best, streak)
    return best


def _award(identity, earned_at):
    if identity in _ALL_BADGES:
        family, tier, target = _ALL_BADGES[identity]
        return {'id': identity, 'title': family['title'], 'tier': tier['name'],
                'earned_at': earned_at, 'points': tier['points'],
                'target': target, 'unit': family['unit'], 'family_id': family['id'],
                'legacy': identity in _LEGACY_BADGES}
    quest, first = _quest_identity(identity)
    return {'id': identity, 'title': quest['title'], 'tier': tr('Quête'),
            'earned_at': earned_at, 'points': quest['points'], 'period_label': _period_label(quest, first),
            'target': quest['target'], 'unit': quest['unit'], 'legacy': quest['id'] in _LEGACY_QUESTS}


def _period_label(quest, first):
    if quest['period'] == 'week':
        end = first + timedelta(days=6)
        return tr('Du {start} au {end}',
                  start=format_date(first) if language() == 'en' else first.strftime('%d/%m'),
                  end=format_date(end))
    return f'{tr(_MONTHS[first.month - 1]).capitalize()} {first.year}'


def _localized_report(value):
    """Localize display fields only; catalog IDs and saved awards stay stable."""
    if isinstance(value, list):
        return [_localized_report(item) for item in value]
    if isinstance(value, dict):
        return {key: tr(item) if key in {'title', 'description', 'name', 'tier', 'level_label'} and isinstance(item, str)
                else _localized_report(item) for key, item in value.items()}
    return value


def _report(state, values, periods, now, new_ids=()):
    awards = state['awards']
    families = []
    for family in FAMILIES:
        tiers = []
        for index, (tier, target) in enumerate(zip(TIERS, family['targets'])):
            identity = f"{family.get('award_prefix', family['id'])}:{index + 1}"
            tiers.append({'id': identity, **tier, 'target': target,
                          'earned_at': awards.get(identity, {}).get('earned_at')})
        families.append({key: value for key, value in family.items() if key not in {'targets', 'award_prefix'}} | {
            'current': values[family['id']], 'tiers': tiers,
            'earned_count': sum(tier['earned_at'] is not None for tier in tiers)})
    quests = []
    for quest in QUESTS:
        first = _period(now.date(), quest['period'])
        identity = f"quest:{quest['id']}:{first.isoformat()}"
        current = periods[quest['period']].get(first, {}).get(quest['metric'], 0)
        quests.append({key: value for key, value in quest.items() if key not in {'metric', 'period'}} | {
            'id': identity, 'current': current,
            'earned_at': awards.get(identity, {}).get('earned_at'),
            'period_label': _period_label(quest, first)})
    all_awards = [_award(identity, award['earned_at']) for identity, award in awards.items()]
    all_awards.sort(key=lambda award: (award['earned_at'], award['id']), reverse=True)
    legacy = [award for award in all_awards if award['legacy']]
    points = sum(award['points'] for award in all_awards)
    level = 1 + points // 500
    labels = (tr('Premiers pas'), tr('Sur ta lancée'), tr('Un rythme à toi'), tr('Belle régularité'), tr('Cap sur la suite'))
    return _localized_report({
        'families': families, 'quests': quests, 'points': points, 'level': level,
        'level_label': labels[min(len(labels) - 1, (level - 1) // 3)],
        'level_floor': (level - 1) * 500, 'next_level_points': level * 500,
        'earned_count': sum(identity in _BADGES for identity in awards),
        'total_count': len(_BADGES),
        'quests_completed': sum(award['id'].startswith('quest:') and not award['legacy'] for award in all_awards),
        'legacy_count': len(legacy), 'legacy_points': sum(award['points'] for award in legacy),
        'legacy_awards': legacy[:100], 'recent_awards': all_awards[:20],
        'new_awards': [_award(identity, awards[identity]['earned_at']) for identity in new_ids],
        'ledger_full': len(awards) >= MAX_AWARDS,
    })


def snapshot(db, now=None):
    """Show current progress and previously earned rewards without changing data."""
    now = _clock(db, now)
    with getattr(db, '_lock', nullcontext()):
        state = validate_state(db.get_setting(SETTING, {'version': 1, 'awards': {}}))
        values, periods = _metrics(db, now)
    return _report(state, values, periods, now)


def reconcile(db, now=None):
    """Award each reached tier and each qualified calendar quest exactly once."""
    # DesktopStore uses a reentrant lock. Keep reading the ledger, examining
    # the journal and writing new awards atomic with background backups.
    with getattr(db, '_lock', nullcontext()):
        return _reconcile_locked(db, _clock(db, now))


def _reconcile_locked(db, now):
    state = validate_state(db.get_setting(SETTING, {'version': 1, 'awards': {}}))
    values, periods = _metrics(db, now)
    qualified = [identity for identity, (family, _, target) in _BADGES.items()
                 if values[family['id']] >= target]
    for quest in QUESTS:
        for first, bucket in sorted(periods[quest['period']].items()):
            if bucket[quest['metric']] >= quest['target']:
                qualified.append(f"quest:{quest['id']}:{first.isoformat()}")
    new_ids = []
    for identity in qualified:
        if identity not in state['awards'] and len(state['awards']) < MAX_AWARDS:
            state['awards'][identity] = {'earned_at': now.isoformat(timespec='seconds')}
            new_ids.append(identity)
    if new_ids:
        db.set_setting(SETTING, state)
    return _report(state, values, periods, now, new_ids)
