"""Read-only progress reports from the activity journal and personal targets.

All ranges are half-open local calendar intervals. Planned activities, future
completions and deleted rows never contribute to a report. Reading a report
does not create timetable entries or persist calculated values.
"""
from __future__ import annotations
from .i18n import tr

from datetime import date, datetime, time, timedelta
import math
import re

from .time_store import local_stamp


METRICS = ('work', 'sleep', 'sport', 'rest')
TARGETS_SETTING = 'desktop_progression_targets'
ACKNOWLEDGEMENTS_SETTING = 'desktop_progression_acknowledgements'
MAX_ACKNOWLEDGEMENTS = 5000
_ACK_METRICS = {*METRICS, 'recovery'}


def _empty_totals():
    return {metric: 0 for metric in METRICS}


def validate_targets(data):
    """Validate minutes per week; zero disables that personal target."""
    if not isinstance(data, dict) or set(data) != set(METRICS):
        raise ValueError(tr('Les objectifs doivent préciser travail, sommeil, sport et détente.'))
    if any(type(value) is not int or not 0 <= value <= 7 * 24 * 60 for value in data.values()):
        raise ValueError(tr('Chaque objectif doit être un nombre entier de minutes entre 0 et 10 080 par semaine.'))
    if sum(data.values()) > 7 * 24 * 60:
        raise ValueError(tr('L’ensemble de tes objectifs dépasse les 168 heures disponibles dans une semaine.'))
    return {metric: data[metric] for metric in METRICS}


def _validate_period_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'(week|month|quarter):\d{4}-\d{2}-\d{2}', value):
        raise ValueError(tr('La période du signal de progression est invalide.'))
    kind, raw = value.split(':')
    try:
        start = date.fromisoformat(raw)
    except ValueError:
        raise ValueError(tr('La date du signal de progression est invalide.')) from None
    # A valid January 2000 anchor can start its week/three-month window in
    # late 1999. Accept exactly the possible derived lower bounds as well.
    earliest = {'week': date(1999, 12, 27), 'month': date(2000, 1, 1), 'quarter': date(1999, 11, 1)}[kind]
    if not earliest <= start <= date(2200, 12, 31) or (kind == 'week' and start.weekday() != 0) or (kind != 'week' and start.day != 1):
        raise ValueError(tr('La période du signal de progression est invalide.'))
    return value


def _acknowledgement_key(period_key, metric):
    _validate_period_key(period_key)
    if metric not in _ACK_METRICS:
        raise ValueError(tr('La catégorie du signal de progression est invalide.'))
    return f'{period_key}|{metric}'


def validate_acknowledgements(data):
    if not isinstance(data, list) or len(data) > MAX_ACKNOWLEDGEMENTS:
        raise ValueError(tr('La liste des signaux de progression acceptés est invalide.'))
    seen = set()
    for value in data:
        if not isinstance(value, str) or value.count('|') != 1:
            raise ValueError(tr('Un signal de progression accepté est invalide.'))
        period, metric = value.split('|')
        _acknowledgement_key(period, metric)
        if value in seen:
            raise ValueError(tr('Un signal de progression accepté est présent plusieurs fois.'))
        seen.add(value)
    return list(data)


def load_targets(db):
    return validate_targets(db.get_setting(TARGETS_SETTING, _empty_totals()))


def save_targets(db, targets):
    clean = validate_targets(targets)
    db.set_setting(TARGETS_SETTING, clean)
    return clean


def acknowledge(db, period_key, metric):
    key = _acknowledgement_key(period_key, metric)
    values = validate_acknowledgements(db.get_setting(ACKNOWLEDGEMENTS_SETTING, []))
    if key not in values:
        values.append(key)
        db.set_setting(ACKNOWLEDGEMENTS_SETTING, values[-MAX_ACKNOWLEDGEMENTS:])


def clear_acknowledgement(db, period_key, metric):
    key = _acknowledgement_key(period_key, metric)
    values = validate_acknowledgements(db.get_setting(ACKNOWLEDGEMENTS_SETTING, []))
    if key in values:
        db.set_setting(ACKNOWLEDGEMENTS_SETTING, [value for value in values if value != key])


def format_duration(minutes):
    """Round up to a whole minute without showing fractional durations."""
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or minutes < 0:
        raise ValueError(tr('La durée doit être un nombre positif ou nul.'))
    hours, remaining = divmod(math.ceil(minutes), 60)
    return f'{hours} h {remaining:02d}' if hours else f'{remaining} min'


def _month_shift(value, count):
    ordinal = value.year * 12 + value.month - 1 + count
    year, month = divmod(ordinal, 12)
    return date(year, month + 1, 1)


def _bounds(kind, anchor):
    if kind == 'week':
        start = anchor - timedelta(days=anchor.weekday())
        end = start + timedelta(days=7)
        previous = start - timedelta(days=7)
    elif kind in {'month', 'quarter'}:
        count = 1 if kind == 'month' else 3
        start = _month_shift(anchor.replace(day=1), 1 - count)
        end = _month_shift(start, count)
        previous = _month_shift(start, -count)
    else:
        raise ValueError(tr('Choisis une semaine, un mois ou trois mois.'))
    return start, end, previous


def _clock(db, now):
    result = now if now is not None else db._time_now()
    if not isinstance(result, datetime) or result.tzinfo is not None:
        raise ValueError(tr('Choisis une date et une heure locales valides.'))
    return result


def _midnight(value):
    return datetime.combine(value, time())


def _empty_aggregate():
    return dict(totals=_empty_totals(), work_sources={'courses': 0, 'personal': 0},
                work_by_subject=[], entries_count=0, has_data=False, recorded_minutes=0)


def _read_entries(db, start, end, now):
    """Parse and classify each entry once, before distributing it to periods."""
    labels = db.category_labels(include_archived=True)
    study = db.study_categories() | {'ds', 'cpge', 'permanence'}
    result = []
    for entry in db.list_time_entries(start.isoformat(), end.isoformat()):
        if entry.get('deleted') or entry['status'] != 'completed':
            continue
        entry_start, entry_end = local_stamp(entry['start_at']), local_stamp(entry['end_at'])
        if entry_end > now or entry_end <= start or entry_start >= end:
            continue
        category = entry['category']
        if category in {'sport', 'eps'}:
            metric = 'sport'
        elif category == 'sommeil':
            metric = 'sleep'
        elif category == 'detente':
            metric = 'rest'
        elif category in study:
            metric = 'work'
        else:
            metric = None
        source = 'courses' if entry['source'] == 'timetable' else 'personal'
        result.append((entry_start, entry_end, category, metric, source))
    return labels, result


def _accumulate(result, by_subject, entry, start, end):
    entry_start, entry_end, category, metric, source = entry
    minutes = int((min(end, entry_end) - max(start, entry_start)).total_seconds() // 60)
    if minutes <= 0:
        return
    result['entries_count'] += 1
    result['recorded_minutes'] += minutes
    if metric is not None:
        result['totals'][metric] += minutes
        result['has_data'] = True
    if metric == 'work':
        by_subject[category] = by_subject.get(category, 0) + minutes
        result['work_sources'][source] += minutes


def _aggregate(entries, labels, start, end):
    result = _empty_aggregate()
    if end <= start:
        return result
    by_subject = {}
    for entry in entries:
        _accumulate(result, by_subject, entry, start, end)
    result['work_by_subject'] = [dict(category=key, label=labels.get(key, key), minutes=value)
                                 for key, value in sorted(by_subject.items(), key=lambda item: (-item[1], labels.get(item[0], item[0])))]
    return result


def _scores(totals, targets, days, has_data):
    result = {'work': None, 'sleep': None, 'recovery': None, 'global': None}
    if not has_data or days <= 0:
        return result
    axes = {key: min(100.0, 100 * totals[key] / (target * days / 7))
            for key, target in targets.items() if target > 0}
    result['work'] = axes.get('work')
    result['sleep'] = axes.get('sleep')
    recovery = [axes[key] for key in ('sport', 'rest') if key in axes]
    result['recovery'] = sum(recovery) / len(recovery) if recovery else None
    components = [value for value in result.values() if value is not None]
    result['global'] = sum(components) / len(components) if components else None
    return result


def build_report(db, kind='week', anchor=None, now=None):
    now = _clock(db, now)
    anchor = now.date() if anchor is None else anchor
    if type(anchor) is not date or not 2000 <= anchor.year <= 2200:
        raise ValueError(tr('Choisis une date entre 2000 et 2200.'))
    first, limit, previous = _bounds(kind, anchor)
    start, full_end, previous_start = map(_midnight, (first, limit, previous))
    end = max(start, min(full_end, now))
    days = (end - start).total_seconds() / 86400
    labels, entries = _read_entries(db, previous_start, end, now)
    totals = _aggregate(entries, labels, start, end)
    targets = load_targets(db)
    key = f'{kind}:{first.isoformat()}'
    acknowledgements = validate_acknowledgements(db.get_setting(ACKNOWLEDGEMENTS_SETTING, []))
    duration = min(end - start, start - previous_start)
    current_end = start + duration
    previous_end = previous_start + duration
    current = totals if current_end == end else _aggregate(entries, labels, start, current_end)
    prior = _aggregate(entries, labels, previous_start, previous_end)
    comparable = current['has_data'] and prior['has_data']
    deltas = {metric: current['totals'][metric] - prior['totals'][metric] for metric in METRICS}
    percentages = {metric: (100 * deltas[metric] / prior['totals'][metric]
                            if comparable and prior['totals'][metric] else None) for metric in METRICS}
    comparison = dict(current_start=start, current_end=current_end,
                      previous_start=previous_start, previous_end=previous_end,
                      duration_days=duration.total_seconds() / 86400,
                      common_duration=duration,
                      current_totals=current['totals'], previous_totals=prior['totals'],
                      current_has_data=current['has_data'], previous_has_data=prior['has_data'],
                      has_data=comparable, deltas=deltas, percentages=percentages)
    return dict(kind=kind, anchor=anchor, period_key=key, period_start=first, period_end=limit,
                start=start, end=end, elapsed_days=days, targets=targets,
                scores=_scores(totals['totals'], targets, days, totals['has_data']),
                acknowledged=[metric for metric in (*METRICS, 'recovery') if f'{key}|{metric}' in acknowledgements],
                comparison=comparison, **totals)


def annual_history(db, year, now=None):
    """September–August average recorded minutes per elapsed calendar day."""
    if type(year) is not int or not 2000 <= year <= 2200:
        raise ValueError(tr('Choisis une année scolaire valide.'))
    now = _clock(db, now)
    first = date(year, 9, 1)
    stop = date(year + 1, 9, 1)
    _, entries = _read_entries(db, _midnight(first), _midnight(stop), now)
    buckets = []
    for offset in range(12):
        start = _midnight(_month_shift(first, offset))
        end = max(start, min(_midnight(_month_shift(first, offset + 1)), now))
        buckets.append((start, end, _empty_aggregate(), {}))
    # An ordinary entry touches one bucket; overnight entries may touch two.
    # Long imported entries still contribute to every month they overlap.
    for entry in entries:
        entry_start, entry_end = entry[:2]
        lower = max(0, (entry_start.year - first.year) * 12 + entry_start.month - first.month)
        upper = min(11, (entry_end.year - first.year) * 12 + entry_end.month - first.month)
        for offset in range(lower, upper + 1):
            start, end, totals, subjects = buckets[offset]
            if end > start:
                _accumulate(totals, subjects, entry, start, end)
    result = []
    for start, end, totals, _ in buckets:
        days = (end - start).total_seconds() / 86400
        averages = ({metric: minutes / days for metric, minutes in totals['totals'].items()}
                    if days and totals['has_data'] else None)
        result.append(dict(month=start.date(), days=days, totals=totals['totals'], averages=averages,
                           has_data=totals['has_data'], future=start >= now))
    return result
