"""Local grade entry, statistics and a lightweight annual Qt chart."""

from __future__ import annotations

from datetime import date
import hashlib
import math
import sqlite3
from typing import Any
import uuid

from PySide6.QtCore import QDate, QEasingCurve, QLocale, QPointF, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDateEdit, QDialog, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLayout, QLineEdit,
    QScrollArea, QSizePolicy, QSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QToolTip, QVBoxLayout, QWidget,
)

from mpsi_core.grades import stats
from .i18n import tr, language, format_date, qt_locale

from .page_chrome import AccentCard, PageHero, accent_stat_card
from .ui_updates import updating
from .theme import palette_for
from .widgets import (
    AnimatedDialog, animate_table_row, button, clear_layout, confirm,
    motion_enabled, observe_visual_preferences, show_error,
)


def number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    text = f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") if language() == "fr" else text


def score_on_twenty(row: dict[str, Any]) -> float:
    return float(row["score"]) / float(row["scale"]) * 20


def color_icon(value: str) -> QIcon:
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(value))
    painter.drawEllipse(3, 3, 12, 12)
    painter.end()
    return QIcon(pixmap)


def kind_color(kind: str, theme: str) -> str:
    known = {"cours": "blue", "colle": "green", "ds": "orange"}
    if kind in known:
        return palette_for(theme)[known[kind]]
    hue = int.from_bytes(hashlib.sha256(kind.encode("utf-8")).digest()[:2], "big") % 360
    color = QColor.fromHsl(hue, 165, 172 if theme == "dark" else 100)
    if theme != "dark":
        # Keep even yellow hues readable when used for small legend labels.
        def luminance(value):
            channels = [value.redF(), value.greenF(), value.blueF()]
            linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
            return sum(channel * weight for channel, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
        while (1.05 / (luminance(color) + 0.05)) < 4.5:
            color = color.darker(108)
    return color.name()


class SubjectDialog(AnimatedDialog):
    """Create or rename a subject without entering timetable configuration."""

    def __init__(self, ctx, subject=None, parent=None):
        super().__init__(parent)
        self.ctx, self.subject = ctx, subject
        self.saved_id = None
        self._saving = False
        self.color = subject["color"] if subject else "#0071E3"
        self.setWindowTitle(tr("Modifier la matière") if subject else tr("Ajouter une matière"))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(18)
        title = QLabel(self.windowTitle())
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        form = QFormLayout()
        form.setVerticalSpacing(16)
        self.name = QLineEdit(subject["name"] if subject else "")
        self.name.setMaxLength(60)
        self.name.setPlaceholderText(tr("Ex. Biologie, droit, économie…"))
        self.name.setAccessibleName(tr("Nom de la matière"))
        form.addRow(tr("Nom"), self.name)
        self.color_button = button(tr("Choisir une couleur"), self.choose_color)
        self.color_button.setIcon(color_icon(self.color))
        form.addRow(tr("Couleur"), self.color_button)
        layout.addLayout(form)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button(tr("Annuler"), self.reject))
        self.save_button = button(tr("Enregistrer"), self.save, primary=True)
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def choose_color(self):
        value = QColorDialog.getColor(QColor(self.color), self, tr("Couleur de la matière"))
        if value.isValid():
            self.color = value.name().upper()
            self.color_button.setIcon(color_icon(self.color))

    def save(self):
        if self._saving or self.saved_id is not None:
            return
        self._saving = True
        self.save_button.setEnabled(False)
        try:
            subjects = self.ctx.db.get_subjects(include_archived=True)
            if self.subject:
                row = next((item for item in subjects if item["id"] == self.subject["id"]), None)
                if row is None:
                    raise ValueError(tr("Cette matière n’existe plus. Actualise la page avant de réessayer."))
                row.update(name=self.name.text().strip(), color=self.color)
            else:
                row = dict(id="subject_" + uuid.uuid4().hex, name=self.name.text().strip(), color=self.color, active=True)
                subjects.append(row)
            self.ctx.db.save_subjects(subjects)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._saving = False
            self.save_button.setEnabled(True)
            self.error.setText(str(exc))
            self.error.show()
            return
        self.saved_id = row["id"]
        self.ctx.mark_changed('subjects', 'timetable')
        self.ctx.notice.emit(tr("Matière modifiée.") if self.subject else tr("Matière ajoutée."))
        self.accept()


class GradeDialog(AnimatedDialog):
    """Edit all grade fields together, saving only after successful validation."""

    def __init__(self, ctx, subject: str = "maths", grade: dict[str, Any] | None = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.grade = grade
        self.saved_id: int | None = None
        self._saving = False
        self.setWindowTitle(tr("Modifier une note") if grade else tr("Ajouter une note"))
        self.setMinimumWidth(550)
        self.setModal(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(8)
        title = QLabel(self.windowTitle())
        title.setObjectName("dialogTitle")
        layout.addWidget(title)
        subtitle = QLabel(tr("Tous les barèmes sont convertis automatiquement sur 20."))
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        tabs = QHBoxLayout()
        self.detail_buttons = {}
        self.detail_group = QButtonGroup(self)
        self.details_stack = QStackedWidget()
        for index, text in enumerate((tr("Évaluation"), tr("Classe · facultatif"))):
            control = button(tr(text), lambda checked=False, i=index: self._show_details(i))
            control.setCheckable(True)
            control.setAutoDefault(False)
            control.setProperty("role", "tab")
            self.detail_group.addButton(control, index)
            self.detail_buttons[index] = control
            tabs.addWidget(control)
        tabs.addStretch()
        layout.addLayout(tabs)
        evaluation = QWidget()
        form = QFormLayout(evaluation)
        form.setContentsMargins(0, 0, 0, 0)
        form.setVerticalSpacing(10)
        form.setHorizontalSpacing(22)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.subject = QComboBox()
        self.subject.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.subject.setMinimumContentsLength(18)
        self.subject.setAccessibleName(tr("Matière de l’évaluation"))
        for row in ctx.db.get_subjects(include_archived=True):
            if row["active"] or (grade and row["id"] == grade["subject"]):
                label = row["name"] + (tr(" (archivée)") if not row["active"] else "")
                self.subject.addItem(color_icon(row["color"]), label, row["id"])
        selected = self.subject.findData(grade["subject"] if grade else subject)
        self.subject.setCurrentIndex(max(0, selected) if self.subject.count() else -1)
        form.addRow(tr("Matière"), self.subject)
        self.kind = QComboBox()
        self.kind.setEditable(True)
        self.kind.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.kind.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.kind.setMinimumContentsLength(18)
        self.kind.lineEdit().setMaxLength(60)
        self.kind.lineEdit().setPlaceholderText(tr("Choisir ou saisir un type"))
        self.kind.setAccessibleName(tr("Type d’évaluation, choix ou texte libre"))
        form.addRow(tr("Type d’évaluation"), self.kind)
        self._update_kinds()
        if grade:
            index = self.kind.findData(grade["kind"])
            if index < 0:
                self.kind.addItem(grade["kind"], grade["kind"])
                index = self.kind.count() - 1
            self.kind.setCurrentIndex(index)

        self.score = self._spin(0, 1_000_000, 0, tr("Note obtenue"))
        self.scale = self._spin(0.001, 1_000_000, 20, tr("Barème"))
        score_line = QHBoxLayout()
        score_line.addWidget(self.score, 1)
        slash = QLabel(tr("sur"))
        slash.setObjectName("muted")
        score_line.addWidget(slash)
        score_line.addWidget(self.scale, 1)
        form.addRow(tr("Note / barème"), score_line)
        self.coefficient = self._spin(0.001, 10000, 1, tr("Coefficient de la note"))
        self.coefficient.setSingleStep(0.5)
        form.addRow(tr("Coefficient"), self.coefficient)

        self.graded_on = QDateEdit()
        self.graded_on.setLocale(qt_locale())
        self.graded_on.setCalendarPopup(True)
        self.graded_on.setDisplayFormat("d MMM yyyy" if language() == "en" else "dd/MM/yyyy")
        self.graded_on.setMaximumDate(QDate.currentDate())
        self.graded_on.setDate(QDate.currentDate())
        self.graded_on.setAccessibleName(tr("Date de l’évaluation"))
        form.addRow(tr("Date"), self.graded_on)
        self.label = QLineEdit()
        self.label.setPlaceholderText(tr("Ex. Projet de groupe · facultatif"))
        self.label.setMaxLength(240)
        self.label.setAccessibleName(tr("Nom de l’évaluation"))
        form.addRow(tr("Nom de l’évaluation"), self.label)
        self.details_stack.addWidget(evaluation)

        comparison = QWidget()
        comparison_layout = QVBoxLayout(comparison)
        comparison_layout.setContentsMargins(0, 4, 0, 0)
        comparison_layout.setSpacing(12)
        help_text = QLabel(tr("Renseigne uniquement ce que tu connais. Ces repères ne changent pas ta moyenne personnelle."))
        help_text.setObjectName("muted")
        help_text.setWordWrap(True)
        comparison_layout.addWidget(help_text)
        self.class_average_enabled = QCheckBox(tr("Je connais la moyenne de la classe"))
        comparison_layout.addWidget(self.class_average_enabled)
        average_line = QHBoxLayout()
        self.class_average = self._spin(-1, 1_000_000, -1, tr("Moyenne de la classe sur le barème de l’évaluation"))
        self.class_average.setSpecialValueText("—")
        self.class_average.setEnabled(False)
        average_line.addWidget(self.class_average, 1)
        self.class_scale_label = QLabel()
        self.class_scale_label.setObjectName("muted")
        average_line.addWidget(self.class_scale_label)
        comparison_layout.addLayout(average_line)
        self.rank_enabled = QCheckBox(tr("Je connais mon classement"))
        comparison_layout.addWidget(self.rank_enabled)
        rank_line = QHBoxLayout()
        self.rank = QSpinBox()
        self.class_size = QSpinBox()
        for spin, name in ((self.rank, tr("Position dans la classe")), (self.class_size, tr("Effectif de la classe"))):
            spin.setRange(0, 2_147_483_647)
            spin.setSpecialValueText("—")
            spin.setAccessibleName(tr(name))
            spin.setEnabled(False)
        rank_line.addWidget(self.rank, 1)
        rank_line.addWidget(QLabel(tr("sur")))
        rank_line.addWidget(self.class_size, 1)
        comparison_layout.addLayout(rank_line)
        rank_hint = QLabel(tr("Position / effectif, par exemple 5 sur 32. La première place correspond à 1."))
        rank_hint.setObjectName("muted")
        rank_hint.setWordWrap(True)
        comparison_layout.addWidget(rank_hint)
        comparison_layout.addStretch()
        self.details_stack.addWidget(comparison)
        layout.addWidget(self.details_stack)
        self.class_average_enabled.toggled.connect(self.class_average.setEnabled)
        self.rank_enabled.toggled.connect(self.rank.setEnabled)
        self.rank_enabled.toggled.connect(self.class_size.setEnabled)
        self._show_details(0)

        if grade:
            self.score.setValue(grade["score"])
            self.scale.setValue(grade["scale"])
            self.coefficient.setValue(grade.get("coefficient", 1))
            self.graded_on.setDate(QDate.fromString(grade["graded_on"], "yyyy-MM-dd"))
            self.label.setText(grade.get("label", ""))
            self.label.setCursorPosition(0)
            if grade.get("class_average") is not None:
                self.class_average_enabled.setChecked(True)
                self.class_average.setValue(grade["class_average"])
            if grade.get("rank") is not None:
                self.rank_enabled.setChecked(True)
                self.rank.setValue(grade["rank"])
                self.class_size.setValue(grade["class_size"])

        self.preview = QLabel()
        self.preview.setObjectName("GradePreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(48)
        self.preview.setStyleSheet("font-size: 21px; font-weight: 650; padding: 8px;")
        layout.addWidget(self.preview)
        self.year_hint = QLabel()
        self.year_hint.setObjectName("muted")
        self.year_hint.setWordWrap(True)
        layout.addWidget(self.year_hint)
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setStyleSheet("color: #e45c69;")
        self.error.setWordWrap(True)
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.hide()
        layout.addWidget(self.error)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button(tr("Annuler"), self.reject))
        self.save_button = button(tr("Enregistrer"), self.save, primary=True)
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)
        self.score.valueChanged.connect(self._update_preview)
        self.scale.valueChanged.connect(self._update_preview)
        self.graded_on.dateChanged.connect(self._update_preview)
        self._update_preview()

    def _show_details(self, index):
        self.details_stack.setCurrentIndex(index)
        self.detail_buttons[index].setChecked(True)

    @staticmethod
    def _spin(minimum: float, maximum: float, value: float, accessible_name: str) -> QDoubleSpinBox:
        class CompactSpinBox(QDoubleSpinBox):
            def textFromValue(self, amount):
                return number(amount, 3)

        spin = CompactSpinBox()
        spin.setLocale(qt_locale())
        spin.setDecimals(3)
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSingleStep(0.5)
        spin.setAccessibleName(tr(accessible_name))
        return spin

    def _update_kinds(self):
        previous = self.kind.currentText()
        self.kind.clear()
        for key, label in self.ctx.db.grade_kind_labels().items():
            self.kind.addItem(tr(label), key)
        if previous:
            self.kind.setCurrentText(previous)

    def selected_kind(self):
        text = self.kind.currentText().strip()
        index = self.kind.findText(text, Qt.MatchFlag.MatchFixedString)
        return self.kind.itemData(index) if index >= 0 else text

    def _update_preview(self):
        score, scale = self.score.value(), self.scale.value()
        self.class_scale_label.setText(tr("sur {scale} · même barème", scale=number(scale)))
        if score > scale:
            self.preview.setText(tr("La note dépasse le barème"))
        else:
            self.preview.setText(f"{number(score)} / {number(scale)}   →   {number(score / scale * 20)} / 20")
        grade_date = self.graded_on.date().toString("yyyy-MM-dd")
        start, end = f"{self.ctx.year}-08-01", f"{self.ctx.year + 1}-08-01"
        outside_year = not start <= grade_date < end
        self.year_hint.setText(
            tr("Cette date est hors de l’année affichée. Tu retrouveras la note en changeant l’année en haut de l’application.")
            if outside_year else tr("Coefficient 1 par défaut. La moyenne reste indicative.")
        )

    def save(self):
        if self._saving or self.saved_id is not None:
            return
        if not self.subject.currentData():
            self.error.setText(tr("Ajoute d’abord une matière depuis la page Notes."))
            self.error.show()
            return
        kind = self.selected_kind()
        if not kind or len(kind) > 60:
            self.error.setText(tr("Indique un type d’évaluation de 1 à 60 caractères."))
            self.error.show()
            self._show_details(0)
            self.kind.setFocus()
            return
        # interpretText commits text still being edited before validating the fields.
        for spin in (self.score, self.scale, self.coefficient, self.class_average, self.rank, self.class_size):
            spin.interpretText()
        if self.score.value() > self.scale.value():
            self.error.setText(tr("La note doit être comprise entre 0 et le barème."))
            self.error.show()
            self._show_details(0)
            self.score.setFocus()
            return
        if self.class_average_enabled.isChecked() and not 0 <= self.class_average.value() <= self.scale.value():
            self.error.setText(tr("Indique une moyenne de classe comprise entre 0 et le barème, ou décoche cette option."))
            self.error.show()
            self._show_details(1)
            self.class_average.setFocus()
            return
        if self.rank_enabled.isChecked() and not 1 <= self.rank.value() <= self.class_size.value():
            self.error.setText(tr("Indique une position et un effectif : de 1 à l’effectif de la classe, ou décoche cette option."))
            self.error.show()
            self._show_details(1)
            (self.class_size if not self.class_size.value() else self.rank).setFocus()
            return
        payload = dict(
            subject=self.subject.currentData(), kind=kind,
            score=self.score.value(), scale=self.scale.value(),
            graded_on=self.graded_on.date().toString("yyyy-MM-dd"),
            label=self.label.text().strip(), coefficient=self.coefficient.value(),
            class_average=self.class_average.value() if self.class_average_enabled.isChecked() else None,
            rank=self.rank.value() if self.rank_enabled.isChecked() else None,
            class_size=self.class_size.value() if self.rank_enabled.isChecked() else None,
        )
        self._saving = True
        self.save_button.setEnabled(False)
        self.save_button.setText(tr("Enregistrement…"))
        self.error.hide()
        try:
            if self.grade:
                if not self.ctx.db.update_grade(self.grade["id"], **payload):
                    raise ValueError(tr("Cette note n’existe plus. Ferme cette fenêtre et actualise la liste."))
                self.saved_id = self.grade["id"]
            else:
                self.saved_id = self.ctx.db.add_grade(**payload)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._saving = False
            self.save_button.setEnabled(True)
            self.save_button.setText(tr("Enregistrer"))
            self.error.setText(str(exc))
            self.error.show()
            return
        self.ctx.mark_changed('grades')
        self.ctx.notice.emit(tr("Note modifiée.") if self.grade else tr("Note enregistrée."))
        self.accept()


def class_average_color(theme: str) -> str:
    """A readable comparison color, also distinguished by dashes and diamonds."""
    return "#C4A7FF" if theme == "dark" else "#7650B5"


class GradeChart(QWidget):
    """Cached annual grade, class-average and optional ranking charts."""

    MONTHS = ("Août", "Sept.", "Oct.", "Nov.", "Déc.", "Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.")

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.rows: list[dict[str, Any]] = []
        self.kind_labels = {}
        self._all_hit_points: list[tuple[QPointF, dict[str, Any]]] = []
        self._point_buckets = {}
        self._series = {}
        self._class_series = []
        self._ranking_series = []
        self._rank_limit = 2
        self.mode = "grades"
        self._cache_key = None
        self._axes_layer = self._curves_layer = None
        self._motion_allowed = True
        self._year = ctx.year
        self._reveal = 1.0
        self._pending_reveal = False
        self.reveal_animation = QVariantAnimation(self)
        self.reveal_animation.setDuration(650)
        self.reveal_animation.setStartValue(0.0)
        self.reveal_animation.setEndValue(1.0)
        self.reveal_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.reveal_animation.valueChanged.connect(self._set_reveal)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("Évolution annuelle des notes, de zéro à vingt"))
        ctx.theme_changed.connect(self._theme_updated)
        observe_visual_preferences(self)

    def set_grades(self, rows):
        self.kind_labels = self.ctx.db.grade_kind_labels()
        ordered = sorted(rows, key=lambda row: (row["graded_on"], row.get("id", 0)))
        year = self.ctx.year
        changed = ordered != self.rows or self._year != year
        self._year = year
        if changed:
            # Keep a snapshot: an edited caller-owned row must invalidate the
            # scene even when the list itself has not been replaced.
            self.rows = [dict(row) for row in ordered]
            self._series = {}
            self._class_series = []
            self._ranking_series = []
            for row in self.rows:
                when = date.fromisoformat(row['graded_on'])
                self._series.setdefault(row['kind'], []).append(
                    (when, score_on_twenty(row), row))
                if row.get('class_average') is not None:
                    average = float(row['class_average']) / float(row['scale']) * 20
                    self._class_series.append((when, average, dict(row, _chart_value='class_average')))
                if row.get('rank') is not None and row.get('class_size') is not None:
                    self._ranking_series.append((when, int(row['rank']), dict(row, _chart_value='ranking')))
            self._rank_limit = max((int(row['class_size']) for _, _, row in self._ranking_series), default=2)
            self._reset_scene()
        self._describe_chart()
        self.update()

    def set_mode(self, mode: str):
        if mode not in ('grades', 'ranking'):
            raise ValueError(tr("Le graphique doit afficher les notes ou le classement."))
        if self.mode == mode:
            return
        self.mode = mode
        self._describe_chart()
        self._reset_scene()
        QToolTip.hideText()
        self.unsetCursor()
        self.update()

    def _describe_chart(self):
        if self.mode == 'ranking':
            self.setAccessibleName(tr("Évolution annuelle du classement dans la classe"))
            summary = tr("{count} classements renseignés. Le premier rang est en haut.", count=len(self._ranking_series))
        else:
            self.setAccessibleName(tr("Évolution annuelle des notes et de la moyenne de classe, de zéro à vingt"))
            summary = tr("{grades} notes et {averages} moyennes de classe renseignées.", grades=len(self.rows), averages=len(self._class_series))
        self.setAccessibleDescription(
            tr("{summary} Année {start}–{end}. Les valeurs détaillées sont accessibles dans le tableau historique.",
               summary=summary, start=self._year, end=self._year + 1)
        )

    def _reset_scene(self):
        self._cache_key = None
        self.reveal_animation.stop()
        has_points = bool(self._ranking_series if self.mode == 'ranking' else self.rows)
        self._pending_reveal = has_points and motion_enabled(self.ctx)
        self._reveal = 1.0
        self._all_hit_points = []
        self._point_buckets = {}
        if self.isVisible():
            self._start_reveal()

    def _start_reveal(self):
        self._motion_allowed = motion_enabled(self.ctx)
        if self._pending_reveal and self._motion_allowed and not self.window().isMinimized():
            self._pending_reveal = False
            self._reveal = 0.0
            self.reveal_animation.start()
        else:
            self._pending_reveal = False
            self._reveal = 1.0

    def _set_reveal(self, value):
        # Preferences are read at animation start; the shared observer handles
        # live changes without a SQLite lookup on each frame.
        if not self._motion_allowed or not motion_enabled() or not self.isVisible() or self.window().isMinimized():
            self._reset_motion()
        else:
            self._reveal = float(value)
        self.update()

    def _reset_motion(self):
        self.reveal_animation.stop()
        self._pending_reveal = False
        self._reveal = 1.0
        self.update()

    def _theme_updated(self, *_):
        self.update()

    def showEvent(self, event):
        super().showEvent(event)
        self._start_reveal()

    def hideEvent(self, event):
        self._reset_motion()
        QToolTip.hideText()
        self.unsetCursor()
        super().hideEvent(event)

    def _axis(self):
        left = max(39, 16 + len(str(self._rank_limit)) * 8) if self.mode == 'ranking' else 39
        return QRectF(left, 14, max(1, self.width() - left - 16), max(1, self.height() - 45))

    def _value_y(self, value, axis):
        if self.mode == 'ranking':
            return axis.top() + (value - 1) / max(1, self._rank_limit - 1) * axis.height()
        return axis.bottom() - value / 20 * axis.height()

    def _axis_values(self):
        if self.mode == 'ranking':
            return sorted({1 + round((self._rank_limit - 1) * index / 4) for index in range(5)})
        return range(0, 21, 5)

    def _reveal_right(self):
        axis = self._axis()
        return axis.left() - 6 + (axis.width() + 12) * self._reveal

    @property
    def _hit_points(self):
        # Retain the existing inspection contract without rebuilding this list
        # during every paint of the reveal animation.
        if self._reveal >= 1:
            return self._all_hit_points
        right = self._reveal_right()
        return [(point, row) for point, row in self._all_hit_points if point.x() <= right]

    def _ensure_scene(self):
        ratio = self.devicePixelRatioF()
        key = (self.width(), self.height(), ratio, self.ctx.theme, self.font().toString(), self.mode)
        if key == self._cache_key:
            return
        layers = []
        for draw in (self._paint_axes, self._paint_curves):
            layer = QPixmap(max(1, math.ceil(self.width() * ratio)), max(1, math.ceil(self.height() * ratio)))
            layer.setDevicePixelRatio(ratio)
            layer.fill(Qt.GlobalColor.transparent)
            painter = QPainter(layer)
            try:
                draw(painter)
            finally:
                painter.end()
            layers.append(layer)
        self._axes_layer, self._curves_layer = layers
        self._cache_key = key

    def paintEvent(self, event):
        self._ensure_scene()
        painter = QPainter(self)
        try:
            painter.drawPixmap(0, 0, self._axes_layer)
            axis = self._axis()
            painter.setClipRect(QRectF(axis.left() - 6, axis.top() - 6,
                                      (axis.width() + 12) * self._reveal, axis.height() + 12))
            painter.drawPixmap(0, 0, self._curves_layer)
        finally:
            painter.end()

    def _paint_axes(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = palette_for(self.ctx.theme)
        axis = self._axis()
        muted, border = QColor(colors["muted"]), QColor(colors["border"])
        label_font = QFont(self.font())
        label_font.setPointSizeF(8.5)
        p.setFont(label_font)
        for value in self._axis_values():
            y = self._value_y(value, axis)
            p.setPen(QPen(border, 1, Qt.PenStyle.DashLine if value != 0 else Qt.PenStyle.SolidLine))
            p.drawLine(QPointF(axis.left(), y), QPointF(axis.right(), y))
            p.setPen(muted)
            p.drawText(QRectF(0, y - 9, axis.left() - 10, 18), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, str(value))

        start = date(self._year, 8, 1)
        end = date(self._year + 1, 8, 1)
        days = (end - start).days

        def x_position(day: date):
            return axis.left() + (day - start).days / days * axis.width()

        p.setPen(muted)
        for i, month in enumerate(self.MONTHS):
            if axis.width() < 540 and i % 2:
                continue
            when = date(self._year if i < 5 else self._year + 1, ((i + 7) % 12) + 1, 1)
            x = x_position(when)
            if language() == "en":
                month = qt_locale().monthName(when.month, QLocale.FormatType.ShortFormat)
            p.drawText(QRectF(x - 22, axis.bottom() + 10, 44, 20), Qt.AlignmentFlag.AlignCenter, month)

        if not (self._ranking_series if self.mode == 'ranking' else self.rows):
            # A quiet empty state retains the annual axes and never fabricates data.
            text = tr("Ton classement, à ton rythme") if self.mode == 'ranking' else tr("Ta progression commence ici")
            details = (tr("Renseigne un classement facultatif dans une note.")
                       if self.mode == 'ranking' else tr("Ajoute une première note pour dessiner ton année."))
            panel_width = min(380, axis.width())
            panel = QRectF(axis.center().x() - panel_width / 2, axis.center().y() - 36, panel_width, 76)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(colors["surface"]))
            p.drawRoundedRect(panel, 12, 12)
            font = QFont(self.font())
            font.setPointSizeF(11)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            p.setPen(QColor(colors["text"]))
            p.drawText(panel.adjusted(0, 8, 0, -35), Qt.AlignmentFlag.AlignCenter, text)
            p.setFont(label_font)
            p.setPen(muted)
            p.drawText(panel.adjusted(6, 35, -6, -7), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, details)

    def _paint_curves(self, p):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        axis = self._axis()
        start = date(self._year, 8, 1)
        days = (date(self._year + 1, 8, 1) - start).days
        surface = QColor(palette_for(self.ctx.theme)['surface'])
        self._all_hit_points = []
        self._point_buckets = {}
        if self.mode == 'ranking':
            groups = [(self._ranking_series, palette_for(self.ctx.theme)['accent'], False)]
        else:
            groups = [(self._series[kind], kind_color(kind, self.ctx.theme), False) for kind in sorted(self._series)]
            if self._class_series:
                groups.append((self._class_series, class_average_color(self.ctx.theme), True))
        for group, color_value, comparison in groups:
            if not group:
                continue
            color = QColor(color_value)
            points = [QPointF(axis.left() + (day - start).days / days * axis.width(),
                             self._value_y(score, axis)) for day, score, _ in group]
            path = QPainterPath(points[0])
            for point in points[1:]:
                path.lineTo(point)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(color, 2.5, Qt.PenStyle.DashLine if comparison else Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawPath(path)
            p.setBrush(surface)
            p.setPen(QPen(color, 2.5))
            for point, (_, _, row) in zip(points, group):
                if comparison:
                    diamond = QPainterPath(QPointF(point.x(), point.y() - 5))
                    diamond.lineTo(point.x() + 5, point.y())
                    diamond.lineTo(point.x(), point.y() + 5)
                    diamond.lineTo(point.x() - 5, point.y())
                    diamond.closeSubpath()
                    p.drawPath(diamond)
                else:
                    p.drawEllipse(point, 4.3, 4.3)
                index = len(self._all_hit_points)
                self._all_hit_points.append((point, row))
                bucket = (math.floor(point.x() / 16), math.floor(point.y() / 16))
                self._point_buckets.setdefault(bucket, []).append((index, point, row))

    def _nearest(self, position):
        right = self._reveal_right()
        column, line = math.floor(position.x() / 16), math.floor(position.y() / 16)
        nearest = None
        distance = 15 ** 2
        for x in range(column - 1, column + 2):
            for y in range(line - 1, line + 2):
                for index, point, row in self._point_buckets.get((x, y), ()):
                    if point.x() > right:
                        continue
                    value = (point.x() - position.x()) ** 2 + (point.y() - position.y()) ** 2
                    if value < distance or (nearest is not None and value == distance and index < nearest[0]):
                        nearest = (index, row)
                        distance = value
        return nearest[1] if nearest else None

    def _tooltip(self, row):
        when = format_date(row['graded_on'])
        caption = f"{tr(self.kind_labels.get(row['kind'], row['kind']))} · {when}\n"
        if row.get('_chart_value') == 'ranking':
            caption += tr("Classement : {rank}/{size}", rank=row['rank'], size=row['class_size'])
        elif row.get('_chart_value') == 'class_average':
            value = float(row['class_average']) / float(row['scale']) * 20
            caption += tr("Moyenne de classe : {average}/{scale} → {value}/20", average=number(row['class_average']), scale=number(row['scale']), value=number(value))
        else:
            caption += tr("Ta note : {score}/{scale} → {value}/20", score=number(row['score']), scale=number(row['scale']), value=number(score_on_twenty(row)))
            # Equal marks may occupy the same pixel. Include the comparison
            # here as well so neither datum becomes inaccessible on hover.
            if row.get('class_average') is not None:
                value = float(row['class_average']) / float(row['scale']) * 20
                caption += tr("\nMoyenne de classe : {average}/{scale} → {value}/20", average=number(row['class_average']), scale=number(row['scale']), value=number(value))
        if row.get('label'):
            caption += f"\n{row['label']}"
        return caption

    def mouseMoveEvent(self, event):
        position = event.position()
        row = self._nearest(position)
        if row is not None:
            QToolTip.showText(event.globalPosition().toPoint(), self._tooltip(row), self)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            QToolTip.hideText()
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        self.unsetCursor()
        super().leaveEvent(event)


class NotesPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.subject = "maths"
        self.rows: list[dict[str, Any]] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.add_button = button(tr("+  Ajouter une note"), self.add_note, primary=True)
        self.hero = PageHero(
            ctx, "notes", tr("RÉSULTATS"), tr("Notes et évaluations"),
            tr("Moyennes, classements et historique de tes évaluations."),
            actions=[self.add_button],
        )
        layout.addWidget(self.hero)
        self.subject_tools = QWidget()
        tools = QHBoxLayout(self.subject_tools)
        tools.setContentsMargins(0, 0, 0, 0)
        tools.setSpacing(10)
        self.subject_selector = QComboBox()
        self.subject_selector.setAccessibleName(tr("Matière affichée"))
        self.subject_selector.setMinimumContentsLength(18)
        self.subject_selector.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.subject_selector.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.subject_selector.setMaxVisibleItems(12)
        self.subject_selector.currentIndexChanged.connect(self._subject_changed)
        tools.addWidget(self.subject_selector, 1)
        self.subject_add_button = button(tr("+ Matière"), self.add_subject)
        self.subject_add_button.setAccessibleName(tr("Ajouter une matière"))
        tools.addWidget(self.subject_add_button)
        self.subject_edit_button = button(tr("Modifier la matière"), self.edit_subject)
        tools.addWidget(self.subject_edit_button)
        layout.addWidget(self.subject_tools)
        self.year_label = QLabel()
        self.year_label.setObjectName("colorEyebrow")

        self.empty_profile = AccentCard(ctx, "notes")
        empty_title = QLabel(tr("Tes matières, tes progrès."))
        empty_title.setObjectName("sectionTitle")
        self.empty_profile.body.addWidget(empty_title)
        empty_text = QLabel(tr("Ajoute une première matière pour commencer à suivre tes notes."))
        empty_text.setObjectName("muted")
        empty_text.setWordWrap(True)
        self.empty_profile.body.addWidget(empty_text)
        self.empty_add_button = button(tr("Ajouter une matière"), self.add_subject, primary=True)
        self.empty_profile.body.addWidget(self.empty_add_button, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.empty_profile)

        self.stats_widget = QWidget()
        self.stats_layout = QHBoxLayout(self.stats_widget)
        self.stats_layout.setContentsMargins(0, 0, 0, 0)
        self.stats_layout.setSpacing(18)
        self.mean_stat = accent_stat_card(ctx, 'notes', tr('Moyenne indicative'), '—', tr('Chaque nouvelle note compte'))
        self.best_stat = accent_stat_card(ctx, 'documents', tr('Meilleure note'), '—', tr('Chaque nouvelle note compte'))
        self.trend_stat = accent_stat_card(ctx, 'home', tr('Progression récente'), '—', tr('Disponible à partir de 6 notes'))
        for card in (self.mean_stat, self.best_stat, self.trend_stat):
            self.stats_layout.addWidget(card)
        self._render_state = None
        layout.addWidget(self.stats_widget)

        chart_card = self.chart_card = AccentCard(ctx, "notes")
        chart_header = QHBoxLayout()
        chart_title = QLabel(tr("L’année en perspective"))
        chart_title.setObjectName("sectionTitle")
        chart_header.addWidget(chart_title)
        chart_header.addStretch()
        chart_header.addWidget(self.year_label)
        chart_card.body.addLayout(chart_header)
        chart_modes = QHBoxLayout()
        self.chart_mode_group = QButtonGroup(self)
        self.chart_mode_buttons = {}
        for mode, text in (("grades", tr("Notes et moyenne de classe")), ("ranking", tr("Classement"))):
            control = button(text, lambda checked=False, m=mode: self.set_chart_mode(m))
            control.setCheckable(True)
            control.setProperty("role", "tab")
            control.setAccessibleName(tr("Afficher le graphique : {label}", label=text))
            self.chart_mode_group.addButton(control)
            self.chart_mode_buttons[mode] = control
            chart_modes.addWidget(control)
        self.chart_mode_buttons["grades"].setChecked(True)
        chart_modes.addStretch()
        chart_card.body.addLayout(chart_modes)
        self.legend_scroll = QScrollArea()
        self.legend_scroll.setWidgetResizable(True)
        self.legend_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.legend_scroll.setFixedHeight(42)
        self.legend_scroll.setAccessibleName(tr("Légende des types d’évaluation"))
        legend_content = QWidget()
        self.legend = QHBoxLayout(legend_content)
        self.legend.setContentsMargins(0, 0, 0, 4)
        self.legend.setSpacing(18)
        self.legend_scroll.setWidget(legend_content)
        chart_card.body.addWidget(self.legend_scroll)
        self.chart = GradeChart(ctx)
        chart_card.body.addWidget(self.chart, 1)
        self.details_label = QLabel()
        self.details_label.setObjectName("muted")
        self.details_label.setWordWrap(True)
        self.details_label.setTextFormat(Qt.TextFormat.PlainText)
        chart_card.body.addWidget(self.details_label)
        layout.addWidget(chart_card, 2)

        history = self.history_card = AccentCard(ctx, "home")
        history_header = QHBoxLayout()
        self.history_title = QLabel(tr("Historique"))
        self.history_title.setObjectName("sectionTitle")
        history_header.addWidget(self.history_title)
        history_header.addStretch()
        self.edit_button = button(tr("Modifier"), self.edit_note)
        self.delete_button = button(tr("Supprimer"), self.delete_note, danger=True)
        self.edit_button.setEnabled(False)
        self.delete_button.setEnabled(False)
        history_header.addWidget(self.edit_button)
        history_header.addWidget(self.delete_button)
        history.body.addLayout(history_header)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels([tr("Date"), tr("Type"), tr("Nom de l’évaluation"), tr("Note"), tr("Sur 20"), tr("Coef."), tr("Classe /20"), tr("Rang")])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(50)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(False)
        self.table.setMinimumHeight(165)
        self.table.setAccessibleName(tr("Historique des notes"))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 155)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self._selection_changed)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_note())
        history.body.addWidget(self.table)
        self.empty_history = QLabel(tr("Aucune note pour cette matière et cette année."))
        self.empty_history.setObjectName("muted")
        self.empty_history.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_history.setMinimumHeight(75)
        history.body.addWidget(self.empty_history)
        layout.addWidget(history, 1)
        ctx.watch_data(self.refresh, 'grades', 'subjects', 'year')
        ctx.theme_changed.connect(self._theme_updated)
        self.refresh()

    def set_subject(self, subject):
        self.subject = subject
        self.refresh()

    def _subject_changed(self, index):
        if index >= 0:
            self.set_subject(self.subject_selector.itemData(index))

    def _refresh_subjects(self):
        subjects = self.ctx.db.get_subjects(include_archived=True)
        recorded = {row["subject"] for row in self.ctx.db._rows('SELECT DISTINCT subject FROM grades')}
        choices = [row for row in subjects if row["active"] or row["id"] in recorded]
        self.subject_selector.blockSignals(True)
        self.subject_selector.clear()
        for row in choices:
            title = row["name"] + (tr(" (archivée)") if not row["active"] else "")
            self.subject_selector.addItem(color_icon(row["color"]), title, row["id"])
        index = self.subject_selector.findData(self.subject)
        self.subject_selector.setCurrentIndex(max(0, index) if choices else -1)
        self.subject = self.subject_selector.currentData()
        self.subject_selector.blockSignals(False)
        self.subject_selector.setToolTip(self.subject_selector.currentText())
        self.subject_tools.setVisible(bool(choices))
        self.subject_edit_button.setEnabled(bool(choices))
        self.add_button.setEnabled(any(row["active"] for row in subjects))
        self.empty_profile.setVisible(not choices)
        for widget in (self.stats_widget, self.chart_card, self.history_card):
            widget.setVisible(bool(choices))

    def add_subject(self):
        dialog = SubjectDialog(self.ctx, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_subject(dialog.saved_id)
            return dialog.saved_id
        return None

    def edit_subject(self):
        subject = next((row for row in self.ctx.db.get_subjects(include_archived=True) if row["id"] == self.subject), None)
        if subject:
            dialog = SubjectDialog(self.ctx, subject=subject, parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self.set_subject(dialog.saved_id)

    def _theme_updated(self, *_):
        self._refresh_legend()
        self._refresh_table_colors()

    def set_chart_mode(self, mode):
        self.chart.set_mode(mode)
        self.chart_mode_buttons[self.chart.mode].setChecked(True)
        self._refresh_legend()
        self._refresh_details()

    def _refresh_legend(self):
        clear_layout(self.legend)
        if self.chart.mode == "ranking":
            legend = QLabel(tr("●  Ma position dans la classe"))
            legend.setStyleSheet(f"color: {palette_for(self.ctx.theme)['accent']}; font-size: 11px;")
            self.legend.addWidget(legend)
            self.legend.addStretch()
            self.legend_scroll.setVisible(any(row.get("rank") is not None for row in self.rows))
            return
        labels = self.ctx.db.grade_kind_labels()
        for kind in sorted({row["kind"] for row in self.rows}, key=lambda key: labels.get(key, key).casefold()):
            title = tr(labels.get(kind, kind))
            legend = QLabel(f"●  {title}")
            legend.setTextFormat(Qt.TextFormat.PlainText)
            legend.setStyleSheet(f"color: {kind_color(kind, self.ctx.theme)}; font-size: 11px;")
            self.legend.addWidget(legend)
        if any(row.get("class_average") is not None for row in self.rows):
            legend = QLabel(tr("◆  Moyenne de la classe · pointillés"))
            legend.setStyleSheet(f"color: {class_average_color(self.ctx.theme)}; font-size: 11px;")
            self.legend.addWidget(legend)
        self.legend.addStretch()
        self.legend_scroll.setVisible(bool(self.rows))

    def _refresh_details(self, result=None, labels=None):
        if self.chart.mode == "ranking":
            count = sum(row.get("rank") is not None for row in self.rows)
            self.details_label.setText(
                tr("{count} classement renseigné sur {total} évaluations. La première place est en haut. Survole un point pour voir la position et l’effectif (x / y). L’effectif peut varier selon l’évaluation."
                   if count == 1 else "{count} classements renseignés sur {total} évaluations. La première place est en haut. Survole un point pour voir la position et l’effectif (x / y). L’effectif peut varier selon l’évaluation.",
                   count=count, total=len(self.rows))
                if count else tr("Le classement est facultatif. Ajoute-le ou complète une note dans l’onglet Classe de son formulaire.")
            )
            return
        result = result if result is not None else stats(self.rows)
        labels = labels if labels is not None else self.ctx.db.grade_kind_labels()
        details = [f"{tr(labels.get(kind, kind))} : {number(values['weighted_mean'])}/20"
                   for kind, values in result["by_kind"].items()]
        if details:
            details.append(tr("Minimum : {value}/20", value=number(result['min'])))
        if any(row.get("class_average") is not None for row in self.rows):
            details.append(tr("Moyenne de classe en pointillés, sur 20 · valeurs renseignées uniquement"))
        self.details_label.setText("     ·     ".join(details) if details else tr("Barèmes libres, un même repère sur 20. Les notes sont conservées sur ton PC."))

    def _refresh_table_colors(self):
        for index, row in enumerate(self.rows):
            if self.table.item(index, 4):
                self.table.item(index, 4).setForeground(QColor(kind_color(row["kind"], self.ctx.theme)))
            if self.table.item(index, 6):
                self.table.item(index, 6).setForeground(QColor(class_average_color(self.ctx.theme)))

    def refresh(self):
        selected_id = self.selected_grade()["id"] if self.selected_grade() else None
        self._refresh_subjects()
        self.rows = sorted(self.ctx.grades(self.subject), key=lambda row: (row["graded_on"], row["id"]), reverse=True) if self.subject else []
        labels = self.ctx.db.grade_kind_labels()
        self.year_label.setText(f"{self.ctx.year} – {self.ctx.year + 1}")
        state = (self.subject, self.rows, labels, self.ctx.year)
        if state == self._render_state:
            return
        self._render_state = state
        result = stats(self.rows)
        mean = f"{number(result['weighted_mean'])} / 20" if self.rows else "—"
        best = f"{number(result['max'])} / 20" if self.rows else "—"
        trend = result["trend"]
        trend_value = (("+" if trend >= 0 else "") + number(trend) + " pt") if trend is not None else "—"
        self.mean_stat.value.setText(mean)
        self.mean_stat.caption.setText(tr("{count} note · coefficients pris en compte" if len(self.rows) == 1 else "{count} notes · coefficients pris en compte", count=len(self.rows)))
        self.best_stat.value.setText(best)
        self.best_stat.caption.setText(tr("Médiane : {value} / 20", value=number(result['median'])) if self.rows else tr("Chaque nouvelle note compte"))
        self.trend_stat.value.setText(trend_value)
        self.trend_stat.caption.setText(tr("3 dernières notes / 3 précédentes") if trend is not None else tr("Disponible à partir de 6 notes"))
        self.chart.set_grades(self.rows)
        self._refresh_legend()
        self._refresh_details(result, labels)
        self.history_title.setText(tr("Historique  ·  {count}", count=len(self.rows)))
        with updating(self.table):
            self.table.setRowCount(len(self.rows))
            for row_index, row in enumerate(self.rows):
                values = [
                    format_date(row["graded_on"]),
                    tr(labels.get(row["kind"], row["kind"])), row.get("label") or "—",
                    f"{number(row['score'])} / {number(row['scale'])}",
                    number(score_on_twenty(row)), number(row.get("coefficient", 1)),
                    number(float(row['class_average']) / float(row['scale']) * 20) if row.get('class_average') is not None else "—",
                    f"{row['rank']} / {row['class_size']}" if row.get('rank') is not None else "—",
                ]
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    item.setData(Qt.ItemDataRole.UserRole, row["id"])
                    if column in (3, 4, 5, 6, 7):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if column == 4:
                        font = QFont(item.font())
                        font.setWeight(QFont.Weight.Bold)
                        item.setFont(font)
                    item.setToolTip(value)
                    if column == 6 and row.get('class_average') is not None:
                        item.setToolTip(tr("Moyenne de classe : {average} / {scale} → {value} / 20", average=number(row['class_average']), scale=number(row['scale']), value=value))
                    self.table.setItem(row_index, column, item)
                if row["id"] == selected_id:
                    self.table.selectRow(row_index)
            self.table.setColumnHidden(6, not any(row.get('class_average') is not None for row in self.rows))
            self.table.setColumnHidden(7, not any(row.get('rank') is not None for row in self.rows))
        self._refresh_table_colors()
        self.table.setVisible(bool(self.rows))
        self.empty_history.setVisible(not self.rows)
        self._selection_changed()

    def selected_grade(self):
        selected = self.table.selectionModel().selectedRows()
        if selected:
            index = selected[0].row()
            if 0 <= index < len(self.rows):
                item = self.table.item(index, 0)
                if item:
                    identity = item.data(Qt.ItemDataRole.UserRole)
                    return next((row for row in self.rows if row["id"] == identity), None)
        return None

    def _selection_changed(self):
        selected = self.selected_grade() is not None
        self.edit_button.setEnabled(selected)
        self.delete_button.setEnabled(selected)

    def add_note(self):
        if not self.ctx.db.subject_labels():
            if self.add_subject() is None:
                return
        dialog = GradeDialog(self.ctx, subject=self.subject, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._show_saved_note(dialog)

    def edit_note(self):
        selected = self.selected_grade()
        if selected:
            dialog = GradeDialog(self.ctx, grade=selected, parent=self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._show_saved_note(dialog)

    def _show_saved_note(self, dialog):
        self.set_subject(dialog.subject.currentData())
        for index, row in enumerate(self.rows):
            if row["id"] == dialog.saved_id:
                self.table.selectRow(index)
                self.table.scrollToItem(self.table.item(index, 0))
                animate_table_row(self.table, index, self.ctx)
                break

    def delete_note(self):
        selected = self.selected_grade()
        if not selected:
            return
        name = self.ctx.db.subject_labels(include_archived=True).get(selected['subject'], selected['subject'])
        kind = tr(self.ctx.db.grade_kind_labels().get(selected['kind'], selected['kind']))
        description = tr("{name} · {kind}\n{score}/{scale} du {date}", name=name, kind=kind, score=number(selected['score']), scale=number(selected['scale']), date=format_date(selected['graded_on']))
        if not confirm(self, tr("Supprimer cette note ?"), description + tr("\n\nCette suppression est définitive.")):
            return
        try:
            self.ctx.db.delete_grade(selected["id"])
        except (OSError, sqlite3.Error) as exc:
            show_error(self, str(exc))
            return
        self.ctx.mark_changed('grades')
        self.ctx.notice.emit(tr("Note supprimée."))
