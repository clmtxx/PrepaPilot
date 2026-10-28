"""A small searchable launcher; opening it never changes application data."""
from dataclasses import dataclass
import unicodedata

from PySide6.QtCore import QEvent, QSize, Qt
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel, QLineEdit,
                              QListWidget, QListWidgetItem, QVBoxLayout)

from .i18n import tr
from .icons import icon
from .theme import palette_for
from .widgets import AnimatedDialog, button


@dataclass(frozen=True)
class QuickAction:
    key: str
    title: str
    description: str
    symbol: str = 'spark'
    keywords: str = ''


def search_text(value):
    """Match accents and punctuation without changing the displayed wording."""
    normalized = unicodedata.normalize('NFKD', value.casefold())
    return ''.join(char if char.isalnum() else ' ' for char in normalized
                   if not unicodedata.combining(char))


class QuickActionsDialog(AnimatedDialog):
    def __init__(self, ctx, actions, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.actions = tuple(actions)
        self.selected_key = None
        self.setWindowTitle(tr('Actions rapides'))
        self.setWindowModality(Qt.WindowModal)
        self.resize(600, 550)
        self.setMinimumSize(420, 420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)
        heading = QHBoxLayout()
        heading.addWidget(QLabel(tr('Que veux-tu faire ?'), objectName='dialogTitle'), 1)
        heading.addWidget(QLabel('Ctrl+K', objectName='badge'))
        layout.addLayout(heading)
        caption = QLabel(tr('Une recherche, un raccourci vers ton prochain pas.'), objectName='muted')
        caption.setWordWrap(True)
        layout.addWidget(caption)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Rechercher une action ou un espace…'))
        self.search.setAccessibleName(tr('Rechercher une action ou un espace'))
        self.search.setClearButtonEnabled(True)
        self.search.installEventFilter(self)
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setAccessibleName(tr('Actions disponibles'))
        self.results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setIconSize(QSize(21, 21))
        self.results.itemActivated.connect(self.activate_selected)
        self.results.itemClicked.connect(self.activate_selected)
        layout.addWidget(self.results, 1)
        self.empty = QLabel(tr('Aucun résultat. Essaie « note », « document » ou « temps ».'), objectName='muted')
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        footer = QHBoxLayout()
        self.result_count = QLabel(objectName='muted')
        footer.addWidget(self.result_count, 1)
        close = button(tr('Fermer'), self.reject)
        close.setAutoDefault(False)
        footer.addWidget(close)
        self.open_button = button(tr('Ouvrir  →'), self.activate_selected, primary=True)
        self.open_button.setAutoDefault(False)
        footer.addWidget(self.open_button)
        layout.addLayout(footer)
        keys = QLabel(tr('↑ ↓ Choisir · Entrée Ouvrir · Échap Fermer'), objectName='muted')
        keys.setWordWrap(True)
        keys.setStyleSheet('font-size:11px;')
        layout.addWidget(keys)
        colors = palette_for(ctx.theme)
        self.results.setStyleSheet(
            'QListWidget { padding:5px; }'
            f'QListWidget::item {{ padding:10px 12px; border:1px solid transparent; }}'
            f'QListWidget::item:selected {{ background:{colors["accent_soft"]}; border-color:{colors["accent"]}; }}'
            f'QListWidget::item:hover {{ background:{colors["surface2"]}; }}')
        self.search.textChanged.connect(self.filter_actions)
        self.search.returnPressed.connect(self.activate_selected)
        self.filter_actions('')

    def showEvent(self, event):
        super().showEvent(event)
        self.search.setFocus(Qt.OtherFocusReason)

    def filter_actions(self, query):
        terms = search_text(query).split()
        previous = self.results.currentItem()
        normalized = ' '.join(terms)
        previous_key = previous.data(Qt.UserRole) if previous and normalized == getattr(self, '_last_query', '') else None
        self._last_query = normalized
        self.results.clear()
        matches = []
        for order, action in enumerate(self.actions):
            haystack = search_text(f'{action.title} {action.description} {action.keywords}')
            if all(term in haystack for term in terms):
                title = ' '.join(search_text(action.title).split())
                rank = 0 if not terms or title == normalized else 1 if title.startswith(normalized) else 2 if all(term in title for term in terms) else 3
                matches.append((rank, order, action))
        for _, _, action in sorted(matches):
            item = QListWidgetItem(icon(action.symbol, palette_for(self.ctx.theme)['accent']),
                                   f'{action.title}\n{action.description}')
            item.setData(Qt.UserRole, action.key)
            item.setToolTip(action.description)
            item.setSizeHint(QSize(0, 64))
            self.results.addItem(item)
            if action.key == previous_key:
                self.results.setCurrentItem(item)
        count = self.results.count()
        if count and self.results.currentRow() < 0:
            self.results.setCurrentRow(0)
        self.empty.setVisible(not count)
        self.open_button.setEnabled(bool(count))
        self.result_count.setText(tr('{count} résultat(s)', count=count))

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Up, Qt.Key_Down):
                count = self.results.count()
                if count:
                    step = 1 if event.key() == Qt.Key_Down else -1
                    row = max(0, min(count - 1, self.results.currentRow() + step))
                    self.results.setCurrentRow(row)
                    self.results.scrollToItem(self.results.currentItem())
                return True
        return super().eventFilter(watched, event)

    def activate_selected(self, *_):
        selected = self.results.currentItem()
        if selected is not None and self.selected_key is None:
            self.selected_key = selected.data(Qt.UserRole)
            self.accept()
