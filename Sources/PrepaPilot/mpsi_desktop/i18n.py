"""Small explicit FR/EN catalog: stable data identifiers are never translated.

French source strings are message identifiers. Format values are inserted after
translation, so personal names, subjects, filenames and notes remain untouched.
This module has no mandatory Qt dependency and is also used by storage errors.
"""
from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
import importlib
import os
import sys
import sqlite3
import json
from pathlib import Path

LANGUAGES = {"fr": "Français", "en": "English"}
_language = "fr"
_CATALOGS = ("translations_shell", "translations_study", "translations_schedule",
             "translations_progress", "translations_cloud", "translations_updates",
             "translations_experience", "translations_engagement", "translations_quick_actions",
             "translations_search", "translations_focus_bar", "translations_help", "translations_launch",
             "translations_organization")


def language():
    return _language


def normalize_language(value):
    return value if value in LANGUAGES else "fr"


def load_saved_language(data_dir):
    """Read one preference without creating a database or taking its app lock."""
    database = Path(data_dir).resolve() / 'mpsi.sqlite3'
    if not database.is_file():
        return 'fr'
    try:
        connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=1)
        try:
            row = connection.execute("SELECT value FROM settings WHERE key = 'desktop_language'").fetchone()
            value = json.loads(row[0]) if row else None
            return normalize_language(value)
        finally:
            connection.close()
    except (sqlite3.Error, ValueError, TypeError):
        return 'fr'


@lru_cache(maxsize=1)
def english_catalog():
    result = {}
    for name in _CATALOGS:
        try:
            module = importlib.import_module("." + name, __package__)
        except ModuleNotFoundError as exc:
            if exc.name != __package__ + "." + name:
                raise
            continue
        for source, target in module.EN.items():
            if source in result and result[source] != target:
                raise ValueError(f"Conflicting English translation for {source!r}")
            result[source] = target
    return result


def set_language(value):
    global _language
    if value not in LANGUAGES:
        raise ValueError("Unsupported language")
    _language = value
    # The splash process inherits this before it imports application code.
    os.environ["PREPAPILOT_LANGUAGE"] = value
    if "PySide6.QtCore" in sys.modules:
        from PySide6.QtCore import QLocale
        QLocale.setDefault(QLocale("en_GB" if value == "en" else "fr_FR"))
    return value


def tr(source, **values):
    message = english_catalog().get(source, source) if _language == "en" else source
    return message.format(**values) if values else message


_DAYS = {
    "fr": ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"),
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
}
_MONTHS = {
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
}


def format_date(value, style="short"):
    if hasattr(value, "toPython"):
        value = value.toPython()
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    if style == "iso":
        return value.strftime("%Y-%m-%d")
    if style == "long":
        return f"{_DAYS[_language][value.weekday()]}, {value.day} {_MONTHS[_language][value.month - 1]} {value.year}" if _language == "en" else f"{_DAYS[_language][value.weekday()]} {value.day} {_MONTHS[_language][value.month - 1]} {value.year}"
    return f"{value.day} {_MONTHS['en'][value.month - 1][:3]} {value.year}" if _language == "en" else value.strftime("%d/%m/%Y")


def format_datetime(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return format_date(value) + (" at " if _language == "en" else " à ") + value.strftime("%H:%M")


def format_number(value, decimals=None):
    text = format(value, f".{decimals}f") if decimals is not None else format(value, "g")
    return text.replace(".", ",") if _language == "fr" else text


def qt_locale():
    from PySide6.QtCore import QLocale
    return QLocale("en_GB" if _language == "en" else "fr_FR")


# Helpers are launched in another process, with this explicit inherited choice.
if os.environ.get("PREPAPILOT_LANGUAGE") in LANGUAGES:
    _language = os.environ["PREPAPILOT_LANGUAGE"]
