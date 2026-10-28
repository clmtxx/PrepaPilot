"""Grade normalization, descriptive statistics and locally generated charts."""

from __future__ import annotations
from mpsi_desktop.i18n import tr, format_number

from collections import defaultdict
from datetime import date
from io import BytesIO
import math
import re
from statistics import median
from typing import Any, Iterable
import unicodedata


SUBJECT_LABELS = {"maths": "Mathématiques", "physique": "Physique", "anglais": "Anglais"}
KIND_LABELS = {
    "cours": "Contrôle", "ds": "Examen écrit", "colle": "Oral",
    "projet": "Projet", "tp": "Travaux pratiques", "autre": "Autre",
}


def _plain(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(tr('Le nom doit être du texte.'))
    value = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())


def normalize_subject(subject: str) -> str:
    aliases = {
        "maths": "maths", "math": "maths", "mathematiques": "maths",
        "mathematique": "maths", "physique": "physique", "phy": "physique",
        "phys": "physique", "anglais": "anglais", "english": "anglais", "ang": "anglais",
    }
    if not isinstance(subject, str):
        raise ValueError(tr('L’identifiant de la matière doit être du texte.'))
    if any(ord(char) < 32 or ord(char) == 127 for char in subject):
        raise ValueError(tr('L’identifiant de la matière est invalide.'))
    alias = aliases.get(_plain(subject))
    if alias:
        return alias
    identity = subject.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", identity):
        raise ValueError(tr('L’identifiant de la matière est invalide.'))
    return identity


def normalize_kind(kind: str) -> str:
    aliases = {
        "cours": "cours", "eval": "cours", "evaluation": "cours", "evaluations": "cours",
        "evaluation de cours": "cours", "evaluations de cours": "cours",
        "controle": "cours", "controles": "cours",
        "colle": "colle", "colles": "colle", "kholle": "colle", "kholles": "colle",
        "oral": "colle", "oraux": "colle",
        "ds": "ds", "devoir surveille": "ds", "devoirs surveilles": "ds",
        "examen ecrit": "ds", "examens ecrits": "ds",
        "projet": "projet", "projets": "projet", "tp": "tp", "travaux pratiques": "tp",
        "autre": "autre",
    }
    if (not isinstance(kind, str) or not 1 <= len(kind.strip()) <= 60
            or any(ord(char) < 32 or ord(char) == 127 for char in kind)):
        raise ValueError(tr('Le type d’évaluation doit contenir entre 1 et 60 caractères, sur une seule ligne.'))
    return aliases.get(_plain(kind), kind.strip())


def _score(grade: dict[str, Any]) -> float:
    # Always compute from the original scale to avoid accumulating rounding error.
    return float(grade["score"]) / float(grade["scale"]) * 20.0


def _weighted(grades: list[dict[str, Any]]) -> float:
    # Scaling weights first also handles very large, individually finite inputs.
    largest = max(float(grade.get("coefficient", 1)) for grade in grades)
    weights = [float(grade.get("coefficient", 1)) / largest for grade in grades]
    return math.fsum(_score(grade) * weight for grade, weight in zip(grades, weights)) / math.fsum(weights)


def _aggregate(grades: list[dict[str, Any]]) -> dict[str, Any]:
    values = [_score(grade) for grade in grades]
    if not values:
        return {
            "count": 0, "mean": None, "weighted_mean": None, "median": None,
            "min": None, "max": None, "trend": None, "last_score": None,
        }
    ordered = sorted(grades, key=lambda grade: (grade["graded_on"], grade.get("id", 0)))
    trend = None
    if len(ordered) >= 6:
        last = ordered[-3:]
        previous = ordered[-6:-3]
        trend = _weighted(last) - _weighted(previous)
    return {
        "count": len(values),
        "mean": math.fsum(values) / len(values),
        "weighted_mean": _weighted(grades),
        "median": median(values), "min": min(values), "max": max(values),
        "trend": trend, "last_score": _score(ordered[-1]),
    }


def stats(grades: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return statistics on /20 scores; trend compares the last two sets of three.

    The overall weighted mean is informative: it does not assume any official
    weighting between course evaluations, oral exams and written exams.
    """
    rows = list(grades)
    result = _aggregate(rows)
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for grade in rows:
        groups[grade["kind"]].append(grade)
    ordered_kinds = [kind for kind in KIND_LABELS if kind in groups]
    ordered_kinds.extend(sorted(set(groups) - set(KIND_LABELS), key=str.casefold))
    result["by_kind"] = {kind: _aggregate(groups[kind]) for kind in ordered_kinds}
    return result


def format_stats(grades: Iterable[dict[str, Any]], subject: str, subject_label: str | None = None) -> str:
    subject = normalize_subject(subject)
    rows = [row for row in grades if row["subject"] == subject]
    result = stats(rows)
    name = subject_label or (tr(SUBJECT_LABELS[subject]) if subject in SUBJECT_LABELS else subject)
    if not rows:
        return tr('{v0} : aucune note enregistrée.', v0=name)
    def num(value: float) -> str:
        return format_number(value, 2)
    lines = [
        tr('{name} — {count} note(s)', name=name, count=result['count']),
        tr('Moyenne indicative pondérée : {v0}/20', v0=num(result['weighted_mean'])),
        tr('Médiane : {v0}/20', v0=num(result['median'])),
        tr('Minimum / maximum : {v0} / {v1}', v0=num(result['min']), v1=num(result['max'])),
        tr('Dernière note : {v0}/20', v0=num(result['last_score'])),
    ]
    if result["trend"] is not None:
        sign = "+" if result["trend"] >= 0 else ""
        lines.append(tr('Évolution : {v0}{v1} point(s) (3 dernières / 3 précédentes)', v0=sign, v1=num(result['trend'])))
    else:
        lines.append(tr('Évolution calculée à partir de 6 notes.'))
    for kind, group in result["by_kind"].items():
        kind_label = tr(KIND_LABELS[kind]) if kind in KIND_LABELS else kind
        lines.append(tr('• {kind} : {average}/20 ({count} note(s))', kind=kind_label, average=num(group['weighted_mean']), count=group['count']))
    lines.append(tr("Toutes les notes sont ramenées sur 20. Coefficient 1 par défaut ; cette moyenne n'est pas une moyenne officielle."))
    return "\n".join(lines)


def plot_grades(grades: Iterable[dict[str, Any]], subject: str, subject_label: str | None = None) -> BytesIO:
    """Render a PNG in memory using a headless backend, with a line per category."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter, date2num
    from matplotlib.figure import Figure
    from matplotlib.ticker import FixedLocator

    subject = normalize_subject(subject)
    rows = sorted((row for row in grades if row["subject"] == subject), key=lambda row: (row["graded_on"], row.get("id", 0)))
    if not rows:
        raise ValueError(tr('Aucune note à représenter pour cette matière.'))
    figure = Figure(figsize=(10, 5.4), dpi=150, layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    colors = {"cours": "#2563eb", "colle": "#0f766e", "ds": "#b45309"}
    markers = {"cours": "o", "colle": "s", "ds": "D"}
    palette = ("#2563eb", "#0f766e", "#b45309", "#7c3aed", "#db2777", "#475569")
    for position, kind in enumerate(stats(rows)["by_kind"]):
        group = [row for row in rows if row["kind"] == kind]
        if group:
            axes.plot([date.fromisoformat(row["graded_on"]) for row in group], [_score(row) for row in group],
                      label=tr(KIND_LABELS[kind]) if kind in KIND_LABELS else kind, color=colors.get(kind, palette[position % len(palette)]),
                      marker=markers.get(kind, "o"), markersize=5, linewidth=1.7)
    locator = AutoDateLocator(minticks=3, maxticks=9)
    axes.xaxis.set_major_locator(locator)
    axes.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    axes.set_ylim(-0.5, 20.5)
    axes.set_yticks(range(0, 21, 2))
    axes.set_ylabel(tr('Note sur 20'))
    axes.set_xlabel(tr("Date de l'évaluation"))
    title = subject_label or (tr(SUBJECT_LABELS[subject]) if subject in SUBJECT_LABELS else subject)
    axes.set_title(tr('{v0} · évolution des notes', v0=title), loc="left", fontsize=16, pad=16)
    axes.grid(axis="y", color="#e2e8f0")
    axes.spines[["top", "right"]].set_visible(False)
    axes.legend(loc="best", frameon=False)
    if len({row["graded_on"] for row in rows}) == 1:
        from datetime import timedelta
        center = date.fromisoformat(rows[0]["graded_on"])
        lower = center - timedelta(days=min(7, (center - date.min).days))
        upper = center + timedelta(days=min(7, (date.max - center).days))
        axes.set_xlim(lower, upper)
    # Automatic margins and date ticks can otherwise leave Python's supported
    # calendar for valid imported notes near years 1 or 9999.
    lower, upper = axes.get_xlim()
    first, last = date2num(date.min), date2num(date.max)
    if lower < first or upper > last:
        lower, upper = max(first, lower), min(last, upper)
        axes.set_xlim(lower, upper)
        locator = FixedLocator([lower + (upper - lower) * index / 6 for index in range(7)])
        axes.xaxis.set_major_locator(locator)
        axes.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    buffer = BytesIO()
    buffer.name = f"notes-{subject}.png"
    figure.savefig(buffer, format="png", facecolor="white")
    buffer.seek(0)
    figure.clear()
    return buffer
