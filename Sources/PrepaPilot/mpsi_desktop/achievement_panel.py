"""A rewarding, lightweight collection of achievements and recurring quests."""
from __future__ import annotations
from .i18n import tr, language, format_date

from datetime import datetime

from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLayout,
    QProgressBar, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget, QSizePolicy,
)

from .achievement_visuals import BadgeFigure, METALS, TIER_NAMES
from .progression import format_duration
from .progression_visuals import axis_palette
from .theme import palette_for
from .visuals import ReflectiveTitle
from .widgets import AnimatedDialog, Card, button


_FAMILY_AXES = {
    "work_total": "work", "work_week": "sport", "work_month": "rest",
    "sleep_streak": "sleep", "sport_total": "sport", "sport_streak": "sport",
}


def _label(text="", name="muted"):
    result = QLabel(str(text), objectName=name)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(True)
    result.setMinimumWidth(0)
    return result


def _count(number):
    return f"{int(number):,}".replace(",", "\u202f") if language() == 'fr' else f"{int(number):,}"


def _amount(value, unit):
    if unit == "minutes":
        return format_duration(value)
    value = int(value)
    if unit == 'nights':
        return tr('{value} nuit' if value == 1 else '{value} nuits', value=value)
    if unit == 'weeks':
        return tr('{value} semaine' if value == 1 else '{value} semaines', value=value)
    return tr('{value} jour' if value == 1 else '{value} jours', value=value)


def _date(value):
    try:
        return format_date(datetime.fromisoformat(value))
    except (TypeError, ValueError):
        return ""


def _bar():
    result = QProgressBar()
    result.setRange(0, 1000)
    result.setTextVisible(False)
    result.setFixedHeight(7)
    return result


def _progress(bar, current, target, earned=False):
    fraction = 1 if earned else min(1, max(0, current / max(1, target)))
    bar.setValue(round(fraction * 1000))
    bar.setAccessibleDescription(f"{round(fraction * 100)} %")


class _QuestCard(Card):
    def __init__(self, index, parent=None):
        super().__init__(parent)
        self.index = index
        self.axis = ("work", "sport", "sleep", "rest")[index % 4]
        self._theme = None
        self.setObjectName(f"AchievementQuest_{index}")
        self.body.setContentsMargins(22, 20, 22, 20)
        self.body.setSpacing(10)
        top = QHBoxLayout()
        self.period = _label("", "eyebrow")
        self.reward = _label("", "badge")
        self.reward.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        top.addWidget(self.period, 1)
        top.addWidget(self.reward)
        self.body.addLayout(top)
        self.title = _label("", "cardTitle")
        self.description = _label()
        self.progress = _bar()
        self.status = _label()
        self.body.addWidget(self.title)
        self.body.addWidget(self.description)
        self.body.addStretch()
        self.body.addWidget(self.progress)
        self.body.addWidget(self.status)

    def render(self, quest):
        # The period is part of the id, so a new week reuses the same card.
        quest_id = quest.get("id", "")
        axis = "sport" if quest_id.startswith("quest:sport_") else ("work", "sport", "sleep", "rest")[self.index % 4]
        if axis != self.axis:
            self.axis = axis
            if self._theme:
                self.set_theme(self._theme)
        self.period.setText(quest.get("period_label", ""))
        earned = bool(quest.get("earned_at"))
        self.reward.setText(f"{'' if earned else '+'}{_count(quest.get('points', 0))} XP")
        self.title.setText(quest.get("title", ""))
        self.description.setText(quest.get("description", ""))
        current, target, unit = quest.get("current", 0), quest.get("target", 1), quest.get("unit", "days")
        if quest.get('id', '').startswith('quest:sleep_nights:'):
            unit = 'nights'
        _progress(self.progress, current, target, earned)
        self.progress.setAccessibleName(tr('Progression de la quête {v0}', v0=quest.get('title', '')))
        if earned:
            self.status.setText(tr('Accomplie le {v0} · Bien joué !', v0=_date(quest['earned_at'])))
        else:
            self.status.setText(tr('{v0} sur {v1}', v0=_amount(current, unit), v1=_amount(target, unit)))

    def set_theme(self, theme):
        self._theme = theme
        colors = palette_for(theme)
        axis = axis_palette(self.axis, theme)
        self.setStyleSheet(f"QFrame#{self.objectName()} {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {axis['tint']},stop:.38 {axis['tint']},stop:1 {colors['surface']});border:1px solid {axis['accent']};border-radius:22px;}}")
        self.title.setStyleSheet(f"color:{axis['accent']};font-size:18px;font-weight:600;")
        reward_ink = '#111627' if theme == 'dark' else '#FFFFFF'
        reward_end = axis['light'] if theme == 'dark' else axis['dark']
        self.reward.setStyleSheet(f"color:{reward_ink};background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {axis['accent']},stop:1 {reward_end});border-radius:11px;padding:5px 9px;font-size:12px;font-weight:600;")
        self.progress.setStyleSheet(f"QProgressBar {{background:{colors['border']};border:none;border-radius:3px;}} QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {axis['accent']},stop:1 {axis['light']});border-radius:3px;}}")


class _FamilyCard(Card):
    def __init__(self, family_id, show_details, parent=None):
        super().__init__(parent)
        self.family_id = family_id
        self.setObjectName(f"AchievementFamily_{family_id}")
        self.body.setContentsMargins(22, 20, 22, 20)
        self.body.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(6)
        self.collection = _label("", "eyebrow")
        self.title = _label("", "cardTitle")
        self.value = _label("", "statValue")
        text.addWidget(self.collection)
        text.addWidget(self.title)
        text.addWidget(self.value)
        top.addLayout(text, 1)
        self.figure = BadgeFigure(family=family_id, locked=True)
        self.figure.setFixedSize(120, 114)
        top.addWidget(self.figure)
        self.body.addLayout(top)
        self.description = _label()
        self.body.addWidget(self.description)
        self.body.addStretch()
        self.progress = _bar()
        self.body.addWidget(self.progress)
        self.next_tier = _label()
        self.body.addWidget(self.next_tier)
        self.details_button = button(tr('Découvrir les paliers  →'), lambda: show_details(family_id))
        self.details_button.setProperty("role", "link")
        self.details_button.setAccessibleName(tr('Voir les paliers de {v0}', v0=family_id))
        self.body.addWidget(self.details_button, 0, Qt.AlignmentFlag.AlignLeft)

    def render(self, family):
        tiers = family.get("tiers", [])
        earned = [(index, tier) for index, tier in enumerate(tiers) if tier.get("earned_at")]
        upcoming = next((tier for tier in tiers if not tier.get("earned_at")), None)
        current, unit = family.get("current", 0), family.get("unit", "minutes")
        if self.family_id == 'sleep_streak':
            unit = 'nights'
        self.collection.setText(tr('{v0} / {v1} MÉDAILLES', v0=len(earned), v1=len(tiers)))
        self.title.setText(family.get("title", ""))
        self.value.setText(_amount(current, unit))
        self.description.setText(family.get("description", ""))
        self.figure.set_badge(earned[-1][0] if earned else 0, self.family_id, not earned)
        self.details_button.setAccessibleName(tr('Voir les cinq paliers de {v0}', v0=family.get('title', '')))
        self.progress.setAccessibleName(tr('Prochain palier de {v0}', v0=family.get('title', '')))
        if upcoming:
            _progress(self.progress, current, upcoming["target"])
            self.next_tier.setText(tr('Prochain palier : {v0} · {v1} · +{v2} XP', v0=upcoming['name'], v1=_amount(upcoming['target'], unit), v2=_count(upcoming['points'])))
        else:
            _progress(self.progress, 1, 1, True)
            self.next_tier.setText(tr('Collection complète. Les cinq paliers sont à toi.'))

    def set_theme(self, theme):
        colors = palette_for(theme)
        axis = axis_palette(_FAMILY_AXES[self.family_id], theme)
        self.setStyleSheet(f"QFrame#{self.objectName()} {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {axis['tint']},stop:.38 {axis['tint']},stop:1 {colors['surface']});border:1px solid {axis['accent']};border-radius:24px;}}")
        self.value.setStyleSheet(f"color:{axis['accent']};font-size:30px;font-weight:650;letter-spacing:-.8px;")
        self.title.setStyleSheet(f"font-size:18px;font-weight:600;color:{colors['text']};")
        self.progress.setStyleSheet(f"QProgressBar {{background:{colors['border']};border:none;border-radius:3px;}} QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {axis['accent']},stop:1 {axis['light']});border-radius:3px;}}")
        self.figure.update()


class AchievementDetailsDialog(AnimatedDialog):
    """The complete reward ladder is built only when its collection is opened."""

    def __init__(self, family, theme="light", parent=None):
        super().__init__(parent)
        self.setWindowTitle(family.get("title", tr('Mes succès')))
        self.resize(590, 600)
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(12)
        layout.addWidget(_label(family.get("title", ""), "dialogTitle"))
        layout.addWidget(_label(family.get("description", "")))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 4, 8, 4)
        rows.setSpacing(10)
        colors = palette_for(theme)
        for index, tier in enumerate(family.get("tiers", [])):
            card = Card()
            card.setObjectName(f"AchievementTier_{index}")
            card.body.setContentsMargins(14, 10, 16, 10)
            row = QHBoxLayout()
            row.setSpacing(16)
            earned = bool(tier.get("earned_at"))
            figure = BadgeFigure(index, family.get("id", "work_total"), not earned)
            figure.setFixedSize(92, 86)
            row.addWidget(figure)
            text = QVBoxLayout()
            text.setSpacing(5)
            name = _label(tier.get("name", tr(TIER_NAMES[min(4, index)])), "cardTitle")
            accent = METALS[min(index, 4)][1 if theme == "dark" else 2]
            name.setStyleSheet(f"color:{accent};font-size:18px;font-weight:650;")
            text.addWidget(name)
            unit = 'nights' if family.get('id') == 'sleep_streak' else family.get('unit', 'minutes')
            text.addWidget(_label(f"{_amount(tier.get('target', 0), unit)} · +{_count(tier.get('points', 0))} XP"))
            text.addWidget(_label(tr('Obtenue le {v0}', v0=_date(tier['earned_at'])) if earned else tr('À débloquer'), "muted"))
            row.addLayout(text, 1)
            card.body.addLayout(row)
            border = accent if earned else colors["border"]
            card.setStyleSheet(f"QFrame#{card.objectName()} {{background:{colors['surface']};border:1px solid {border};border-radius:19px;}}")
            rows.addWidget(card)
        rows.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout.addWidget(_label(tr('Tes médailles obtenues restent acquises, même si tu corriges ensuite ton journal.')))
        actions = QHBoxLayout()
        actions.addStretch()
        close = button(tr("Fermer"), self.accept, primary=True)
        close.setDefault(True)
        actions.addWidget(close)
        layout.addLayout(actions)


class AchievementHistoryDialog(AnimatedDialog):
    """Older scales stay visible without turning them into new achievements."""

    def __init__(self, report, theme="light", parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Historique des succès'))
        self.resize(700, 540)
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(14)
        layout.addWidget(_label(tr('Tes étapes précédentes.'), "dialogTitle"))
        total = report.get("legacy_count", 0)
        points = report.get("legacy_points", 0)
        layout.addWidget(_label(tr('{count} récompense(s) conservée(s) · {points} XP inclus dans ton niveau.', count=_count(total), points=_count(points))))
        layout.addWidget(_label(tr('Ces succès ont été obtenus avec les anciens barèmes. Ils restent acquis ; les nouveaux paliers ont leur propre progression.')))
        awards = report.get("legacy_awards", [])[:100]
        self.table = QTableWidget(len(awards), 4)
        self.table.setAccessibleName(tr('Succès obtenus avec les anciens barèmes'))
        self.table.setHorizontalHeaderLabels((tr('Succès'), tr('Palier'), tr('Obtenu le'), "XP"))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            self.table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        for row, award in enumerate(awards):
            title = award.get("title", "")
            if award.get("period_label"):
                title += f"\n{award['period_label']}"
            elif award.get("target") is not None and award.get("unit"):
                title += tr('\nAncien objectif : {v0}', v0=_amount(award['target'], award['unit']))
            values = (title, award.get("tier") or tr('Quête'),
                      _date(award.get("earned_at")), _count(award.get("points", 0)))
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value))
                if column == 3:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row, column, item)
        self.table.horizontalHeader().sectionResized.connect(
            lambda column, *_: self.table.resizeRowsToContents() if column == 0 else None)
        self.table.resizeRowsToContents()
        layout.addWidget(self.table, 1)
        self.history_hint = _label(tr('Les {v0} récompenses les plus récentes sont affichées sur {v1} conservées.', v0=len(awards), v1=_count(total)) if total > len(awards)
                                   else tr('Toutes tes récompenses des anciens barèmes sont affichées.'))
        layout.addWidget(self.history_hint)
        actions = QHBoxLayout()
        actions.addStretch()
        close = button(tr("Fermer"), self.accept, primary=True)
        close.setDefault(True)
        actions.addWidget(close)
        layout.addLayout(actions)


class AchievementPanel(QWidget):
    """Stable widgets consume read-only snapshots; earning is owned by the app."""

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.report = {}
        self._closed = False
        self._theme = None
        self._pending_celebration = False
        self._build_ui()
        self.set_theme(ctx.theme)

    def _build_ui(self):
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.outer.setSpacing(18)
        self.outer.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        self.celebration_card = Card()
        self.celebration_card.setObjectName("AchievementCelebration")
        self.celebration_card.body.setContentsMargins(20, 14, 20, 14)
        announcement = QHBoxLayout()
        self.celebration_text = _label("", "cardTitle")
        self.celebration_text.setAccessibleName(tr('Nouveaux succès'))
        announcement.addWidget(self.celebration_text, 1)
        dismiss = button(tr("Fermer"), self.celebration_card.hide)
        dismiss.setAccessibleName(tr("Fermer l'annonce des nouveaux succès"))
        announcement.addWidget(dismiss)
        self.celebration_card.body.addLayout(announcement)
        self.celebration_card.hide()
        self.outer.addWidget(self.celebration_card)

        self.hero = Card()
        self.hero.setObjectName("AchievementHero")
        self.hero.body.setContentsMargins(28, 22, 24, 24)
        top = QHBoxLayout()
        top.setSpacing(20)
        text = QVBoxLayout()
        text.setSpacing(9)
        self.level_label = _label(tr('NIVEAU 1'), "eyebrow")
        text.addWidget(self.level_label)
        self.hero_title = ReflectiveTitle(tr('Chaque effort\nlaisse une trace.'))
        self.hero_title.setWordWrap(True)
        self.hero_title.setMinimumWidth(0)
        self.hero_title.setStyleSheet("font-size:32px;font-weight:700;letter-spacing:-1px;")
        text.addWidget(self.hero_title)
        self.hero_caption = _label(tr('Des petits pas aux grandes étapes. Ta collection grandit avec toi.'))
        text.addWidget(self.hero_caption)
        self.hero_stats = _label("", "cardTitle")
        text.addWidget(self.hero_stats)
        self.level_progress = _bar()
        self.level_progress.setAccessibleName(tr('Progression vers le prochain niveau'))
        text.addWidget(self.level_progress)
        self.level_hint = _label()
        text.addWidget(self.level_hint)
        top.addLayout(text, 1)
        art = QVBoxLayout()
        art.setSpacing(0)
        self.hero_figure = BadgeFigure(locked=True)
        self.hero_figure.setFixedSize(224, 196)
        art.addWidget(self.hero_figure, 0, Qt.AlignmentFlag.AlignCenter)
        self.hero_medal_name = _label(tr("La première médaille t'attend."))
        self.hero_medal_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hero_medal_name.setMaximumWidth(230)
        art.addWidget(self.hero_medal_name)
        top.addLayout(art)
        self.hero.body.addLayout(top)
        self.legacy_info = QWidget()
        legacy_row = QHBoxLayout(self.legacy_info)
        legacy_row.setContentsMargins(0, 12, 0, 0)
        legacy_row.setSpacing(18)
        self.legacy_caption = _label()
        legacy_row.addWidget(self.legacy_caption, 1)
        self.history_button = button(tr("Voir l'historique  →"), self.show_history)
        self.history_button.setProperty("role", "link")
        self.history_button.setAccessibleName(tr('Voir les succès obtenus avec les anciens barèmes'))
        legacy_row.addWidget(self.history_button)
        self.legacy_info.hide()
        self.hero.body.addWidget(self.legacy_info)
        self.outer.addWidget(self.hero)

        self.outer.addWidget(_label(tr('Tes quêtes du moment.'), "sectionTitle"))
        self.outer.addWidget(_label(tr('Des rendez-vous simples pour avancer régulièrement. Chaque quête rapporte ses XP une seule fois par période.')))
        self.quest_grid = QGridLayout()
        self.quest_grid.setSpacing(14)
        self.quest_cards = []
        self.quest_grid.setColumnStretch(0, 1)
        self.quest_grid.setColumnStretch(1, 1)
        self.outer.addLayout(self.quest_grid)

        collection_top = QHBoxLayout()
        collection_top.addWidget(_label(tr('Ta collection.'), "sectionTitle"), 1)
        self.collection_count = _label("", "badge")
        collection_top.addWidget(self.collection_count)
        self.outer.addLayout(collection_top)
        self.outer.addWidget(_label(tr('Bronze, Argent, Or, Platine, Diamant. Cinq paliers, des médailles de plus en plus précieuses.')))
        family_grid = QGridLayout()
        family_grid.setSpacing(14)
        self.family_cards = {}
        for index, family_id in enumerate(_FAMILY_AXES):
            card = _FamilyCard(family_id, self.show_details)
            self.family_cards[family_id] = card
            family_grid.addWidget(card, index // 2, index % 2)
        family_grid.setColumnStretch(0, 1)
        family_grid.setColumnStretch(1, 1)
        self.outer.addLayout(family_grid)

        self.note = _label(tr("Les activités réalisées du journal comptent, cours inclus. Les activités prévues ne comptent pas. Tes succès et tes XP restent acquis après une correction. Ils suivent tes sauvegardes : pense à sauvegarder avant de changer d'appareil."))
        self.outer.addWidget(self.note)

    def refresh(self, report=None):
        if self._closed:
            return
        if report is None:
            if hasattr(self.ctx, "achievement_report"):
                report = self.ctx.achievement_report()
            else:
                from . import achievements
                report = achievements.snapshot(self.ctx.db)
        self.report = report
        self.set_theme(self.ctx.theme)
        points = int(report.get("points", 0))
        level = int(report.get("level", 1 + points // 500))
        label = report.get("level_label", tr("Un pas après l'autre"))
        self.level_label.setText(tr('NIVEAU {v0} · {v1}', v0=level, v1=label).upper())
        count, total = report.get("earned_count", 0), report.get("total_count", len(_FAMILY_AXES) * 5)
        self.hero_stats.setText(tr('{v0} XP  ·  {v1} / {v2} médailles', v0=_count(points), v1=count, v2=total))
        self.collection_count.setText(f"{count} / {total}")
        legacy_count = report.get("legacy_count", 0)
        self.legacy_info.setVisible(legacy_count > 0)
        if legacy_count:
            self.legacy_caption.setText(tr("Anciens barèmes : {v0} récompense{v1} et {v2} XP conservés. De nouveaux paliers t'attendent dans la collection.", v0=_count(legacy_count), v1='s' if legacy_count != 1 else '', v2=_count(report.get('legacy_points', 0))))
        floor = report.get("level_floor", (level - 1) * 500)
        next_points = report.get("next_level_points", level * 500)
        _progress(self.level_progress, points - floor, next_points - floor)
        self.level_hint.setText(tr('Encore {v0} XP pour le niveau {v1}.', v0=_count(max(0, next_points - points)), v1=level + 1))
        families = report.get("families", [])
        visible_ids = {family.get("id") for family in families}
        for family_id, card in self.family_cards.items():
            card.setVisible(family_id in visible_ids)
        earned = []
        for family in families:
            card = self.family_cards.get(family.get("id"))
            if card:
                card.render(family)
            for index, tier in enumerate(family.get("tiers", [])):
                if tier.get("earned_at"):
                    earned.append((index, tier.get("earned_at"), family, tier))
        if earned:
            index, _, family, tier = max(earned, key=lambda item: (item[0], item[1]))
            self.hero_figure.set_badge(index, family["id"], False)
            self.hero_medal_name.setText(f"{tier['name']} · {family['title']}")
            self.hero_caption.setText(tr("Tes efforts s'accumulent. Tes récompenses restent."))
        else:
            self.hero_figure.set_badge(0, "work_total", True)
            self.hero_medal_name.setText(tr("La première médaille t'attend."))
            self.hero_caption.setText(tr('Des petits pas aux grandes étapes. Ta collection grandit avec toi.'))
        quests = report.get("quests", [])
        # Allocate only when the catalogue grows. Refreshes and period changes
        # update existing cards instead of replacing their widget trees.
        while len(self.quest_cards) < len(quests):
            index = len(self.quest_cards)
            card = _QuestCard(index)
            self.quest_cards.append(card)
            self.quest_grid.addWidget(card, index // 2, index % 2)
            card.set_theme(self.ctx.theme)
        for index, card in enumerate(self.quest_cards):
            card.setVisible(index < len(quests))
            if index < len(quests):
                card.render(quests[index])

    def set_theme(self, theme=None):
        theme = theme or self.ctx.theme
        if self._theme == theme:
            return
        self._theme = theme
        dark = theme == "dark"
        colors = palette_for(theme)
        start, middle, end = ("#123C71", "#3D286C", "#602548") if dark else ("#CCE8FF", "#E5D5FF", "#FFDCDB")
        border = "#B798FF" if dark else "#A581EE"
        self.hero.setStyleSheet(f"QFrame#AchievementHero {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {start},stop:.58 {middle},stop:1 {end});border:1px solid {border};border-radius:26px;}}")
        self.celebration_card.setStyleSheet(f"QFrame#AchievementCelebration {{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {colors['accent_soft']},stop:1 {axis_palette('sleep', theme)['tint']});border:1px solid {colors['accent']};border-radius:20px;}}")
        self.celebration_text.setStyleSheet(f"color:{colors['accent']};font-size:17px;font-weight:600;")
        self.level_progress.setStyleSheet(f"QProgressBar {{background:{colors['border']};border:none;border-radius:3px;}} QProgressBar::chunk {{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #358BFF,stop:.5 #A661F5,stop:1 #F15AB8);border-radius:3px;}}")
        for card in self.quest_cards:
            card.set_theme(theme)
        for card in self.family_cards.values():
            card.set_theme(theme)
        self.hero_figure.update()

    def celebrate(self, awards):
        if self._closed or not awards:
            return
        points = sum(int(item.get("points", 0)) for item in awards)
        if len(awards) == 1:
            item = awards[0]
            title = item.get("title", tr('Nouveau succès'))
            tier = item.get("tier")
            suffix = f" · {tier}" if tier else ""
            text = tr("{v0}{v1} : c'est à toi !  +{v2} XP", v0=title, v1=suffix, v2=_count(points))
        else:
            text = tr('{v0} nouvelles récompenses. Un beau cap franchi !  +{v1} XP', v0=len(awards), v1=_count(points))
        self.celebration_text.setText(text)
        self.celebration_card.show()
        if self.isVisible():
            self.hero_figure.celebrate()
        else:
            self._pending_celebration = True

    def show_details(self, family_id):
        family = next((item for item in self.report.get("families", []) if item.get("id") == family_id), None)
        if family and not self._closed:
            dialog = AchievementDetailsDialog(family, self.ctx.theme, self)
            dialog.exec()
            dialog.deleteLater()

    def show_history(self):
        if not self._closed and self.report.get("legacy_count", 0):
            dialog = AchievementHistoryDialog(self.report, self.ctx.theme, self)
            dialog.exec()
            dialog.deleteLater()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_celebration and not self._closed:
            self._pending_celebration = False
            self.hero_figure.celebrate()

    def shutdown(self):
        self._closed = True
        self._pending_celebration = False
        for figure in self.findChildren(BadgeFigure):
            figure._reset_motion()
        for animation in self.findChildren(QAbstractAnimation):
            animation.stop()
