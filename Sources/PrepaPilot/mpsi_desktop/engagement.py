"""A factual, pressure-free weekly rhythm on the home page."""
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QSizePolicy, QVBoxLayout, QWidget

from .catalog import duration_text
from .i18n import format_date, qt_locale, tr
from .page_chrome import AccentCard
from .progression import load_targets
from .theme import palette_for
from .time_store import local_stamp
from .widgets import button


def weekly_momentum(db, today=None, *, now=None):
    """Read the local calendar once; never award points or create activities.

    Work follows the same category rules as Progression. Only completed entries
    ending before the cutoff contribute; an overnight entry is split at midnight.
    """
    now = db._time_now() if now is None else now
    today = now.date() if today is None else today
    if type(today) is not date or not isinstance(now, datetime) or now.tzinfo is not None:
        raise ValueError('Expected a local date and datetime')
    first = today - timedelta(days=today.weekday())
    start = datetime.combine(first, time())
    end = min(now, datetime.combine(today + timedelta(days=1), time()), start + timedelta(days=7))
    days = [dict(day=first + timedelta(days=index), work_minutes=0, recovery_minutes=0,
                 future=first + timedelta(days=index) > min(today, now.date())) for index in range(7)]
    study = db.study_categories() | {'ds', 'cpge', 'permanence'}
    sessions = 0
    for entry in db.list_time_entries(first.isoformat(), (first + timedelta(days=7)).isoformat()):
        if entry.get('deleted') or entry['status'] != 'completed':
            continue
        entry_start, entry_end = local_stamp(entry['start_at']), local_stamp(entry['end_at'])
        if entry_end > end or entry_start >= end or entry_end <= start:
            continue
        category = entry['category']
        metric = 'work_minutes' if category in study else 'recovery_minutes' if category in {'sport', 'eps', 'detente', 'sommeil'} else None
        if metric is None:
            continue
        counted = False
        for day in days:
            lower = datetime.combine(day['day'], time())
            upper = min(lower + timedelta(days=1), end)
            minutes = max(0, int((min(upper, entry_end) - max(lower, entry_start)).total_seconds() // 60))
            day[metric] += minutes
            counted = counted or minutes > 0
        if metric == 'work_minutes' and counted:
            sessions += 1
    return dict(days=days, work_minutes=sum(day['work_minutes'] for day in days),
                active_days=sum(day['work_minutes'] > 0 for day in days), sessions=sessions,
                target=load_targets(db)['work'], today=today)


class MomentumCard(AccentCard):
    """Seven calendar marks and one useful next step, backed by the journal."""

    def __init__(self, ctx, navigate, on_focus, parent=None):
        super().__init__(ctx, 'home', parent)
        self.navigate, self.on_focus = navigate, on_focus
        self.summary = None
        top = QHBoxLayout()
        self.heading = QLabel(tr('TON ÉLAN DE LA SEMAINE'), objectName='colorEyebrow')
        top.addWidget(self.heading)
        top.addStretch()
        self.progression_button = button(tr('Voir ma progression  →'), lambda: self.navigate('progression'))
        self.progression_button.setProperty('role', 'link')
        top.addWidget(self.progression_button)
        self.body.addLayout(top)

        center = QHBoxLayout()
        center.setSpacing(24)
        summary = QVBoxLayout()
        summary.setSpacing(3)
        self.total_label = QLabel(objectName='statValue')
        self.total_label.setStyleSheet('font-size:30px;font-weight:700;letter-spacing:-.5px;')
        summary.addWidget(self.total_label)
        self.days_label = QLabel(objectName='muted')
        self.days_label.setWordWrap(True)
        summary.addWidget(self.days_label)
        center.addLayout(summary, 2)
        self.day_cells = []
        for _ in range(7):
            cell = QWidget()
            cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            layout = QVBoxLayout(cell)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(6)
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            marker = QLabel()
            marker.setFixedSize(34, 34)
            marker.setAlignment(Qt.AlignCenter)
            duration = QLabel()
            duration.setAlignment(Qt.AlignCenter)
            layout.addWidget(label, 0, Qt.AlignHCenter)
            layout.addWidget(marker, 0, Qt.AlignHCenter)
            layout.addWidget(duration, 0, Qt.AlignHCenter)
            center.addWidget(cell, 1)
            self.day_cells.append((cell, label, marker, duration))
        self.body.addLayout(center)

        self.goal_label = QLabel(objectName='muted')
        self.goal_label.setWordWrap(True)
        self.body.addWidget(self.goal_label)
        self.goal_bar = QProgressBar()
        self.goal_bar.setRange(0, 1000)
        self.goal_bar.setTextVisible(False)
        self.goal_bar.setFixedHeight(7)
        self.body.addWidget(self.goal_bar)

        bottom = QHBoxLayout()
        bottom.setSpacing(18)
        self.encouragement = QLabel(objectName='muted')
        self.encouragement.setWordWrap(True)
        bottom.addWidget(self.encouragement, 1)
        self.focus_action = button(tr('Commencer une séance'), self.on_focus, primary=True)
        bottom.addWidget(self.focus_action)
        self.body.addLayout(bottom)
        ctx.theme_changed.connect(self._render)
        self.refresh()

    def refresh(self, today=None):
        self.summary = weekly_momentum(self.ctx.db, today)
        self._render()

    def sync_focus_state(self):
        """Keep the next action truthful without adding another timer."""
        session = getattr(self.ctx, '_live_focus_session', None)
        status = session.status if session is not None else 'idle'
        text = {'running': tr('Retrouver ma séance'), 'paused': tr('Reprendre'),
                'review': tr('Voir le bilan')}.get(status, tr('Commencer une séance'))
        if self.focus_action.text() != text:
            self.focus_action.setText(text)

    def _render(self, *_):
        if self.summary is None:
            return
        data = self.summary
        colors = palette_for(self.ctx.theme)
        self.total_label.setText(duration_text(data['work_minutes']))
        if data['active_days'] == 0:
            caption = tr('de travail renseigné cette semaine')
        elif data['active_days'] == 1:
            caption = tr('sur 1 jour de travail renseigné')
        else:
            caption = tr('sur {count} jours de travail renseignés', count=data['active_days'])
        self.days_label.setText(caption)
        for day, (cell, label, marker, duration) in zip(data['days'], self.day_cells):
            value = day['day']
            stamp = QDate(value.year, value.month, value.day)
            label.setText(qt_locale().toString(stamp, 'ddd').rstrip('.'))
            label.setStyleSheet(f"font-size:11px;color:{colors['muted']};")
            duration.setText(duration_text(day['work_minutes']) if day['work_minutes'] else '–')
            duration.setStyleSheet(f"font-size:10px;color:{colors['muted']};")
            if day['future']:
                text, description, color, background = '·', tr('À venir'), colors['muted'], colors['surface2']
            elif day['work_minutes']:
                text, description, color, background = '✓', tr('{duration} de travail renseigné', duration=duration_text(day['work_minutes'])), colors['green'], colors['surface2']
            elif day['recovery_minutes']:
                text, description, color, background = '○', tr('Récupération renseignée'), colors['accent'], colors['accent_soft']
            else:
                text, description, color, background = '–', tr('Aucun travail ni récupération renseignés'), colors['muted'], colors['surface2']
            border = colors['accent'] if value == data['today'] else colors['border']
            marker.setText(text)
            marker.setStyleSheet(f'background:{background};color:{color};border:1px solid {border};border-radius:17px;font-size:18px;font-weight:700;')
            info = f"{format_date(value, 'long')} · {description}"
            if value == data['today']:
                info += ' · ' + tr('Aujourd’hui')
            cell.setToolTip(info)
            cell.setAccessibleName(info)
            marker.setAccessibleName(info)
        target = data['target']
        self.goal_label.setVisible(bool(target))
        self.goal_bar.setVisible(bool(target))
        if target:
            reached = data['work_minutes'] >= target
            self.goal_label.setText(tr('Ton objectif hebdomadaire : {done} / {target}', done=duration_text(data['work_minutes']), target=duration_text(target)))
            self.goal_bar.setValue(min(1000, int(data['work_minutes'] * 1000 / target)))
            self.goal_bar.setAccessibleName(self.goal_label.text())
            self.goal_bar.setStyleSheet(f"QProgressBar {{background:{colors['surface2']};border:0;border-radius:3px;}} QProgressBar::chunk {{background:{colors['green'] if reached else colors['accent']};border-radius:3px;}}")
        if target and data['work_minutes'] >= target:
            message = tr('Ton objectif est atteint. Prends aussi le temps de souffler.')
        elif data['work_minutes']:
            message = tr('Chaque pas compte. Une pause fait aussi partie du chemin.')
        else:
            message = tr('Une petite séance suffit pour commencer. Garde aussi du temps pour toi.')
        self.encouragement.setText(message)
        self.sync_focus_state()
