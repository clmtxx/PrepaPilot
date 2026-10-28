"""Keep a focus session within reach while browsing the study workspace."""
import math
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from .i18n import tr
from .theme import palette_for
from .widgets import button


class _ElidedLabel(QLabel):
    """Keep arbitrary personal titles from pushing the session controls away."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = ''
        self.setTextFormat(Qt.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def set_full_text(self, text):
        if text != self.full_text:
            self.full_text = text
            self.setToolTip(text)
            self.setAccessibleName(text)
            self._elide()

    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideRight, max(0, self.width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._elide()


class FocusSessionBar(QFrame):
    """A passive view of the dashboard's session; it owns no clock or journal.

    The window refreshes this view after a focus tick, an action or navigation.
    Hiding the bar never pauses work, and callbacks are triggered only by input.
    """
    def __init__(self, ctx, on_return, on_toggle, on_review, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._callbacks = (on_return, on_toggle, on_review)
        self._session = None
        self._metadata_key = None
        self._last_action_at = float('-inf')
        self._requested_visible = False
        self.has_session = False
        self.setObjectName('FocusSessionBar')
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 7, 14, 7)
        row.setSpacing(12)
        self.time_label = QLabel('25:00', objectName='focusBarTime')
        self.time_label.setTextFormat(Qt.PlainText)
        self.time_label.setAlignment(Qt.AlignCenter)
        self.time_label.setFixedWidth(72)
        row.addWidget(self.time_label)
        copy = QWidget()
        copy.setMinimumWidth(0)
        copy.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        labels = QVBoxLayout(copy)
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(2)
        self.status_label = QLabel(objectName='focusBarStatus')
        self.status_label.setTextFormat(Qt.PlainText)
        self.context_label = _ElidedLabel()
        labels.addWidget(self.status_label)
        labels.addWidget(self.context_label)
        row.addWidget(copy, 1)
        self.return_button = button(tr('Retrouver ma séance'), self._return)
        self.return_button.setToolTip(tr('Revenir à la séance sur l’accueil'))
        self.toggle_button = button(tr('Pause'), self._toggle, primary=True)
        self.review_button = button(tr('Voir le bilan'), self._review, primary=True)
        for action in (self.return_button, self.toggle_button, self.review_button):
            action.setFixedHeight(32)
            row.addWidget(action)
        ctx.theme_changed.connect(self._apply_palette)
        ctx.watch_data(self._invalidate_metadata, 'subjects')
        self._apply_palette()
        self.hide()

    def _apply_palette(self, *_):
        colors = palette_for(self.ctx.theme)
        self.setStyleSheet(
            f'QFrame#FocusSessionBar {{ background:{colors["accent_soft"]};'
            f'border:1px solid {colors["border"]};border-radius:14px; }}'
            f'QLabel#focusBarTime {{ color:{colors["accent"]};font-size:22px;font-weight:700; }}'
            f'QLabel#focusBarStatus {{ color:{colors["accent"]};font-size:10px;font-weight:700;letter-spacing:.8px; }}'
            'QPushButton { padding:3px 12px; }')

    def _invalidate_metadata(self):
        self._metadata_key = None
        if self._session is not None:
            self.refresh(self._session, visible=self._requested_visible)

    def refresh(self, session, visible=True):
        self._session = session
        self._requested_visible = visible
        status = session.status if session is not None else 'idle'
        self.has_session = status in ('running', 'paused', 'review')
        self.setVisible(self.has_session and visible)
        if not self.has_session:
            return
        state = session.state
        metadata = (state.get('category'), state.get('title', ''))
        if metadata != self._metadata_key:
            self._metadata_key = metadata
            category, title = metadata
            subject = self.ctx.db.category_labels(include_archived=True).get(category, tr('Minuteur libre'))
            self.context_label.set_full_text(f'{subject} · {title}' if title else subject)
        measured = session.elapsed_seconds if status == 'review' else session.remaining_seconds
        minutes, seconds = divmod(max(0, math.ceil(measured)), 60)
        clock = f'{minutes:02d}:{seconds:02d}'
        if self.time_label.text() != clock:
            self.time_label.setText(clock)
        description = tr('Temps de concentration réalisé : {time}', time=clock) if status == 'review' else tr('Temps de concentration restant : {time}', time=clock)
        if self.time_label.accessibleName() != description:
            self.time_label.setAccessibleName(description)
        captions = {
            'running': tr('SÉANCE EN COURS'),
            'paused': tr('SÉANCE EN PAUSE'),
            'review': tr('BILAN À VÉRIFIER'),
        }
        self.status_label.setText(captions[status])
        self.setAccessibleName(tr('Ta séance reste disponible dans tous les espaces'))
        self.toggle_button.setVisible(status != 'review')
        self.review_button.setVisible(status == 'review')
        self.toggle_button.setText(tr('Reprendre') if status == 'paused' else tr('Pause'))
        self.toggle_button.setAccessibleName(tr('Reprendre la séance') if status == 'paused' else tr('Mettre la séance en pause'))
        self.review_button.setAccessibleName(tr('Voir le bilan de la séance'))

    def _current(self):
        return self._session.status if self._session is not None else 'idle'

    def _return(self):
        if self._current() in ('running', 'paused', 'review'):
            self._callbacks[0]()

    def _toggle(self):
        # A rapid double click must not immediately undo a pause or resume.
        now = time.monotonic()
        if self._current() in ('running', 'paused') and now - self._last_action_at >= .35:
            self._last_action_at = now
            self._callbacks[1]()

    def _review(self):
        if self._current() == 'review':
            self._callbacks[2]()
