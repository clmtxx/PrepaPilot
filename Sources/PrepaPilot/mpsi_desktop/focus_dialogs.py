"""Small, explicit setup and journal review for a focus session."""
from __future__ import annotations

import sqlite3

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDateTimeEdit, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QSizePolicy, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)

from .i18n import tr, language, qt_locale

from .catalog import duration_text
from .widgets import AnimatedDialog, button, confirm


ERRORS = (ValueError, OSError, sqlite3.Error)


def _label(text, name="muted"):
    result = QLabel(text)
    result.setObjectName(name)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    return result


def _subjects(ctx, selected=None, *, review=False):
    result = QComboBox()
    result.setAccessibleName(tr("Matière de la séance"))
    result.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    result.setMinimumContentsLength(20)
    result.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    result.addItem(tr("Choisir une matière pour enregistrer") if review else tr("Minuteur libre · sans enregistrement"), None)
    result.addItem(tr("Travail autonome · sans matière"), "permanence")
    for subject in ctx.db.get_subjects(include_archived=False):
        result.addItem(subject["name"], subject["id"])
        result.setItemData(result.count() - 1, QColor(subject["color"]), Qt.ItemDataRole.ForegroundRole)
    index = result.findData(selected)
    result.setCurrentIndex(max(0, index))
    return result


class FocusSetupDialog(AnimatedDialog):
    """Collect options without starting a timer or writing journal entries."""

    def __init__(self, ctx, default_minutes=25, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.values = None
        self.setWindowTitle(tr("Une séance de travail"))
        self.setMinimumWidth(520)
        self.resize(560, 400)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(16)
        outer.addWidget(_label(tr("Un moment pour avancer."), "dialogTitle"))
        outer.addWidget(_label(tr("Choisis ton sujet et ton objectif. Tu valideras le temps à ajouter au journal à la fin.")))
        form = QFormLayout()
        form.setSpacing(14)
        self.category = _subjects(ctx)
        self.minutes = QSpinBox()
        self.minutes.setRange(1, 240)
        self.minutes.setValue(default_minutes)
        self.minutes.setSuffix(" min")
        self.minutes.setAccessibleName(tr("Durée de la séance en minutes"))
        self.title = QLineEdit()
        self.title.setMaxLength(250)
        self.title.setPlaceholderText(tr("Ex. Comprendre le chapitre 3 · facultatif"))
        self.title.setAccessibleName(tr("Objectif facultatif de la séance"))
        form.addRow(tr("Matière"), self.category)
        form.addRow(tr("Durée"), self.minutes)
        form.addRow(tr("Objectif"), self.title)
        outer.addLayout(form)
        self.hint = _label("")
        outer.addWidget(self.hint)
        outer.addStretch()
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button(tr("Annuler"), self.reject))
        self.start_button = button(tr("Commencer"), self.start, primary=True)
        self.start_button.setDefault(True)
        actions.addWidget(self.start_button)
        outer.addLayout(actions)
        self.category.currentIndexChanged.connect(self._update_hint)
        self._update_hint()

    def _update_hint(self, *_):
        self.category.setToolTip(self.category.currentText())
        self.hint.setText(
            tr("Minuteur libre : rien n’est ajouté au journal. Tu pourras choisir une matière à la fin si tu changes d’avis.")
            if self.category.currentData() is None else
            tr("Les pauses ne sont pas comptées. À la fin, tu peux ajuster les horaires, enregistrer ou ignorer la séance.")
        )

    def start(self):
        self.values = dict(category=self.category.currentData(), minutes=self.minutes.value(), title=self.title.text().strip())
        self.accept()


class FocusReviewDialog(AnimatedDialog):
    """Review each work period separately; saving is delegated atomically."""

    def __init__(self, ctx, session, parent=None):
        super().__init__(parent)
        self.ctx, self.session = ctx, session
        self.saved_ids = []
        self.discarded = False
        self._saving = False
        self._resolved = False
        state = session.state
        self.setWindowTitle(tr("Le bilan de ta séance"))
        self.setMinimumWidth(690)
        self.resize(740, 600)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 22)
        outer.setSpacing(10)
        outer.addWidget(_label(tr("Chaque effort compte."), "dialogTitle"))
        description = tr("Vérifie les périodes de travail avant de les ajouter à Gestion du temps. Les pauses restent séparées.")
        if state.get("interrupted"):
            description = tr("La séance a été interrompue. Vérifie les horaires avant de l’enregistrer ; le temps d’absence n’est pas ajouté.")
        elif state.get("category") is None:
            description = tr("Ce minuteur était libre. Tu peux ignorer le bilan, ou choisir une matière pour l’ajouter à Gestion du temps.")
        outer.addWidget(_label(description))
        form = QFormLayout()
        form.setSpacing(10)
        self.category = _subjects(ctx, state.get("category"), review=True)
        self.title = QLineEdit(state.get("title") or "")
        self.title.setMaxLength(250)
        self.title.setPlaceholderText(tr("Séance de travail · objectif facultatif"))
        self.title.setAccessibleName(tr("Nom de la séance dans le journal"))
        form.addRow(tr("Matière"), self.category)
        form.addRow(tr("Activité"), self.title)
        outer.addLayout(form)
        self.table = QTableWidget(0, 3)
        self.table.setAccessibleName(tr("Périodes de travail à enregistrer"))
        self.table.setHorizontalHeaderLabels([tr("Début"), tr("Fin"), tr("Durée")])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 86)
        self.table.verticalHeader().hide()
        # The shared table theme reserves 9 px above and below a cell widget.
        # Keep the date editor tall enough for its own padding and text.
        self.table.verticalHeader().setDefaultSectionSize(64)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setMinimumHeight(140)
        self.table.setAlternatingRowColors(True)
        outer.addWidget(self.table, 1)
        table_actions = QHBoxLayout()
        self.total = _label("", "sectionTitle")
        table_actions.addWidget(self.total, 1)
        self.remove_button = button(tr("Retirer cette période"), self.remove_period)
        self.remove_button.setAccessibleName(tr("Retirer la période sélectionnée du bilan"))
        table_actions.addWidget(self.remove_button)
        outer.addLayout(table_actions)
        self.rounding_hint = _label(tr("Seules les minutes entières de chaque période sont retenues : début arrondi à la minute suivante, fin à la minute précédente. Ajuste les horaires si nécessaire."))
        outer.addWidget(self.rounding_hint)
        self.error = _label("", "error")
        self.error.hide()
        outer.addWidget(self.error)
        actions = QHBoxLayout()
        self.discard_button = button(tr("Ignorer la séance"), self.discard, danger=True)
        actions.addWidget(self.discard_button)
        actions.addStretch()
        self.later_button = button(tr("Plus tard"), self.reject)
        actions.addWidget(self.later_button)
        self.save_button = button(tr("Ajouter au journal"), self.save, primary=True)
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        outer.addLayout(actions)
        self.table.itemSelectionChanged.connect(self._update_totals)
        self.category.currentIndexChanged.connect(self._update_totals)
        self._populate(session.review_entries())

    def _populate(self, segments):
        self.table.setRowCount(len(segments))
        for row, segment in enumerate(segments):
            for column, key in enumerate(("start_at", "end_at")):
                editor = QDateTimeEdit(QDateTime.fromString(segment[key], Qt.DateFormat.ISODate))
                editor.setLocale(qt_locale())
                editor.setCalendarPopup(True)
                editor.setDisplayFormat("d MMM yyyy HH:mm" if language() == "en" else "dd/MM/yyyy HH:mm")
                editor.setAccessibleName(tr("{boundary} de la période {number}", boundary=tr('Début') if column == 0 else tr('Fin'), number=row + 1))
                editor.dateTimeChanged.connect(self._update_totals)
                self.table.setCellWidget(row, column, editor)
            self.table.setItem(row, 2, QTableWidgetItem())
        if segments:
            self.table.selectRow(0)
        self._update_totals()

    def _entries(self):
        return [dict(start_at=self.table.cellWidget(row, 0).dateTime().toString("yyyy-MM-ddTHH:mm"),
                     end_at=self.table.cellWidget(row, 1).dateTime().toString("yyyy-MM-ddTHH:mm"))
                for row in range(self.table.rowCount())]

    def _update_totals(self, *_):
        total, valid = 0, True
        for row in range(self.table.rowCount()):
            start, end = (self.table.cellWidget(row, column) for column in (0, 1))
            item = self.table.item(row, 2)
            if start is None or end is None or item is None:
                continue
            minutes = start.dateTime().secsTo(end.dateTime()) // 60
            valid = valid and minutes > 0
            total += max(0, minutes)
            item.setText(duration_text(minutes) if minutes > 0 else tr("À corriger"))
        self.total.setText(tr("{duration} à enregistrer", duration=duration_text(total)) if self.table.rowCount() else tr("Aucune minute complète"))
        self.remove_button.setEnabled(self.table.currentRow() >= 0 and not self._saving)
        self.save_button.setEnabled(bool(self.category.currentData()) and total > 0 and valid and not self._saving)
        self.category.setToolTip(self.category.currentText())

    def remove_period(self):
        row = self.table.currentRow()
        if row >= 0:
            self.table.removeRow(row)
            self._update_totals()

    def _show_error(self, exc):
        message = str(exc)
        if "chevauche" in message or "overlap" in message:
            message += tr(" Ajuste les horaires ci-dessus, ou choisis Plus tard pour vérifier dans Gestion du temps.")
        self.error.setText(message)
        self.error.show()

    def save(self):
        if self._saving or self._resolved:
            return
        self._saving = True
        self.save_button.setEnabled(False)
        try:
            self.saved_ids = self.session.save(category=self.category.currentData(), title=self.title.text().strip(), segments=self._entries())
        except ERRORS as exc:
            self._saving = False
            self._show_error(exc)
            self._update_totals()
            return
        self._resolved = True
        self.ctx.mark_changed("activities")
        self.ctx.notice.emit(tr("Séance ajoutée à Gestion du temps. Tu peux y modifier chaque période."))
        self.accept()

    def discard(self):
        if self._saving or self._resolved:
            return
        if not confirm(self, tr("Ignorer cette séance ?"), tr("Le bilan sera supprimé sans ajouter de temps au journal. Les activités déjà enregistrées restent conservées.")):
            return
        try:
            self.session.discard()
        except ERRORS as exc:
            self._show_error(exc)
            return
        self.discarded = True
        self._resolved = True
        self.accept()

    def reject(self):
        if self._saving:
            return
        if not self._resolved:
            try:
                self.session.update_review(category=self.category.currentData(), title=self.title.text().strip(), segments=self._entries())
            except ERRORS as exc:
                self._show_error(exc)
                return
        super().reject()
