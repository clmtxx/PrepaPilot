"""Study profile vocabulary shared by setup, settings and timetable views."""
from __future__ import annotations

from .i18n import tr

def _plain_text(value, maximum, message, *, required=False):
    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(message)
    value = value.strip()
    if len(value) > maximum or (required and not value):
        raise ValueError(message)
    return value


def validate_program(value):
    return _plain_text(value, 80, tr('Le nom du parcours doit contenir au plus 80 caractères.'))


def validate_schedule_labels(value):
    if not isinstance(value, dict) or set(value) != {"S1", "S2"}:
        raise ValueError(tr('Donne un nom à chacun des deux plannings.'))
    return {key: _plain_text(value[key], 40, tr('Chaque nom de planning doit contenir de 1 à 40 caractères.'), required=True)
            for key in ("S1", "S2")}


def schedule_labels(db):
    # Existing users keep the names of their two original timetable models.
    return validate_schedule_labels(db.get_setting("desktop_schedule_labels", {"S1": tr('Semestre 1'), "S2": tr('Semestre 2')}))


def new_schedule_labels():
    return {"S1": tr('Planning principal'), "S2": tr('Planning alternatif')}


def example_profile(anchor):
    """An optional, editable example, with no course imposed on a new user."""
    subjects = [
        dict(id="maths", name=tr('Mathématiques'), color="#0071e3", active=True),
        dict(id="francais", name=tr('Expression écrite'), color="#b15430", active=True),
        dict(id="anglais", name=tr('Anglais'), color="#c23c6f", active=True),
        dict(id="informatique", name=tr('Informatique'), color="#4f5bd5", active=True),
        dict(id="subject_" + "1" * 32, name=tr('Méthodologie'), color="#008578", active=True),
    ]
    slots = []
    for day in range(5):
        for index, start in enumerate(("09:00", "11:00")):
            subject = subjects[(day + index) % len(subjects)]
            slots.append(dict(id=f"example-{day}-{index}", weekday=day, start=start,
                              end="10:30" if index == 0 else "12:00", category=subject["id"],
                              title="", week="all"))
    slots.append(dict(id="example-workshop", weekday=2, start="14:00", end="16:00",
                      category="informatique", title=tr('Atelier'), week="A"))
    return subjects, dict(version=2, week_anchor=anchor, semesters={"S1": slots, "S2": []})
