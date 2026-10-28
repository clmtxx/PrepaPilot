"""Shared vocabulary for documents, the timetable and the activity journal."""
from .i18n import tr

SUBJECTS = {
    "maths": "Mathématiques",
    "physique": "Physique-chimie",
    "si": "Sciences de l’ingénieur",
    "informatique": "Informatique (ITC)",
    "francais": "Français-philosophie",
    "anglais": "Anglais",
    "allemand": "Allemand",
    "espagnol": "Espagnol",
    "tipe": "TIPE",
    "eps": "EPS",
    "autre": "Autre",
}
DOCUMENT_KINDS = {"cours": "Cours", "td": "Exercices / TD", "tp": "Travaux pratiques", "devoir": "Devoirs",
                  "colle": "Oraux", "projet": "Projets", "examen": "Examens", "stage": "Stages", "autre": "Autres"}
FIXED_CATEGORIES = {
    "ds": "Évaluation · matière à préciser",
    "cpge": "Temps collectif",
    "permanence": "Travail autonome",
    "sport": "Sport",
    "detente": "Détente",
    "repas": "Repas",
    "sommeil": "Sommeil",
    "trajet": "Trajets",
    "autre": "Autre activité",
}
CATEGORIES = {**SUBJECTS, **FIXED_CATEGORIES}
SUBJECT_COLORS = {
    "maths": "#0071E3", "physique": "#8E44AD", "si": "#008578",
    "informatique": "#4F5BD5", "francais": "#B15430", "anglais": "#C23C6F",
    "allemand": "#B17A12", "espagnol": "#C84F31", "tipe": "#287C96",
    "eps": "#3B8743", "autre": "#68717D",
}
ACTIVITY_COLORS = {
    "ds": "#8D587A", "cpge": "#6673A4", "permanence": "#68717D",
    "sport": "#3B8743", "detente": "#B57E1D", "repas": "#B56F34",
    "sommeil": "#5964A1", "trajet": "#597B87", "autre": "#68717D",
}


def default_subjects():
    return [dict(id=key, name=name, color=SUBJECT_COLORS[key], active=True)
            for key, name in SUBJECTS.items()]


STUDY_CATEGORIES = set(SUBJECTS) - {"eps", "autre"}


def duration_text(minutes):
    hours, rest = divmod(int(minutes), 60)
    return tr("{hours} h {minutes:02d}", hours=hours, minutes=rest) if hours else tr("{minutes} min", minutes=rest)
