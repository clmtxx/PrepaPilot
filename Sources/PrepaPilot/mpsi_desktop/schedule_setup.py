"""Two-step personal subject and alternating-week timetable configuration."""
from __future__ import annotations

from .i18n import tr, qt_locale
import copy
from datetime import date, timedelta
import sqlite3
import uuid

from PySide6.QtCore import QDate, QPointF, QRectF, Qt, QTime
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QDateEdit, QDialog,
    QHBoxLayout, QHeaderView, QLabel, QInputDialog, QStackedWidget, QTableWidget,
    QTableWidgetItem, QTimeEdit, QVBoxLayout, QWidget,
)

from .catalog import FIXED_CATEGORIES
from .subject_store import validate_subjects
from .study_profile import schedule_labels, new_schedule_labels, validate_schedule_labels, example_profile
from .theme import palette_for
from .widgets import AnimatedDialog, button

DAYS = ("Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche")
COLORS = ("#0071e3", "#e09b13", "#bf66cf", "#299b91", "#e76d57", "#749b38", "#557cc4")


def text_label(text, name="muted"):
    label = QLabel(text)
    label.setObjectName(name)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class WeekPreview(QWidget):
    """A compact, color-coded Monday-to-Sunday overview of the draft."""
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.slots = []
        self.names = {}
        self.colors = {}
        self.week = "any"
        self.setMinimumHeight(110)
        self.setMaximumHeight(205)
        self.setAccessibleName(tr('Aperçu de l’emploi du temps du lundi au dimanche'))
        ctx.theme_changed.connect(self.update)

    def set_data(self, slots, names, colors, week):
        self.slots, self.names, self.colors, self.week = slots, names, colors, week
        self.setAccessibleDescription(" ; ".join(
            tr("{day} {start}–{end} {subject} semaine {week}", day=tr(DAYS[slot['weekday']]), start=slot['start'], end=slot['end'], subject=names.get(slot['category'], slot['category']), week=tr("Toutes") if slot.get('week', 'all') == 'all' else slot['week'])
            for slot in slots))
        self.update()

    def paintEvent(self, event):
        palette = palette_for(self.ctx.theme)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(self.font())
        font.setPointSizeF(8.3)
        painter.setFont(font)
        width = self.width() / 7
        height = self.height() - 29
        to_minutes = lambda value: int(value[:2]) * 60 + int(value[3:])
        start = min([480] + [to_minutes(slot["start"]) for slot in self.slots])
        end = max([1080] + [to_minutes(slot["end"]) for slot in self.slots])
        for day, name in enumerate(DAYS):
            rect = QRectF(day * width + 2, 27, width - 4, height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(palette["surface2"]))
            painter.drawRoundedRect(rect, 8, 8)
            painter.setPen(QColor(palette["muted"]))
            painter.drawText(QRectF(day * width, 0, width, 23), Qt.AlignmentFlag.AlignCenter, tr(name))
        for slot in self.slots:
            week = slot.get("week", "all")
            if self.week != "any" and week not in {"all", self.week}:
                continue
            x, card_width = slot["weekday"] * width + 5, width - 10
            if self.week == "any" and week in {"A", "B"}:
                card_width = (width - 12) / 2
                if week == "B":
                    x += card_width + 2
            y = 29 + (to_minutes(slot["start"]) - start) / max(1, end - start) * (height - 4)
            block_height = max(8, (to_minutes(slot["end"]) - to_minutes(slot["start"])) / max(1, end - start) * (height - 4))
            rect = QRectF(x, y, card_width, max(6, block_height - 2))
            color = QColor(self.colors.get(slot["category"], "#0071e3"))
            background = QColor(color)
            background.setAlpha(50 if self.ctx.theme == "dark" else 32)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(rect, 5, 5)
            painter.setPen(QPen(color, 3))
            painter.drawLine(rect.topLeft() + QPointF(2, 3), rect.bottomLeft() + QPointF(2, -3))
            painter.setPen(QColor(palette["text"]))
            title = self.names.get(slot["category"], slot["category"])
            if rect.height() >= 15:
                painter.drawText(rect.adjusted(7, 0, -2, 0), Qt.AlignmentFlag.AlignVCenter,
                                 painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, int(max(1, card_width - 10))))
        painter.end()


class SetupDialog(AnimatedDialog):
    def __init__(self, ctx, parent=None, first_run=False):
        super().__init__(parent)
        self.ctx, self.first_run = ctx, first_run
        self.schedule_names = new_schedule_labels() if first_run else schedule_labels(ctx.db)
        self.subject_rows = copy.deepcopy(ctx.db.get_subjects(include_archived=True))
        self.data = copy.deepcopy(ctx.db.get_timetable())
        self.data.setdefault("week_anchor", "2026-08-31")
        if first_run:
            today = date.today()
            self.data["week_anchor"] = (today - timedelta(days=today.weekday())).isoformat()
            self.subject_rows = []
            self.data["semesters"] = {"S1": [], "S2": []}
        self.data["version"] = 2
        self.active_semester = "S1"
        self.visible_ids = set()
        self._loading = False
        self._saving = False
        self._chosen_start = not first_run
        self.setWindowTitle(tr('Configurer PrépaPilot') if first_run else tr('Matières et emploi du temps'))
        screen = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(900, screen.width() - 60), min(660, screen.height() - 60))
        self.resize(min(1100, screen.width() - 60), min(860, screen.height() - 60))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 26, 28, 26)
        outer.setSpacing(15)
        self.heading = text_label(tr('Un espace qui suit ton rythme.'), "dialogTitle")
        outer.addWidget(self.heading)
        self.step_label = text_label("")
        outer.addWidget(self.step_label)
        self.steps = QStackedWidget()
        outer.addWidget(self.steps, 1)
        self.build_subject_step()
        self.build_schedule_step()
        self.error = text_label("", "error")
        self.error.hide()
        outer.addWidget(self.error)
        actions = QHBoxLayout()
        self.cancel_button = button(tr('Quitter') if first_run else tr('Annuler'), self.reject)
        actions.addWidget(self.cancel_button)
        actions.addStretch()
        self.back_button = button(tr('Retour aux matières'), self.go_back)
        actions.addWidget(self.back_button)
        self.next_button = button(tr('Continuer vers l’emploi du temps'), self.next_step, primary=True)
        self.next_button.setDefault(True)
        actions.addWidget(self.next_button)
        self.save_button = button(tr('Terminer la configuration') if first_run else tr('Enregistrer'), self.save, primary=True)
        actions.addWidget(self.save_button)
        outer.addLayout(actions)
        self.populate_subjects()
        self.populate()
        self.show_step(0)

    def build_subject_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        if self.first_run:
            layout.addWidget(text_label(tr('Choisis un point de départ. Tu pourras ensuite modifier chaque matière et chaque créneau.')))
            choices = QHBoxLayout()
            choices.addWidget(button(tr('Partir de zéro'), self.start_empty))
            choices.addWidget(button(tr('Utiliser un exemple'), self.use_example))
            choices.addStretch()
            layout.addLayout(choices)
        layout.addWidget(text_label(tr('Nomme tes matières et choisis une couleur pour chacune. Archiver une matière conserve son historique et ses documents.')))
        self.subject_table = QTableWidget(0, 3)
        self.subject_table.setHorizontalHeaderLabels([tr('Matière'), tr('Couleur'), tr('Disponibilité')])
        self.subject_table.verticalHeader().hide()
        self.subject_table.verticalHeader().setDefaultSectionSize(50)
        self.subject_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.subject_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.subject_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.subject_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.subject_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.subject_table.setStyleSheet("QTableWidget::item { padding: 4px; }")
        layout.addWidget(self.subject_table, 1)
        row = QHBoxLayout()
        self.add_subject_button = button(tr('+ Ajouter une matière'), self.add_subject)
        self.archive_button = button(tr('Archiver / réactiver'), self.toggle_archive)
        row.addWidget(self.add_subject_button)
        row.addWidget(self.archive_button)
        row.addStretch()
        layout.addLayout(row)
        self.subject_table.setEnabled(not self.first_run)
        self.add_subject_button.setEnabled(not self.first_run)
        self.archive_button.setEnabled(not self.first_run)
        self.steps.addWidget(page)

    def build_schedule_step(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(text_label(tr('Ajoute tes cours du lundi au dimanche, toutes les semaines ou seulement en A ou B. Tu peux aussi laisser le planning vide et le compléter plus tard. Les deux modèles sont renommables : semestre, trimestre, stage…')))
        navigation = QHBoxLayout()
        self.semester = QComboBox()
        for key, name in self.schedule_names.items():
            self.semester.addItem(name, key)
        self.semester.setMaximumWidth(220)
        self.semester.setAccessibleName(tr('Modèle d’emploi du temps'))
        self.day_filter = QComboBox()
        self.day_filter.addItem(tr('Tous les jours'), -1)
        for index, name in enumerate(DAYS):
            self.day_filter.addItem(tr(name), index)
        self.week_filter = QComboBox()
        for title, value in ((tr('Vue A + B'), "any"), (tr('Semaine A'), "A"), (tr('Semaine B'), "B")):
            self.week_filter.addItem(title, value)
        navigation.addWidget(self.semester)
        navigation.addWidget(button(tr('Renommer'), self.rename_schedule))
        navigation.addWidget(self.day_filter)
        navigation.addWidget(self.week_filter)
        navigation.addStretch()
        navigation.addWidget(button(tr('+ Créneau'), self.add_slot))
        navigation.addWidget(button(tr('Retirer'), self.remove_slot, danger=True))
        layout.addLayout(navigation)
        anchor_row = QHBoxLayout()
        anchor_row.addWidget(text_label(tr('Un lundi de semaine A :')))
        self.anchor = QDateEdit(QDate.fromString(self.data["week_anchor"], "yyyy-MM-dd"))
        self.anchor.setCalendarPopup(True)
        self.anchor.setLocale(qt_locale())
        self.anchor.setDisplayFormat("dd MMM yyyy")
        self.anchor.setAccessibleName(tr('Lundi de référence de la semaine A'))
        anchor_row.addWidget(self.anchor)
        self.anchor_hint = text_label("")
        anchor_row.addWidget(self.anchor_hint, 1)
        layout.addLayout(anchor_row)
        self.preview = WeekPreview(self.ctx)
        layout.addWidget(self.preview, 1)
        self.table = QTableWidget(0, 6)
        self.table.setObjectName("timetableEditor")
        self.table.setStyleSheet("""
            QTableWidget#timetableEditor::item { padding: 4px; }
            QTableWidget#timetableEditor QComboBox,
            QTableWidget#timetableEditor QTimeEdit { padding: 4px 8px; min-height: 24px; }
            QTableWidget#timetableEditor QTimeEdit QLineEdit { padding: 0; border: none; background: transparent; }
        """)
        self.table.setHorizontalHeaderLabels([tr('Jour'), tr('Début'), tr('Fin'), tr('Matière / activité'), tr('Libellé facultatif'), tr('Répétition')])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setMinimumHeight(120)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.horizontalHeader().setMinimumSectionSize(120)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table, 1)
        self.semester.currentIndexChanged.connect(self.change_filters)
        self.day_filter.currentIndexChanged.connect(self.change_filters)
        self.week_filter.currentIndexChanged.connect(self.change_filters)
        self.anchor.dateChanged.connect(self.normalize_anchor)
        self.table.itemChanged.connect(self.update_preview)
        self.normalize_anchor()
        self.steps.addWidget(page)

    def category_names(self):
        names = {key: tr(value) for key, value in FIXED_CATEGORIES.items()}
        names.update({row["id"]: row["name"] for row in self.subject_rows})
        return names

    def subject_colors(self):
        colors = {key: self.ctx.db.category_color(key) for key in self.category_names()}
        colors.update({row["id"]: row["color"] for row in self.subject_rows})
        return colors

    def start_empty(self):
        self.subject_rows = []
        self.data = dict(version=2, week_anchor=self.anchor.date().toString("yyyy-MM-dd"), semesters={"S1": [], "S2": []})
        self.enable_subjects()
        self.populate_subjects()
        self.populate()
        self.add_subject()

    def use_example(self):
        self.subject_rows, self.data = example_profile(self.anchor.date().toString("yyyy-MM-dd"))
        self.enable_subjects()
        self.populate_subjects()
        self.populate()

    def rename_schedule(self):
        key = self.semester.currentData()
        name, accepted = QInputDialog.getText(self, tr('Nom du planning'), tr('Nom (40 caractères maximum)'), text=self.schedule_names[key])
        if not accepted:
            return
        try:
            self.schedule_names = validate_schedule_labels({**self.schedule_names, key: name})
        except ValueError as exc:
            self.error.setText(str(exc)); self.error.show()
            return
        self.semester.setItemText(self.semester.findData(key), self.schedule_names[key])
        self.error.hide()

    def enable_subjects(self):
        self._chosen_start = True
        self.subject_table.setEnabled(True)
        self.add_subject_button.setEnabled(True)
        self.archive_button.setEnabled(True)
        self.error.hide()

    def populate_subjects(self):
        self.subject_table.setRowCount(0)
        for row in self.subject_rows:
            self.append_subject(row)

    def append_subject(self, subject):
        row = self.subject_table.rowCount()
        self.subject_table.insertRow(row)
        item = QTableWidgetItem(subject["name"])
        item.setData(Qt.ItemDataRole.UserRole, subject["id"])
        self.subject_table.setItem(row, 0, item)
        color_button = button(subject["color"])
        self.paint_color_button(color_button, subject["color"])
        color_button.clicked.connect(lambda checked=False, control=color_button: self.choose_color(control))
        self.subject_table.setCellWidget(row, 1, color_button)
        active = QCheckBox(tr('Active') if subject["active"] else tr('Archivée'))
        active.setChecked(subject["active"])
        active.toggled.connect(lambda checked, control=active: control.setText(tr('Active') if checked else tr('Archivée')))
        self.subject_table.setCellWidget(row, 2, active)

    def paint_color_button(self, control, color):
        control.setProperty("subjectColor", color)
        control.setText(color.upper())
        control.setMinimumWidth(112)
        chosen = QColor(color)
        brightness = .2126 * chosen.redF() + .7152 * chosen.greenF() + .0722 * chosen.blueF()
        foreground = "#141416" if brightness > .65 else "#ffffff"
        control.setStyleSheet(f"background:{color};color:{foreground};border:1px solid {color};padding:4px 14px;border-radius:12px;")
        control.setAccessibleName(tr("Choisir la couleur {color}", color=color))

    def choose_color(self, control):
        chosen = QColorDialog.getColor(QColor(control.property("subjectColor")), self, tr('Couleur de la matière'))
        if chosen.isValid():
            self.paint_color_button(control, chosen.name())

    def add_subject(self):
        self.append_subject(dict(id="subject_" + uuid.uuid4().hex, name="", color=COLORS[self.subject_table.rowCount() % len(COLORS)], active=True))
        row = self.subject_table.rowCount() - 1
        self.subject_table.selectRow(row)
        self.subject_table.scrollToBottom()
        self.subject_table.editItem(self.subject_table.item(row, 0))

    def toggle_archive(self):
        row = self.subject_table.currentRow()
        if row >= 0:
            active = self.subject_table.cellWidget(row, 2)
            active.setChecked(not active.isChecked())

    def collect_subjects(self):
        result = []
        for row in range(self.subject_table.rowCount()):
            item = self.subject_table.item(row, 0)
            result.append(dict(id=item.data(Qt.ItemDataRole.UserRole), name=item.text().strip(),
                               color=self.subject_table.cellWidget(row, 1).property("subjectColor"),
                               active=self.subject_table.cellWidget(row, 2).isChecked()))
        return validate_subjects(result)

    def show_step(self, index):
        self.steps.setCurrentIndex(index)
        self.step_label.setText(tr('ÉTAPE 1 SUR 2  ·  Tes matières et leurs couleurs') if index == 0 else tr('ÉTAPE 2 SUR 2  ·  Ton emploi du temps et tes semaines A / B'))
        self.back_button.setVisible(index == 1)
        self.next_button.setVisible(index == 0)
        self.save_button.setVisible(index == 1)

    def next_step(self):
        self.next_button.setFocus()
        try:
            if not self._chosen_start:
                raise ValueError(tr('Choisis « Partir de zéro » ou « Utiliser un exemple ».'))
            self.subject_rows = self.collect_subjects()
            if not any(row["active"] for row in self.subject_rows):
                raise ValueError(tr('Ajoute au moins une matière active pour continuer.'))
        except ValueError as exc:
            self.error.setText(str(exc)); self.error.show()
            return
        self.capture()
        self.populate()
        self.error.hide()
        self.show_step(1)

    def go_back(self):
        self.capture()
        self.show_step(0)

    def capture(self):
        if self._loading:
            return
        rows = []
        for row in range(self.table.rowCount()):
            title = self.table.item(row, 4)
            if title is None:
                continue
            rows.append(dict(id=title.data(Qt.ItemDataRole.UserRole), weekday=self.table.cellWidget(row, 0).currentData(),
                             start=self.table.cellWidget(row, 1).time().toString("HH:mm"), end=self.table.cellWidget(row, 2).time().toString("HH:mm"),
                             category=self.table.cellWidget(row, 3).currentData(), title=title.text().strip(),
                             week=self.table.cellWidget(row, 5).currentData()))
        remaining = [row for row in self.data["semesters"][self.active_semester] if row["id"] not in self.visible_ids]
        self.data["semesters"][self.active_semester] = remaining + rows
        self.visible_ids = {row["id"] for row in rows}
        self.data["week_anchor"] = self.anchor.date().toString("yyyy-MM-dd")

    def populate(self):
        self._loading = True
        self.table.setRowCount(0)
        day, week = self.day_filter.currentData(), self.week_filter.currentData()
        slots = sorted(self.data["semesters"][self.active_semester], key=lambda row: (row["weekday"], row["start"]))
        visible = [row for row in slots if (day == -1 or row["weekday"] == day) and (week == "any" or row.get("week", "all") in {"all", week})]
        self.visible_ids = {row["id"] for row in visible}
        for slot in visible:
            self.append_slot(slot)
        self._loading = False
        self.update_preview()

    def append_slot(self, slot):
        row = self.table.rowCount()
        self.table.insertRow(row)
        day = QComboBox()
        for index, name in enumerate(DAYS):
            day.addItem(tr(name), index)
        day.setCurrentIndex(slot["weekday"])
        self.table.setCellWidget(row, 0, day)
        for column, field in ((1, "start"), (2, "end")):
            widget = QTimeEdit(QTime.fromString(slot[field], "HH:mm"))
            widget.setDisplayFormat("HH:mm")
            widget.setLocale(qt_locale())
            self.table.setCellWidget(row, column, widget)
            widget.timeChanged.connect(self.update_preview)
        category = QComboBox()
        inactive = {subject["id"] for subject in self.subject_rows if not subject["active"]}
        names = self.category_names()
        colors = self.subject_colors()
        for key, name in names.items():
            if key in inactive and key != slot["category"]:
                continue
            category.addItem(name + (tr(' · archivée') if key in inactive else ""), key)
            category.setItemData(category.count() - 1, QColor(colors.get(key, "#0071e3")), Qt.ItemDataRole.ForegroundRole)
        if category.findData(slot["category"]) < 0:
            category.addItem(names.get(slot["category"], slot["category"]), slot["category"])
        category.setCurrentIndex(category.findData(slot["category"]))
        self.table.setCellWidget(row, 3, category)
        title = QTableWidgetItem(slot.get("title", ""))
        title.setData(Qt.ItemDataRole.UserRole, slot["id"])
        self.table.setItem(row, 4, title)
        week = QComboBox()
        for name, key in ((tr('Toutes'), "all"), (tr('Semaine A'), "A"), (tr('Semaine B'), "B")):
            week.addItem(name, key)
        week.setMinimumWidth(116)
        week.setCurrentIndex(week.findData(slot.get("week", "all")))
        self.table.setCellWidget(row, 5, week)
        for widget in (day, category, week):
            widget.currentIndexChanged.connect(self.update_preview)

    def change_filters(self, *_):
        self.capture()
        self.active_semester = self.semester.currentData()
        self.populate()

    def normalize_anchor(self, *_):
        monday = self.anchor.date().addDays(1 - self.anchor.date().dayOfWeek())
        if monday != self.anchor.date():
            self.anchor.blockSignals(True)
            self.anchor.setDate(monday)
            self.anchor.blockSignals(False)
        self.anchor_hint.setText(tr("A : semaine du {first} · B : semaine du {second}", first=qt_locale().toString(monday, "dd MMMM"), second=qt_locale().toString(monday.addDays(7), "dd MMMM")))
        self.data["week_anchor"] = monday.toString("yyyy-MM-dd")

    def update_preview(self, *_):
        if self._loading:
            return
        self.capture()
        archived = {row["id"] for row in self.subject_rows if not row["active"]}
        slots = [row for row in self.data["semesters"][self.active_semester] if row["category"] not in archived]
        self.preview.set_data(slots, self.category_names(), self.subject_colors(), self.week_filter.currentData())

    def add_slot(self):
        active = next((row["id"] for row in self.subject_rows if row["active"]), "autre")
        week = self.week_filter.currentData()
        self._loading = True
        self.append_slot(dict(id=uuid.uuid4().hex, weekday=max(0, self.day_filter.currentData()), start="08:00", end="09:00",
                              category=active, title="", week="all" if week == "any" else week))
        self._loading = False
        self.update_preview()
        self.table.selectRow(self.table.rowCount() - 1)
        self.table.scrollToBottom()

    def remove_slot(self):
        self._loading = True
        for row in sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)
        self._loading = False
        self.update_preview()

    def save(self):
        if self._saving:
            return
        self.save_button.setFocus()
        self.capture()
        try:
            self.subject_rows = self.collect_subjects()
            if self.first_run and (not self._chosen_start or not any(row["active"] for row in self.subject_rows)):
                raise ValueError(tr('Choisis ton point de départ et au moins une matière active.'))
            self._saving = True
            self.save_button.setEnabled(False)
            self.ctx.db.save_setup(self.subject_rows, self.data, schedule_labels=self.schedule_names)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._saving = False
            self.save_button.setEnabled(True)
            self.error.setText(str(exc)); self.error.show()
            return
        self.ctx.mark_changed('subjects', 'timetable')
        self.ctx.notice.emit(tr('Configuration enregistrée. Tes matières et ton emploi du temps sont prêts.'))
        self.accept()
