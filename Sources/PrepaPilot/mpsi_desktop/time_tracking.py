"""Native activity journal, totals and editable semester timetable."""
from __future__ import annotations

from .i18n import tr, qt_locale, format_datetime
from datetime import date, datetime, timedelta
import sqlite3

from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateEdit, QDateTimeEdit, QDialog, QFormLayout,
    QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit, QProgressBar, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from .catalog import duration_text
from .page_chrome import AccentCard, PageHero, accent_stat_card
from .schedule_setup import SetupDialog
from .study_profile import schedule_labels
from .theme import palette_for
from .time_store import local_stamp, period_bounds
from .widgets import AnimatedDialog, animate_table_row, button, clear_layout, confirm, show_error

DAYS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
ERRORS = (ValueError, OSError, sqlite3.Error)


def label(text, name="muted"):
    result = QLabel(text)
    result.setObjectName(name)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    return result


def categories(ctx, selected=None):
    combo = QComboBox()
    labels = ctx.db.category_labels(include_archived=selected is not None)
    archived = {row["id"] for row in ctx.db.get_subjects(include_archived=True) if not row["active"]}
    for key, title in labels.items():
        title += tr(' · archivée') if key in archived else ""
        combo.addItem(title, key)
        combo.setItemData(combo.count() - 1, QColor(ctx.db.category_color(key)), Qt.ItemDataRole.ForegroundRole)
    if selected in labels:
        combo.setCurrentIndex(combo.findData(selected))
    return combo


def date_field(day):
    result = QDateEdit(QDate.fromString(str(day), "yyyy-MM-dd"))
    result.setCalendarPopup(True)
    result.setLocale(qt_locale())
    result.setDisplayFormat("dd MMM yyyy")
    return result


class ActivityDialog(AnimatedDialog):
    def __init__(self, ctx, day=None, entry=None, parent=None):
        super().__init__(parent)
        self.ctx, self.entry = ctx, entry
        self.saved_id = None
        self._saving = False
        self.setWindowTitle(tr('Modifier une activité') if entry else tr('Ajouter une activité'))
        self.setMinimumWidth(570)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 30, 32, 30)
        outer.setSpacing(18)
        outer.addWidget(label(self.windowTitle(), "dialogTitle"))
        outer.addWidget(label(tr('Les activités réalisées alimentent tes totaux. Les activités prévues restent séparées.')))
        form = QFormLayout()
        form.setSpacing(16)
        self.category = categories(ctx, entry["category"] if entry else None)
        self.title = QLineEdit(entry["title"] if entry else "")
        self.title.setMaxLength(250)
        self.title.setPlaceholderText(tr('Ex. Révision des suites · facultatif'))
        chosen = date.fromisoformat(str(day)) if day else date.today()
        now = datetime.now().replace(second=0, microsecond=0)
        end = now if chosen == now.date() else datetime.combine(chosen, datetime.strptime("19:00", "%H:%M").time())
        start = end - timedelta(hours=1)
        if entry:
            start, end = local_stamp(entry["start_at"]), local_stamp(entry["end_at"])
        self.start = QDateTimeEdit(QDateTime(start))
        self.end = QDateTimeEdit(QDateTime(end))
        for field in (self.start, self.end):
            field.setLocale(qt_locale())
            field.setCalendarPopup(True)
            field.setDisplayFormat("dd/MM/yyyy  HH:mm")
        self.status = QComboBox()
        self.status.addItem(tr('Réalisé · inclure dans mes totaux'), "completed")
        self.status.addItem(tr('Prévu · ne pas encore compter'), "planned")
        self.status.setCurrentIndex(self.status.findData(entry["status"] if entry else "planned" if end > now else "completed"))
        form.addRow(tr('Catégorie'), self.category)
        form.addRow(tr('Activité'), self.title)
        form.addRow(tr('Début'), self.start)
        form.addRow(tr('Fin'), self.end)
        form.addRow(tr('Statut'), self.status)
        outer.addLayout(form)
        self.duration = label("", "sectionTitle")
        outer.addWidget(self.duration)
        outer.addWidget(label(tr('Pour une nuit de sommeil, choisis le lendemain comme date de fin. Un cours annulé peut être supprimé uniquement pour cette date.')))
        self.error = label("", "error")
        self.error.hide()
        outer.addWidget(self.error)
        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(button(tr('Annuler'), self.reject))
        self.save_button = button(tr('Enregistrer'), self.save, primary=True)
        self.save_button.setDefault(True)
        controls.addWidget(self.save_button)
        outer.addLayout(controls)
        self.start.dateTimeChanged.connect(self.update_duration)
        self.end.dateTimeChanged.connect(self.update_duration)
        self.update_duration()

    def update_duration(self, *_):
        minutes = self.start.dateTime().secsTo(self.end.dateTime()) // 60
        self.duration.setText(tr('Durée : {value0}', value0=duration_text(minutes)) if minutes > 0 else tr('La fin doit suivre le début'))

    def save(self):
        if self._saving or self.saved_id is not None:
            return
        self._saving = True
        self.save_button.setEnabled(False)
        values = dict(category=self.category.currentData(), title=self.title.text().strip(),
                      start_at=self.start.dateTime().toString("yyyy-MM-ddTHH:mm"),
                      end_at=self.end.dateTime().toString("yyyy-MM-ddTHH:mm"), status=self.status.currentData())
        try:
            if self.entry:
                self.ctx.db.update_time_entry(self.entry["id"], **values)
                self.saved_id = self.entry["id"]
            else:
                self.saved_id = self.ctx.db.add_time_entry(**values)
        except ERRORS as exc:
            self._saving = False
            self.save_button.setEnabled(True)
            self.error.setText(str(exc))
            self.error.show()
            return
        self.ctx.mark_changed('activities')
        self.ctx.notice.emit(tr('Activité enregistrée.') if not self.entry else tr('Activité modifiée pour cette date.'))
        self.accept()


class SemesterDialog(AnimatedDialog):
    def __init__(self, ctx, day, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(tr('Changer de planning'))
        self.setMinimumWidth(490)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 28, 30, 28)
        outer.setSpacing(18)
        outer.addWidget(label(tr('Un nouvel emploi du temps.'), "dialogTitle"))
        outer.addWidget(label(tr('Le changement s’applique à partir de la date choisie. Les activités déjà passées et les corrections manuelles sont conservées.')))
        form = QFormLayout()
        self.semester = QComboBox()
        for key, name in schedule_labels(ctx.db).items():
            self.semester.addItem(name, key)
        self.semester.setCurrentIndex(self.semester.findData(ctx.db.semester_for_day(day)))
        self.effective = date_field(day)
        form.addRow(tr('Planning'), self.semester)
        form.addRow(tr('À partir du'), self.effective)
        outer.addLayout(form)
        self.error = label("", "error")
        self.error.hide()
        outer.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button(tr('Annuler'), self.reject))
        actions.addWidget(button(tr('Appliquer'), self.save, primary=True))
        outer.addLayout(actions)

    def save(self):
        try:
            self.ctx.db.set_semester(self.semester.currentData(), self.effective.date().toString("yyyy-MM-dd"))
        except ERRORS as exc:
            self.error.setText(str(exc)); self.error.show()
            return
        self.ctx.mark_changed('timetable')
        self.ctx.notice.emit(tr('Changement de planning enregistré. Ton historique reste conservé.'))
        self.accept()


class HolidayDialog(AnimatedDialog):
    """Explicit holiday dates, independent of any region or school calendar."""
    def __init__(self, ctx, day=None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._saving = False
        self._applying_preset = False
        self._summer_end_chosen = False
        self.setWindowTitle(tr('Vacances et pauses'))
        self.setMinimumWidth(540)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 30, 32, 30)
        outer.setSpacing(18)
        outer.addWidget(label(tr('Une pause dans tes cours.'), "dialogTitle"))
        outer.addWidget(label(tr('Pendant cette période, les cours automatiques sont suspendus. Tes activités personnelles, tes corrections et ton historique restent conservés.')))
        form = QFormLayout()
        form.setSpacing(16)
        self.preset = QComboBox()
        self.preset.addItem(tr('Une semaine'), "week")
        self.preset.addItem(tr('Deux semaines'), "fortnight")
        self.preset.addItem(tr('Vacances d’été · dates à choisir'), "summer")
        self.preset.addItem(tr('Période personnalisée'), "custom")
        chosen = max(date.fromisoformat(str(day)) if day else date.today(), ctx.db._time_now().date())
        self.start = date_field(chosen)
        self.end = date_field(chosen + timedelta(days=min(6, (date.max - chosen).days)))
        self.name = QLineEdit(tr('Pause des cours'))
        self.name.setMaxLength(120)
        form.addRow(tr('Durée'), self.preset)
        form.addRow(tr('Premier jour'), self.start)
        form.addRow(tr('Dernier jour inclus'), self.end)
        form.addRow(tr('Nom'), self.name)
        outer.addLayout(form)
        self.summary = label("", "sectionTitle")
        outer.addWidget(self.summary)
        self.hint = label(tr('Tu peux ajuster les deux dates. Aucun calendrier scolaire n’est appliqué automatiquement.'))
        outer.addWidget(self.hint)
        self.error = label("", "error")
        self.error.hide()
        outer.addWidget(self.error)
        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(button(tr('Annuler'), self.reject))
        self.save_button = button(tr('Enregistrer la période'), self.save, primary=True)
        self.save_button.setDefault(True)
        controls.addWidget(self.save_button)
        outer.addLayout(controls)
        self.preset.currentIndexChanged.connect(self.apply_preset)
        self.start.dateChanged.connect(self.start_changed)
        self.end.dateChanged.connect(self.end_changed)
        self.update_summary()

    def apply_preset(self, *_):
        mode = self.preset.currentData()
        self._applying_preset = True
        if mode in {"week", "fortnight"}:
            self.end.setDate(self.start.date().addDays(6 if mode == "week" else 13))
        elif mode == "summer":
            # No assumed summer dates: the user explicitly chooses the last day.
            self.end.setDate(self.start.date())
            self._summer_end_chosen = False
        if self.name.text() in {tr('Pause des cours'), tr('Vacances scolaires'), tr('Vacances d’été')}:
            self.name.setText(tr('Vacances d’été') if mode == "summer" else tr('Pause des cours'))
        self._applying_preset = False
        self.hint.setText(tr('Choisis la date de fin de tes vacances d’été. Aucun calendrier scolaire n’est appliqué automatiquement.')
                          if mode == "summer" else tr('Tu peux ajuster les deux dates. Aucun calendrier scolaire n’est appliqué automatiquement.'))
        self.update_summary()

    def start_changed(self, *_):
        if self.preset.currentData() in {"week", "fortnight"}:
            self.apply_preset()
        else:
            self.update_summary()

    def end_changed(self, *_):
        if not self._applying_preset:
            self._summer_end_chosen = True
        self.update_summary()

    def update_summary(self):
        count = self.start.date().daysTo(self.end.date()) + 1
        if count <= 0:
            self.summary.setText(tr('La fin doit être le même jour que le début, ou après.'))
        else:
            resume = self.end.date().addDays(1)
            if resume > self.end.maximumDate():
                template = "{count} jour · jusqu’au {date}" if count == 1 else "{count} jours · jusqu’au {date}"
                resume = self.end.date()
            else:
                template = "{count} jour · reprise le {date}" if count == 1 else "{count} jours · reprise le {date}"
            self.summary.setText(tr(template, count=count, date=qt_locale().toString(resume, "dd MMMM yyyy")))

    def save(self):
        if self._saving:
            return
        if self.preset.currentData() == "summer" and not self._summer_end_chosen:
            self.error.setText(tr('Choisis la date de fin de tes vacances d’été avant d’enregistrer.'))
            self.error.show()
            self.end.setFocus()
            return
        self._saving = True
        self.save_button.setEnabled(False)
        try:
            self.ctx.db.add_holiday(self.start.date().toString("yyyy-MM-dd"), self.end.date().toString("yyyy-MM-dd"), self.name.text())
        except ERRORS as exc:
            self._saving = False
            self.save_button.setEnabled(True)
            self.error.setText(str(exc))
            self.error.show()
            return
        self.ctx.mark_changed('timetable')
        self.ctx.notice.emit(tr('Pause enregistrée. Les cours automatiques reprendront à la date indiquée.'))
        self.accept()


class TimetableDialog(SetupDialog):
    """Compatibility entry point that opens the personal schedule editor."""
    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent=parent, first_run=False)
        self.show_step(1)


class TimeTrackingPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.rows = []
        outer = QVBoxLayout(self)
        outer.setSizeConstraint(QLayout.SetMinimumSize)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(22)
        self.hero = PageHero(ctx, "time", tr('GESTION DU TEMPS'), tr('Emploi du temps et journal'),
                             tr('Prévois ta journée et garde une trace du temps réellement consacré à tes activités.'),
                             actions=[button(tr('+ Une activité'), self.add_activity, primary=True)])
        outer.addWidget(self.hero)
        calendar = AccentCard(ctx, "time")
        calendar.body.setContentsMargins(24, 18, 24, 18)
        calendar.body.setSpacing(12)
        navigation = QHBoxLayout()
        navigation.setSpacing(8)
        navigation.addWidget(button("‹", lambda: self.shift_day(-1)))
        self.day = date_field(date.today())
        self.day.setAccessibleName(tr('Journée du journal'))
        navigation.addWidget(self.day)
        navigation.addWidget(button("›", lambda: self.shift_day(1)))
        navigation.addWidget(button(tr('Aujourd’hui'), lambda: self.day.setDate(QDate.currentDate())))
        navigation.addStretch()
        self.semester_label = label("")
        navigation.addWidget(self.semester_label)
        calendar.body.addLayout(navigation)
        planning = QHBoxLayout()
        planning.setSpacing(8)
        planning.addWidget(button(tr('Mon emploi du temps'), self.edit_timetable))
        planning.addWidget(button(tr('Changer de planning'), self.change_semester))
        planning.addWidget(button(tr('Vacances et pauses'), self.edit_holidays))
        planning.addStretch()
        calendar.body.addLayout(planning)
        holiday_mode = QHBoxLayout()
        holiday_mode.setSpacing(14)
        self.holiday_status = label("")
        holiday_mode.addWidget(self.holiday_status, 1)
        self.resume_button = button(tr('Reprendre ce jour'), self.resume_courses)
        holiday_mode.addWidget(self.resume_button)
        calendar.body.addLayout(holiday_mode)
        self.notice = label("")
        calendar.body.addWidget(self.notice)
        outer.addWidget(calendar)
        journal = AccentCard(ctx, "time")
        journal.body.setSizeConstraint(QLayout.SetMinimumSize)
        journal.body.addWidget(label(tr('LE JOURNAL DE TA JOURNÉE'), "colorEyebrow"))
        titlebar = QHBoxLayout()
        self.journal_title = label(tr('Ma journée'), "sectionTitle")
        titlebar.addWidget(self.journal_title)
        titlebar.addStretch()
        self.validate_button = button(tr('Valider les activités passées'), self.complete_day, primary=True)
        titlebar.addWidget(self.validate_button)
        journal.body.addLayout(titlebar)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([tr('Horaire'), tr('Activité'), tr('Catégorie'), tr('Ce jour'), tr('Statut'), tr('Origine')])
        self.table.setShowGrid(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setMinimumHeight(240)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setAccessibleName(tr('Activités prévues et réalisées de la journée'))
        journal.body.addWidget(self.table)
        self.empty = label(tr('Ta journée est libre. Ajoute du travail personnel, du sport, un repas ou une nuit de sommeil.'))
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setMinimumHeight(90)
        journal.body.addWidget(self.empty)
        actions = QHBoxLayout()
        self.edit_button = button(tr('Modifier'), self.edit_activity)
        self.delete_button = button(tr('Supprimer pour ce jour'), self.delete_activity, danger=True)
        actions.addWidget(self.edit_button)
        actions.addStretch()
        actions.addWidget(self.delete_button)
        journal.body.addLayout(actions)
        journal.body.addWidget(label(tr('Prévu n’est jamais compté comme réalisé. Vérifie les cours annulés ou déplacés avant de valider ta journée.')))
        outer.addWidget(journal)
        totals = AccentCard(ctx, "documents")
        totals.body.setSizeConstraint(QLayout.SetMinimumSize)
        totals.body.addWidget(label(tr('TON TEMPS, EN PERSPECTIVE'), "colorEyebrow"))
        filterbar = QHBoxLayout()
        filterbar.addWidget(label(tr('Où va ton temps ?'), "sectionTitle"))
        filterbar.addStretch()
        self.period = QComboBox()
        for text, value in ((tr('Ce jour'), "day"), (tr('Cette semaine'), "week"), (tr('Tout l’historique'), "all"), (tr('Période personnalisée'), "custom")):
            self.period.addItem(text, value)
        filterbar.addWidget(self.period)
        totals.body.addLayout(filterbar)
        date_range = QHBoxLayout()
        date_range.setSpacing(12)
        self.from_date = date_field(date.today() - timedelta(days=6))
        self.to_date = date_field(date.today())
        self.from_date.setAccessibleName(tr('Premier jour des totaux'))
        self.to_date.setAccessibleName(tr('Dernier jour des totaux'))
        date_range.addWidget(self.from_date)
        date_range.addWidget(self.to_date)
        date_range.addStretch()
        totals.body.addLayout(date_range)
        highlights = QHBoxLayout()
        highlights.setSpacing(12)
        self.completed_stat = accent_stat_card(ctx, "time", tr('Temps réalisé'), "—", tr('Toutes tes activités'))
        self.study_stat = accent_stat_card(ctx, "notes", tr('Par matière'), "—", tr('Dans le temps réalisé'))
        self.planned_stat = accent_stat_card(ctx, "settings", tr('Temps prévu'), "—", tr('À confirmer, non compté'))
        for stat in (self.completed_stat, self.study_stat, self.planned_stat):
            stat.body.setContentsMargins(18, 16, 18, 16)
            stat.value.setWordWrap(True)
            highlights.addWidget(stat, 1)
        totals.body.addLayout(highlights)
        self.total_summary = label("")
        totals.body.addWidget(self.total_summary)
        self.total_rows = QVBoxLayout()
        self.total_rows.setSpacing(10)
        totals.body.addLayout(self.total_rows)
        outer.addWidget(totals)
        outer.addStretch()
        self.day.dateChanged.connect(self.refresh)
        self.period.currentIndexChanged.connect(self.refresh_totals)
        self.from_date.dateChanged.connect(self.refresh_totals)
        self.to_date.dateChanged.connect(self.refresh_totals)
        self.table.itemSelectionChanged.connect(self.update_actions)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_activity())
        ctx.watch_data(self.refresh, 'activities', 'timetable', 'subjects')
        ctx.theme_changed.connect(self.refresh)
        # reload_data emits data_changed after data_replaced; refresh once.
        self.refresh()

    def selected_day(self):
        return self.day.date().toString("yyyy-MM-dd")

    def shift_day(self, offset):
        self.day.setDate(self.day.date().addDays(offset))

    def refresh(self, *_):
        selected = self.selected_entry()
        identity = selected["id"] if selected else None
        day = self.selected_day()
        try:
            result = self.ctx.db.ensure_day(day)
            self.rows = self.ctx.db.list_time_entries(day, day)
        except ERRORS as exc:
            self.notice.setText(str(exc))
            return
        self.semester_label.setText(tr("{schedule} · semaine {week}", schedule=schedule_labels(self.ctx.db)[self.ctx.db.semester_for_day(day)], week=self.ctx.db.week_for_day(day)))
        holiday = self.ctx.db.holiday_for_day(day)
        if holiday:
            start = qt_locale().toString(QDate.fromString(holiday["start"], "yyyy-MM-dd"), "dd MMMM")
            end = qt_locale().toString(QDate.fromString(holiday["end"], "yyyy-MM-dd"), "dd MMMM yyyy")
            self.holiday_status.setText(tr('{value0} · du {value1} au {value2} inclus', value0=holiday['label'], value1=start, value2=end))
        else:
            self.holiday_status.setText(tr('Les cours suivent ton emploi du temps.'))
        self.resume_button.setVisible(bool(holiday and day >= self.ctx.db._time_now().date().isoformat()))
        self.resume_button.setToolTip(tr("Reprendre les cours à partir du {date}", date=qt_locale().toString(self.day.date(), "dd MMMM yyyy")))
        self.journal_title.setText(tr(DAYS[self.day.date().dayOfWeek() - 1]) + " · " + qt_locale().toString(self.day.date(), "dd MMMM"))
        conflicts = result["conflicts"]
        self.notice.setText(tr('{value0} créneau(x) de l’emploi du temps n’ont pas été ajoutés à cause d’un chevauchement. ', value0=len(conflicts)) + conflicts[0]
                            if conflicts else tr('Vacances : ajoute tes activités à ton rythme. Les cours automatiques sont suspendus.')
                            if holiday else tr('L’emploi du temps remplit les cours prévus. Ajoute ensuite tes activités personnelles.'))
        lower, upper = period_bounds(day, day)
        self.table.setRowCount(len(self.rows))
        colors = palette_for(self.ctx.theme)
        category_names = self.ctx.db.category_labels(include_archived=True)
        for row_index, entry in enumerate(self.rows):
            start, end = local_stamp(entry["start_at"]), local_stamp(entry["end_at"])
            minutes = int((min(end, upper) - max(start, lower)).total_seconds() // 60)
            times = start.strftime("%H:%M") + "–" + end.strftime("%H:%M")
            if start.date() != end.date():
                times = format_datetime(start) + " → " + format_datetime(end)
            values = [times, entry["title"], category_names.get(entry["category"], entry["category"]), duration_text(minutes),
                      tr('Réalisé') if entry["status"] == "completed" else tr('Prévu'),
                      tr('Personnel') if entry["source"] == "manual" else tr('Corrigé ce jour') if entry["manual_override"] else tr('Emploi du temps')]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, entry["id"])
                if column in (0, 2):
                    item.setForeground(QColor(self.ctx.db.category_color(entry["category"])))
                if column == 4:
                    item.setForeground(QColor(colors["green"] if entry["status"] == "completed" else colors["muted"]))
                item.setToolTip(text if column != 3 else tr('{value0} pour toute l’activité ; {value1} sur cette journée.', value0=duration_text(entry['minutes']), value1=duration_text(minutes)))
                self.table.setItem(row_index, column, item)
            if entry["id"] == identity:
                self.table.selectRow(row_index)
        self.table.setVisible(bool(self.rows))
        self.empty.setVisible(not self.rows)
        self.validate_button.setEnabled(any(row["status"] == "planned" and local_stamp(row["end_at"]) <= datetime.now() for row in self.rows))
        self.update_actions()
        self.refresh_totals()

    def refresh_totals(self, *_):
        mode = self.period.currentData()
        self.from_date.setVisible(mode == "custom")
        self.to_date.setVisible(mode == "custom")
        day = date.fromisoformat(self.selected_day())
        if mode == "day":
            start = end = day.isoformat()
        elif mode == "week":
            first = day - timedelta(days=day.weekday())
            start = first.isoformat()
            end = (first + timedelta(days=min(6, (date.max - first).days))).isoformat()
        elif mode == "custom":
            start, end = self.from_date.date().toString("yyyy-MM-dd"), self.to_date.date().toString("yyyy-MM-dd")
        else:
            start = end = None
        clear_layout(self.total_rows)
        try:
            completed = self.ctx.db.time_totals(start, end)
            planned = self.ctx.db.time_totals(start, end, status="planned")
        except ERRORS as exc:
            self.total_summary.setText(str(exc))
            for stat in (self.completed_stat, self.study_stat, self.planned_stat):
                stat.value.setText("—")
            return
        total = sum(completed.values())
        study_categories = self.ctx.db.study_categories()
        category_names = self.ctx.db.category_labels(include_archived=True)
        study = sum(minutes for category, minutes in completed.items() if category in study_categories)
        self.completed_stat.value.setText(duration_text(total))
        self.study_stat.value.setText(duration_text(study))
        self.planned_stat.value.setText(duration_text(sum(planned.values())))
        self.total_summary.setText(tr('{value0} réalisées · dont {value1} par matière · {value2} prévues, non comptées.', value0=duration_text(total), value1=duration_text(study), value2=duration_text(sum(planned.values()))))
        if not completed:
            self.total_rows.addWidget(label(tr('Pas encore d’activité réalisée sur cette période. Valide les séances passées ou ajoute une activité.')))
        for category, minutes in sorted(completed.items(), key=lambda pair: pair[1], reverse=True):
            row = QHBoxLayout()
            name = label(category_names.get(category, category))
            name.setMinimumWidth(180)
            name.setStyleSheet("font-weight:600;")
            row.addWidget(name)
            bar = QProgressBar()
            bar.setRange(0, max(total, 1))
            bar.setValue(minutes)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            category_color = QColor(self.ctx.db.category_color(category))
            bar.setStyleSheet(
                "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, "
                f"stop:0 {category_color.name()}, stop:1 {category_color.lighter(125).name()}); border-radius:5px; }}"
            )
            row.addWidget(bar, 1)
            row.addWidget(label(duration_text(minutes)))
            self.total_rows.addLayout(row)

    def selected_entry(self):
        selected = self.table.selectionModel().selectedRows()
        if selected:
            item = self.table.item(selected[0].row(), 0)
            identity = item.data(Qt.ItemDataRole.UserRole) if item else None
            return next((row for row in self.rows if row["id"] == identity), None)
        return None

    def update_actions(self):
        enabled = self.selected_entry() is not None
        self.edit_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)

    def show_saved(self, identity):
        self.refresh()
        for index, row in enumerate(self.rows):
            if row["id"] == identity:
                self.table.selectRow(index)
                self.table.scrollToItem(self.table.item(index, 0))
                animate_table_row(self.table, index, self.ctx)
                break

    def add_activity(self):
        dialog = ActivityDialog(self.ctx, day=self.selected_day(), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.day.setDate(dialog.start.date())
            self.show_saved(dialog.saved_id)

    def edit_activity(self):
        selected = self.selected_entry()
        if selected:
            dialog = ActivityDialog(self.ctx, entry=selected, parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.day.setDate(dialog.start.date())
                self.show_saved(dialog.saved_id)

    def delete_activity(self):
        selected = self.selected_entry()
        if selected and confirm(self, tr('Supprimer cette activité ?'), tr('« {value0} » sera retirée pour cette date. Les autres journées et l’emploi du temps ne changent pas.', value0=selected['title'])):
            try:
                self.ctx.db.delete_time_entry(selected["id"])
            except ERRORS as exc:
                show_error(self, str(exc)); return
            self.ctx.mark_changed('activities')
            self.ctx.notice.emit(tr('Activité retirée de cette journée.'))

    def complete_day(self):
        count = sum(row["status"] == "planned" and local_stamp(row["end_at"]) <= datetime.now() for row in self.rows)
        if not count or not confirm(self, tr('Valider les activités passées ?'), tr('Les {value0} activités prévues déjà terminées seront comptées comme réalisées. Vérifie d’abord les absences et changements d’horaires. Les créneaux futurs restent prévus.', value0=count)):
            return
        try:
            saved = self.ctx.db.complete_day(self.selected_day())
        except ERRORS as exc:
            show_error(self, str(exc)); return
        self.ctx.mark_changed('activities')
        self.ctx.notice.emit(tr('{value0} activité(s) validée(s). Tes totaux sont à jour.', value0=saved))

    def change_semester(self):
        SemesterDialog(self.ctx, self.selected_day(), self).exec()

    def edit_timetable(self):
        TimetableDialog(self.ctx, self).exec()

    def edit_holidays(self):
        HolidayDialog(self.ctx, self.selected_day(), self).exec()

    def resume_courses(self):
        when = qt_locale().toString(self.day.date(), "dd MMMM yyyy")
        if not confirm(self, tr('Reprendre les cours ?'), tr('Les cours automatiques reprendront à partir du {value0}. L’historique, tes activités personnelles et les autres vacances programmées seront conservés.', value0=when)):
            return
        try:
            changed = self.ctx.db.end_holiday(self.selected_day())
        except ERRORS as exc:
            show_error(self, str(exc))
            return
        if changed:
            self.ctx.mark_changed('timetable')
            self.ctx.notice.emit(tr("Reprise des cours enregistrée pour le {date}.", date=when))
