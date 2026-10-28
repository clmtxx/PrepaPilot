"""Personal time trends, with explicit targets and read-only presentation."""
from __future__ import annotations
from .i18n import tr, language, format_datetime, format_number, qt_locale

from datetime import date, datetime, timedelta
import sqlite3

from PySide6.QtCore import QDate, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDateEdit, QDialog,
    QDoubleSpinBox, QFormLayout, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLayout, QProgressBar, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from . import progression
from .progression_visuals import ProgressionFigure, ScoreOrb, axis_palette
from .progression_chart import AnnualProgressionChart
from .achievement_panel import AchievementPanel
from .theme import palette_for
from .widgets import AnimatedDialog, Card, button, page_header, show_error


AXES = {"work": "Travail", "sleep": "Sommeil", "sport": "Sport", "rest": "Détente"}
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
SHORT_MONTHS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")


def _label(text, name="muted"):
    item = QLabel(text, objectName=name)
    item.setTextFormat(Qt.PlainText)
    item.setWordWrap(True)
    return item


def _number(value):
    return format_number(value, 1).rstrip("0").rstrip(",.")


def _day(value):
    return f"{value.day} {tr(MONTHS[value.month - 1])} {value.year}"


class ProgressionTargetsDialog(AnimatedDialog):
    """Targets are optional; the user supplies every value explicitly."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.saved = False
        self.setWindowTitle(tr('Mes objectifs personnels'))
        self.setMinimumWidth(510)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(18)
        layout.addWidget(_label(tr('À ton rythme.'), "dialogTitle"))
        layout.addWidget(_label(tr('Choisis tes propres repères. Un objectif à 0 reste désactivé et ne compte pas dans le score.')))
        form = QFormLayout()
        form.setVerticalSpacing(12)
        self.inputs = {}
        targets = progression.load_targets(ctx.db)
        for key, title in AXES.items():
            title = tr(title)
            daily = key in {"sleep", "rest"}
            control = QDoubleSpinBox()
            control.setLocale(qt_locale())
            control.setRange(0, 24 if daily else 168)
            control.setDecimals(2)
            control.setSingleStep(0.25 if daily else 0.5)
            control.setSuffix(tr(' h / jour') if daily else tr(' h / semaine'))
            control.setSpecialValueText(tr('Désactivé'))
            control.setValue(targets[key] / (420 if daily else 60))
            control.setAccessibleName(tr('Objectif {v0}, en heures par {v1}', v0=title.lower(), v1=tr('jour') if daily else tr('semaine')))
            self.inputs[key] = control
            form.addRow(title, control)
        layout.addLayout(form)
        layout.addWidget(_label(tr('Travail = cours réalisés + travail personnel. Sommeil, sport et détente proviennent des activités réalisées de ton journal.')))
        self.error = _label("", "error")
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(button(tr("Annuler"), self.reject))
        self.save_button = button(tr("Enregistrer"), self.save, primary=True)
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def save(self):
        if self.saved:
            return
        values = {key: round(control.value() * (420 if key in {"sleep", "rest"} else 60))
                  for key, control in self.inputs.items()}
        try:
            progression.save_targets(self.ctx.db, values)
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.saved = True
        self.ctx.mark_changed('progression')
        self.ctx.notice.emit(tr('Tes objectifs sont enregistrés.'))
        self.accept()


class ProgressionPage(QWidget):
    """Presentation is cached, and only explicit actions write settings."""

    def __init__(self, ctx, navigate=None, parent=None):
        super().__init__(parent)
        self.ctx, self.navigate = ctx, navigate
        self.mode = "summary"
        self.anchor = date.today()
        self.report = {}
        self.history = []
        self._closed = False
        self._last_refresh = None
        self._history_key = None
        self._visual_theme = None
        self._subject_rows = None
        self._history_rows = None
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.setInterval(60000)
        self.timer.timeout.connect(self.refresh)
        self._data_watch = ctx.watch_data(self.refresh, 'activities', 'timetable', 'subjects', 'year', 'progression')
        ctx.theme_changed.connect(self._theme_changed)
        ctx.achievements_unlocked.connect(self.achievement_panel.celebrate)
        self.refresh()

    def _build_ui(self):
        self.outer = QVBoxLayout(self)
        # The scroll area must honour changing wrapped text and expanded details.
        self.outer.setSizeConstraint(QLayout.SetMinimumSize)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(18)
        self.objectives_button = button(tr('Mes objectifs'), self.edit_targets)
        self.outer.addWidget(page_header(tr('Progression'), tr('Bilan du travail, du sommeil et des activités.'), [self.objectives_button]))
        modes = QHBoxLayout()
        modes.setSpacing(8)
        self.mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for key, title in (("summary", tr('Synthèse')), ("week", tr('Semaine')), ("month", tr('Mois')), ("quarter", tr('3 mois')), ("achievements", tr('Succès'))):
            control = button(title, lambda checked=False, mode=key: self.set_mode(mode))
            control.setCheckable(True)
            control.setProperty("role", "tab")
            control.setAccessibleName(tr('Afficher : {v0}', v0=title))
            self.mode_group.addButton(control)
            self.mode_buttons[key] = control
            modes.addWidget(control)
        self.mode_buttons["summary"].setChecked(True)
        modes.addStretch()
        self.outer.addLayout(modes)
        self.achievement_panel = AchievementPanel(self.ctx, self)
        self.achievement_panel.hide()
        self.outer.addWidget(self.achievement_panel)

        self.period_controls = QWidget()
        controls = QHBoxLayout(self.period_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(10)
        self.previous_button = button("←", lambda: self.shift_period(-1))
        self.previous_button.setAccessibleName(tr('Période précédente'))
        self.next_button = button("→", lambda: self.shift_period(1))
        self.next_button.setAccessibleName(tr('Période suivante'))
        self.date_picker = QDateEdit(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        self.date_picker.setDisplayFormat("dd MMM yyyy" if language() == 'en' else "dd/MM/yyyy")
        self.date_picker.setLocale(qt_locale())
        self.date_picker.setMinimumDate(QDate(2000, 1, 1))
        self.date_picker.setMaximumDate(QDate.currentDate())
        self.date_picker.setAccessibleName(tr('Date de référence de la période'))
        self.date_picker.dateChanged.connect(self._date_changed)
        controls.addWidget(self.previous_button)
        controls.addWidget(self.date_picker)
        controls.addWidget(self.next_button)
        controls.addWidget(button(tr('Période actuelle'), self.current_period))
        controls.addStretch()
        self.outer.addWidget(self.period_controls)
        period_line = QHBoxLayout()
        period_line.setSpacing(12)
        self.period_title = _label("", "sectionTitle")
        self.period_title.setStyleSheet("font-size:15px;font-weight:600;")
        self.period_status = _label("", "badge")
        period_line.addWidget(self.period_title, 1)
        period_line.addWidget(self.period_status)
        self.outer.addLayout(period_line)

        self.hero_card = Card()
        self.hero_card.setObjectName("ProgressionHero")
        self.hero_card.body.setContentsMargins(24, 18, 30, 18)
        hero = QHBoxLayout()
        hero.setSpacing(26)
        self.score_orb = ScoreOrb()
        self.score_orb.setFixedSize(176, 176)
        hero.addWidget(self.score_orb, 0, Qt.AlignVCenter)
        hero_copy = QVBoxLayout()
        hero_copy.setSpacing(10)
        hero_copy.addWidget(_label(tr('UN ÉQUILIBRE QUI T’APPARTIENT'), "eyebrow"))
        self.hero_title = _label(tr('Ton rythme prend forme.'), "sectionTitle")
        self.hero_title.setStyleSheet("font-size:28px;font-weight:650;letter-spacing:-0.8px;")
        hero_copy.addWidget(self.hero_title)
        self.hero_caption = _label(tr('Chaque activité dessine un peu plus ton quotidien.'))
        hero_copy.addWidget(self.hero_caption)
        self.score_values = {"global": _label("—")}
        self.score_values["global"].setAccessibleName(tr('Score global'))
        self.score_values["global"].setStyleSheet("font-size:18px;font-weight:600;")
        self.score_captions = {"global": _label("")}
        global_line = QHBoxLayout()
        global_line.setSpacing(12)
        global_line.addWidget(self.score_values["global"])
        global_line.addWidget(self.score_captions["global"], 1)
        # The orb is the visual score; this line retains an ordinary text value.
        self.global_line = QWidget()
        self.global_line.setLayout(global_line)
        global_line.setContentsMargins(0, 0, 0, 0)
        hero_copy.addWidget(self.global_line)
        self.scores_container = QWidget()
        self.scores_layout = QHBoxLayout(self.scores_container)
        self.scores_layout.setContentsMargins(0, 0, 0, 0)
        self.scores_layout.setSpacing(20)
        self.score_titles = {}
        for key, title in (("work", tr('Travail')), ("sleep", tr('Sommeil')), ("recovery", tr('Récupération'))):
            column = QVBoxLayout()
            column.setSpacing(3)
            self.score_titles[key] = _label(title)
            column.addWidget(self.score_titles[key])
            self.score_values[key] = _label("—")
            self.score_values[key].setStyleSheet("font-size:21px;font-weight:650;letter-spacing:-0.5px;")
            column.addWidget(self.score_values[key])
            self.score_captions[key] = _label("")
            self.score_captions[key].setStyleSheet("font-size:11px;")
            column.addWidget(self.score_captions[key])
            self.scores_layout.addLayout(column, 1)
        hero_copy.addWidget(self.scores_container)
        self.targets_prompt = QWidget()
        target_prompt_layout = QHBoxLayout(self.targets_prompt)
        target_prompt_layout.setContentsMargins(0, 2, 0, 0)
        target_prompt_layout.setSpacing(14)
        target_prompt_layout.addWidget(button(tr('Choisir mes objectifs  →'), self.edit_targets, primary=True), 0, Qt.AlignLeft)
        target_prompt_layout.addStretch()
        hero_copy.addWidget(self.targets_prompt)
        self.empty_card = QWidget()
        empty_layout = QHBoxLayout(self.empty_card)
        empty_layout.setContentsMargins(0, 0, 0, 0)
        empty_layout.setSpacing(8)
        empty_layout.addWidget(_label(tr('Le début de ton historique.')), 1)
        empty_layout.addWidget(button(tr('Noter une activité  →'), self.open_time))
        hero_copy.addWidget(self.empty_card)
        hero.addLayout(hero_copy, 1)
        self.hero_card.body.addLayout(hero)
        self.outer.addWidget(self.hero_card)

        self.metrics_container = QWidget()
        self.metrics_layout = QGridLayout(self.metrics_container)
        self.metrics_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.metrics_layout.setContentsMargins(0, 0, 0, 0)
        self.metrics_layout.setSpacing(16)
        self.metrics_layout.setColumnStretch(0, 1)
        self.metrics_layout.setColumnStretch(1, 1)
        self.metric_values = {}
        self.metric_titles = {}
        self.delta_labels = {}
        self.delta_badges = {}
        self.comparison_labels = {}
        self.target_labels = {}
        self.target_bars = {}
        self.metric_cards = {}
        self.figures = {}
        self._ack_controls = {}
        self.ack_buttons = {}
        for index, (key, title) in enumerate(AXES.items()):
            title = tr(title)
            card = Card()
            card.setObjectName(f"ProgressionMetric_{key}")
            card.body.setContentsMargins(24, 18, 20, 20)
            card.body.setSpacing(10)
            card.body.setSizeConstraint(QLayout.SetMinimumSize)
            self.metric_cards[key] = card
            top = QHBoxLayout()
            top.setSpacing(8)
            numbers = QVBoxLayout()
            numbers.setSpacing(7)
            self.metric_titles[key] = _label(title, "sectionTitle")
            numbers.addWidget(self.metric_titles[key])
            self.metric_values[key] = _label("", "statValue")
            self.metric_values[key].setStyleSheet("font-size:36px;font-weight:650;letter-spacing:-1.2px;")
            numbers.addWidget(self.metric_values[key])
            numbers.addWidget(_label(tr('TEMPS RÉALISÉ'), "eyebrow"))
            numbers.addStretch()
            top.addLayout(numbers, 1)
            figure = ProgressionFigure(key)
            figure.setFixedSize(154, 128)
            card.bind_pointer_figure(figure)
            self.figures[key] = figure
            top.addWidget(figure, 0, Qt.AlignVCenter)
            card.body.addLayout(top)
            self.target_labels[key] = _label("")
            self.target_labels[key].setStyleSheet("font-size:12px;")
            card.body.addWidget(self.target_labels[key])
            target_bar = QProgressBar()
            target_bar.setRange(0, 1000)
            target_bar.setTextVisible(False)
            target_bar.setFixedHeight(6)
            self.target_bars[key] = target_bar
            card.body.addWidget(target_bar)
            foot = QHBoxLayout()
            foot.setSpacing(8)
            self.delta_badges[key] = _label("")
            self.delta_badges[key].setStyleSheet("font-size:12px;font-weight:600;")
            foot.addWidget(self.delta_badges[key], 1)
            control = button(tr('Aucun problème'), lambda checked=False, axis=key: self.toggle_acknowledgement(axis))
            control.setProperty("role", "link")
            control.setStyleSheet("font-size:11px;min-height:16px;padding-top:2px;padding-bottom:2px;")
            control.setToolTip(tr('Change seulement l’indication de cette période. Les durées et le score restent identiques.'))
            self._ack_controls[key] = control
            foot.addWidget(control, 0, Qt.AlignRight)
            card.body.addLayout(foot)
            self.metrics_layout.addWidget(card, index // 2, index % 2)
        self.outer.addWidget(self.metrics_container)

        self.details_card = Card()
        self.details_card.body.setContentsMargins(24, 14, 24, 14)
        self.details_toggle = button(tr('Détails du bilan  +'), self.toggle_details)
        self.details_toggle.setCheckable(True)
        self.details_toggle.setProperty("role", "link")
        self.details_toggle.setAccessibleName(tr('Afficher les détails du bilan'))
        self.details_card.body.addWidget(self.details_toggle, 0, Qt.AlignLeft)
        self.details_body = QWidget()
        details = QVBoxLayout(self.details_body)
        details.setContentsMargins(0, 0, 0, 6)
        details.setSpacing(14)
        self.period_caption = _label("")
        self.comparison_caption = _label("")
        details.addWidget(self.period_caption)
        details.addWidget(self.comparison_caption)
        details.addWidget(_label(tr('Ces repères reflètent uniquement ton journal : une catégorie sans saisie vaut 0, même si l’activité a eu lieu.')))
        for key, title in AXES.items():
            title = tr(title)
            details.addWidget(_label(title, "sectionTitle"))
            self.delta_labels[key] = _label("")
            self.comparison_labels[key] = _label("")
            details.addWidget(self.delta_labels[key])
            details.addWidget(self.comparison_labels[key])
        self.score_explanation = _label(tr('Les scores comparent le temps réalisé à tes objectifs, à hauteur du temps écoulé. Ils ne mesurent ni tes résultats scolaires ni ta santé.'))
        details.addWidget(self.score_explanation)
        calculation = button(tr('Comprendre le calcul  →'), self.explain_scores)
        calculation.setProperty("role", "link")
        details.addWidget(calculation, 0, Qt.AlignLeft)
        self.details_body.hide()
        self.details_card.body.addWidget(self.details_body)
        self.outer.addWidget(self.details_card)

        history_card = self.history_card = Card()
        history_header = QHBoxLayout()
        history_header.addWidget(_label(tr('Ton année au fil des mois.'), "sectionTitle"), 1)
        self.history_axis = QComboBox()
        for key, title in AXES.items():
            title = tr(title)
            self.history_axis.addItem(title, key)
        self.history_axis.setAccessibleName(tr('Axe de l’historique annuel'))
        self.history_axis.currentIndexChanged.connect(self._render_history)
        history_header.addWidget(self.history_axis)
        history_card.body.addLayout(history_header)
        self.history_caption = _label("")
        history_card.body.addWidget(self.history_caption)
        self.chart = AnnualProgressionChart(self.ctx)
        history_card.body.addWidget(self.chart)
        self.history_toggle = button(tr('Afficher les valeurs'), self.toggle_history_table)
        self.history_toggle.setCheckable(True)
        history_card.body.addWidget(self.history_toggle, 0, Qt.AlignLeft)
        self.history_table = self._table((tr('Mois'), tr('Temps réalisé'), tr('Moyenne / jour')))
        self.history_table.setAccessibleName(tr('Valeurs de l’historique annuel'))
        self.history_table.hide()
        history_card.body.addWidget(self.history_table)
        self.outer.addWidget(history_card)

        self.subject_card = Card()
        self.subject_card.body.addWidget(_label(tr('Le travail, matière par matière.'), "sectionTitle"))
        self.work_sources = _label("")
        self.subject_card.body.addWidget(self.work_sources)
        self.subjects = self._table((tr('Matière'), tr('Temps réalisé')))
        self.subjects.setAccessibleName(tr('Travail réalisé par matière pendant la période'))
        self.subject_card.body.addWidget(self.subjects)
        self.outer.addWidget(self.subject_card)
        self.outer.addStretch()

    def toggle_details(self):
        expanded = self.details_toggle.isChecked()
        self.details_body.setVisible(expanded)
        self.details_toggle.setText(tr('Détails du bilan  −') if expanded else tr('Détails du bilan  +'))
        self.details_toggle.setAccessibleName(tr('Masquer les détails du bilan') if expanded else tr('Afficher les détails du bilan'))

    def _apply_visual_theme(self):
        if self._visual_theme == self.ctx.theme:
            return
        self._visual_theme = self.ctx.theme
        colors = palette_for(self.ctx.theme)
        dark = self.ctx.theme == "dark"
        start, middle, finish = ("#123C71", "#34275F", "#572451") if dark else ("#CEE7FF", "#E2D7FF", "#FFD8EC")
        border = "#A586F1" if dark else "#9775E6"
        self.hero_card.setProperty('materialAccent', border)
        self.hero_card.setProperty('materialRadius', 26)
        self.hero_card.setStyleSheet(f"QFrame#ProgressionHero {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {start},stop:.56 {middle},stop:1 {finish});border:1px solid {border};border-radius:26px;}}")
        for key in AXES:
            axis = axis_palette(key, self.ctx.theme)
            card = self.metric_cards[key]
            card.setProperty('materialAccent', axis['accent'])
            card.setProperty('materialRadius', 24)
            card.setStyleSheet(f"QFrame#ProgressionMetric_{key} {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {axis['tint']},stop:.42 {axis['tint']},stop:1 {colors['surface']});border:1px solid {axis['accent']};border-radius:24px;}}")
            self.metric_titles[key].setStyleSheet(f"color:{axis['accent']};font-size:19px;font-weight:600;")
            self.target_bars[key].setStyleSheet(f"QProgressBar {{background:{colors['border']};border:none;border-radius:3px;}} QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {axis['accent']},stop:1 {axis['light']});border-radius:3px;}}")
            self.figures[key].update()
        for key, axis_name in (("work", "work"), ("sleep", "sleep"), ("recovery", "sport")):
            accent = axis_palette(axis_name, self.ctx.theme)["accent"]
            self.score_values[key].setStyleSheet(f"color:{accent};font-size:21px;font-weight:650;letter-spacing:-0.5px;")
            self.score_titles[key].setStyleSheet(f"color:{accent};font-size:12px;font-weight:600;")
        self.score_orb.update()

    @staticmethod
    def _table(headers):
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.setMinimumHeight(130)
        table.setMaximumHeight(310)
        return table

    def set_mode(self, mode):
        if mode not in self.mode_buttons:
            return
        self.mode = mode
        self.mode_buttons[mode].setChecked(True)
        self.refresh()

    def _date_changed(self, value):
        self.anchor = value.toPython()
        self.refresh()

    def current_period(self):
        today = date.today()
        self.anchor = today
        current = QDate(today.year, today.month, today.day)
        if self.date_picker.date() == current:
            self.refresh()
        else:
            self.date_picker.setDate(current)  # dateChanged performs one refresh.

    def shift_period(self, direction):
        current = QDate(self.anchor.year, self.anchor.month, self.anchor.day)
        shifted = current.addDays(7 * direction) if self.mode == "week" else current.addMonths((3 if self.mode == "quarter" else 1) * direction)
        shifted = max(self.date_picker.minimumDate(), min(shifted, QDate.currentDate()))
        self.date_picker.setDate(shifted)

    def refresh(self, *_):
        if self._closed:
            return
        now = datetime.now()
        self._last_refresh = now
        achievements_visible = self.mode == 'achievements'
        if not achievements_visible:
            self.achievement_panel.hide()
        for widget in (self.period_title, self.period_status, self.hero_card,
                       self.metrics_container, self.details_card, self.history_card,
                       self.subject_card, self.objectives_button):
            widget.setVisible(not achievements_visible)
        self.period_controls.setVisible(not achievements_visible and self.mode != 'summary')
        if achievements_visible:
            self.achievement_panel.refresh(self.ctx.achievement_report())
            self.achievement_panel.show()
            return
        self.date_picker.setMaximumDate(QDate(now.year, now.month, now.day))
        anchor = now.date() if self.mode == "summary" else min(self.anchor, now.date())
        self.report = progression.build_report(self.ctx.db, "week" if self.mode == "summary" else self.mode, anchor, now=now)
        # Period navigation does not change the annual chart. Invalidate on
        # writes, a replaced database, a school year change or the next minute.
        history_key = (self.ctx.db, self.ctx.db._connection.total_changes, self.ctx.year,
                       now.replace(second=0, microsecond=0))
        if history_key != self._history_key:
            self.history = progression.annual_history(self.ctx.db, self.ctx.year, now=now)
            self._history_key = history_key
        self._render()

    @property
    def preview_revision(self):
        return self._last_refresh

    def _theme_changed(self, *_):
        if not self._closed:
            if self.mode == 'achievements':
                self.achievement_panel.refresh(self.ctx.achievement_report())
            else:
                self._render()

    def _render(self):
        if not self.report:
            return
        report = self.report
        self._apply_visual_theme()
        self.period_controls.setVisible(self.mode != "summary")
        end = report["period_end"] - timedelta(days=1)
        start = report["period_start"]
        interval = f"{start.day} – {_day(end)}" if (start.year, start.month) == (end.year, end.month) else f"{_day(start)} – {_day(end)}"
        self.period_title.setText((tr('Cette semaine · ') if self.mode == "summary" else "") + interval)
        current = report["end"] < datetime.combine(report["period_end"], datetime.min.time())
        self.period_status.setText(tr('En cours') if current else tr('Terminée'))
        self.period_caption.setText(tr('Période en cours · activités réalisées jusqu’à maintenant. Comparaison à durée égale avec la période précédente.') if current else tr('Période terminée · activités réalisées. Comparaison à durée égale avec la période précédente.'))
        comparison = report["comparison"]
        stamp = format_datetime
        self.comparison_caption.setText(tr('Fenêtres comparées : du {v0} au {v1} ; du {v2} au {v3} (fins exclues).', v0=stamp(comparison['current_start']), v1=stamp(comparison['current_end']), v2=stamp(comparison['previous_start']), v3=stamp(comparison['previous_end'])))
        self.next_button.setEnabled(report["period_end"] <= date.today())
        self.previous_button.setEnabled(self.anchor > date(2000, 1, 1))
        self.empty_card.setVisible(not report["has_data"])
        configured = any(report["targets"].values())
        self.targets_prompt.setVisible(not configured)
        self.scores_container.setVisible(configured)
        self.global_line.setVisible(configured)
        self.hero_caption.setText(tr('Tes activités, tes objectifs. Une vue d’ensemble sur ton équilibre.') if configured else tr('Travail, sommeil, sport et détente : choisis les repères qui te conviennent.'))
        self.score_orb.set_score(report["scores"]["global"] if report["has_data"] else None)
        self.score_explanation.setVisible(configured)
        for key, caption in (("global", tr('Moyenne des repères actifs')), ("work", tr('Cours et travail personnel')), ("sleep", tr('Ton objectif personnel')), ("recovery", tr('Sport et détente'))):
            score = report["scores"][key]
            self.score_values[key].setText(f"{round(score)} / 100" if score is not None and report["has_data"] else "—")
            self.score_captions[key].setText(tr('Journal à compléter') if not report["has_data"] else caption if score is not None else tr('Aucun objectif actif'))
        self.ack_buttons = {}
        for key in AXES:
            self.metric_values[key].setText(progression.format_duration(report["totals"][key]))
            delta, tone, declining = self._comparison_text(key)
            label = self.delta_labels[key]
            label.setText(delta)
            style = f"color:{palette_for(self.ctx.theme)[tone]};"
            if label.styleSheet() != style:
                label.setStyleSheet(style)
            badge = self.delta_badges[key]
            badge.setText(self._comparison_badge(key))
            badge.setToolTip(delta)
            style = f"color:{palette_for(self.ctx.theme)[tone]};font-size:12px;font-weight:600;"
            if badge.styleSheet() != style:
                badge.setStyleSheet(style)
            comparable = comparison.get("has_data", False)
            self.comparison_labels[key].setText(tr('Sur les fenêtres comparées : {v0} contre {v1}.', v0=progression.format_duration(comparison['current_totals'][key]), v1=progression.format_duration(comparison['previous_totals'][key])) if comparable else "")
            self.comparison_labels[key].setVisible(comparable)
            target = report["targets"][key]
            self.target_labels[key].setText(tr('Ton repère : {v0}', v0=progression.format_duration(target / 7) + tr(' / jour') if key in {'sleep', 'rest'} else progression.format_duration(target) + tr(' / semaine')) if target else tr('Sans objectif personnel'))
            period_target = target * report["elapsed_days"] / 7
            ratio = min(1.0, report["totals"][key] / period_target) if period_target > 0 else 0
            self.target_bars[key].setValue(round(ratio * 1000))
            self.target_bars[key].setVisible(bool(target))
            self.target_bars[key].setAccessibleName(tr('{v0} : {v1} % de l’objectif adapté au temps écoulé', v0=tr(AXES[key]), v1=round(ratio * 100)))
            self.target_bars[key].setToolTip(tr('{v0} % du repère pour le temps écoulé · {v1}', v0=round(ratio * 100), v1=progression.format_duration(period_target)))
            acknowledged = key in report["acknowledged"]
            acknowledge_button = self._ack_controls[key]
            acknowledge_button.setText(tr('Rétablir l’indication') if acknowledged else tr('Aucun problème'))
            acknowledge_button.setVisible(declining or acknowledged)
            if declining or acknowledged:
                self.ack_buttons[key] = acknowledge_button
        sources = report["work_sources"]
        self.work_sources.setText(tr('Emploi du temps validé : {v0} · Activités ajoutées : {v1}', v0=progression.format_duration(sources['courses']), v1=progression.format_duration(sources['personal'])))
        rows = report["work_by_subject"]
        if not rows:
            rows = [{"label": tr('Aucune activité de travail réalisée sur cette période'), "minutes": 0}]
        subject_rows = tuple((row["label"], progression.format_duration(row["minutes"])) for row in rows)
        if self._subject_rows != subject_rows:
            self._subject_rows = subject_rows
            self.subjects.setRowCount(len(subject_rows))
            for index, values in enumerate(subject_rows):
                for column, value in enumerate(values):
                    self.subjects.setItem(index, column, QTableWidgetItem(value))
            self.subjects.resizeRowsToContents()
            self.subjects.setFixedHeight(min(280, max(120, self.subjects.horizontalHeader().height() + sum(self.subjects.rowHeight(i) for i in range(self.subjects.rowCount())) + 4)))
        self._render_history()

    def _comparison_badge(self, key):
        comparison = self.report["comparison"]
        if key in self.report["acknowledged"]:
            return tr('À ton rythme')
        if not comparison.get("has_data", False):
            return tr('Comparaison à venir')
        delta = comparison["deltas"][key]
        if abs(delta) < 0.01:
            return tr("→  Temps stable")
        sign = "+" if delta > 0 else "−"
        return tr('{v0} {v1} sur la période précédente', v0=sign, v1=progression.format_duration(abs(delta)))

    def _comparison_text(self, key):
        comparison = self.report["comparison"]
        if not comparison.get("has_data", False):
            return tr('Comparaison indisponible · une des deux périodes n’est pas renseignée.'), "muted", False
        delta = comparison["deltas"][key]
        previous = progression.format_duration(comparison["previous_totals"][key])
        acknowledged = key in self.report["acknowledged"]
        if acknowledged:
            return tr('À ton rythme · indication neutralisée pour cette période. Référence : {v0}.', v0=previous), "muted", delta < 0
        amount = progression.format_duration(abs(delta))
        percentage = comparison["percentages"][key]
        relative = f" ({'+' if percentage > 0 else ''}{_number(percentage)} %)" if percentage is not None and delta else ""
        if abs(delta) < 0.01:
            return tr('{v0}Temps saisi stable · {v1} sur la période précédente.', v0='🙂 ' if key == 'work' else '', v1=previous), "muted", False
        if delta > 0:
            return tr('{v0}+ {v1}{v2} par rapport à la période précédente.', v0='🙂 ' if key == 'work' else '', v1=amount, v2=relative), "green" if key == "work" else "muted", False
        return tr('{v0}− {v1}{v2} par rapport à la période précédente. Une baisse peut refléter une période différente ou un journal incomplet.', v0='🙁 ' if key == 'work' else '', v1=amount, v2=relative), "danger" if key == "work" else "muted", True

    def toggle_acknowledgement(self, axis):
        try:
            if axis in self.report["acknowledged"]:
                progression.clear_acknowledgement(self.ctx.db, self.report["period_key"], axis)
            else:
                progression.acknowledge(self.ctx.db, self.report["period_key"], axis)
        except (ValueError, OSError, sqlite3.Error) as exc:
            show_error(self, str(exc))
            return
        self.ctx.mark_changed('progression')

    def _render_history(self, *_):
        if not hasattr(self, "history_table"):
            return
        axis = self.history_axis.currentData() or "work"
        self.history_caption.setText(tr('Septembre {v0} → août {v1} · moyenne en heures par jour écoulé. Les mois sans saisie restent vides.', v0=self.ctx.year, v1=self.ctx.year + 1))
        self.chart.set_data(self.history, axis)
        table_rows = []
        for row in self.history:
            month = row["month"]
            available = row.get("averages") is not None
            values = (f"{tr(MONTHS[month.month - 1]).capitalize()} {month.year}",
                      progression.format_duration(row["totals"][axis]) if available else tr('À venir') if row.get("future") else tr('Non renseigné'),
                      progression.format_duration(row["averages"][axis]) if available else "—")
            table_rows.append(values)
        table_rows = tuple(table_rows)
        if self._history_rows != table_rows:
            self._history_rows = table_rows
            self.history_table.setRowCount(len(table_rows))
            for index, values in enumerate(table_rows):
                for column, value in enumerate(values):
                    self.history_table.setItem(index, column, QTableWidgetItem(value))
            self.history_table.resizeRowsToContents()

    def toggle_history_table(self):
        visible = self.history_toggle.isChecked()
        self.history_table.setVisible(visible)
        self.history_toggle.setText(tr('Masquer les valeurs') if visible else tr('Afficher les valeurs'))

    def edit_targets(self):
        dialog = ProgressionTargetsDialog(self.ctx, self)
        dialog.exec()
        dialog.deleteLater()

    def explain_scores(self):
        dialog = AnimatedDialog(self)
        dialog.setWindowTitle(tr('Comprendre les scores'))
        dialog.setMinimumWidth(520)
        dialog.setMaximumWidth(610)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(16)
        layout.addWidget(_label(tr('Des repères, pas un verdict.'), "dialogTitle"))
        for text in (
            tr('Seules les activités réalisées et déjà écoulées comptent. Les séances prévues, annulées ou futures sont exclues.'),
            tr('Chaque objectif est ramené à la durée écoulée de la période. Score = temps réalisé ÷ objectif correspondant × 100, avec un plafond de 100. Faire davantage ne pénalise pas le score.'),
            tr('Travail : toutes tes matières, cours compris. Sommeil : ton temps de sommeil. Récupération : moyenne des objectifs actifs de sport et de détente. Le score global est la moyenne des scores Travail, Sommeil et Récupération actifs.'),
            tr('Sans objectif, aucun score n’est calculé pour l’axe. Sans activité renseignée sur une période, aucun score n’est affiché. Le score mesure uniquement le temps saisi par rapport à tes objectifs personnels, jamais ta santé ou tes résultats scolaires.'),
            tr('Les comparaisons utilisent la même durée dans les deux périodes. « Aucun problème » neutralise l’indication pour la période sélectionnée, sans modifier tes données ni le calcul du score.'),
        ):
            layout.addWidget(_label(text))
        layout.addWidget(button(tr("Compris"), dialog.accept, primary=True), 0, Qt.AlignRight)
        dialog.exec()
        dialog.deleteLater()

    def open_time(self):
        if self.navigate:
            self.navigate("time")

    def showEvent(self, event):
        super().showEvent(event)
        if not self._closed:
            self.timer.start()
            if self._last_refresh is None or (datetime.now() - self._last_refresh).total_seconds() >= 60:
                self.refresh()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def shutdown(self):
        if self._closed:
            return
        self._closed = True
        self.timer.stop()
        self.achievement_panel.shutdown()
        self.ctx.achievements_unlocked.disconnect(self.achievement_panel.celebrate)
        self.ctx.data_changed.disconnect(self._data_watch)
        self.ctx.theme_changed.disconnect(self._theme_changed)
