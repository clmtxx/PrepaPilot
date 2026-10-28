"""Bounded, read-only discovery across the user's local study workspace."""
from __future__ import annotations

import json
import sqlite3

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QLabel,
                              QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout)

from .i18n import format_date, format_number, tr
from .icons import icon
from .quick_actions import search_text
from .theme import palette_for
from .widgets import AnimatedDialog, button


KINDS = ('document', 'grade', 'memory')
MAX_RESULTS = 40


def _single_line(value):
    return ' '.join(str(value or '').split())


def _memory_text(value):
    try:
        value = json.loads(value)
    except (TypeError, ValueError):
        pass
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


def find_results(ctx, query, limit=MAX_RESULTS, *, kind=None):
    """Return at most ``limit`` matches, ranked by title and then content.

    SQLite performs matching in the database and returns a bounded candidate set
    per type. No document file is opened and no persistent search index or setting
    is written. A brief connection-local function provides Unicode matching.
    """
    needle = ' '.join(search_text(str(query)[:160]).split())
    if not needle:
        return []
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Expected a search result limit between 1 and 100')
    if kind is not None and kind not in KINDS:
        raise ValueError('Unsupported search result kind')
    terms = tuple(needle.split())
    db = ctx.db
    subjects = db.subject_labels(include_archived=True)

    def score(title, secondary, content):
        title, secondary, content = (search_text(str(value or '')) for value in (title, secondary, content))
        combined = f'{title} {secondary} {content}'
        if not all(term in combined for term in terms):
            return 0
        if needle == title.strip():
            return 100
        if title.startswith(needle):
            return 85
        if all(term in title for term in terms):
            return 70
        return 25 + sum(term in title for term in terms) * 3 + sum(term in secondary for term in terms)

    rows = []
    # Hold the existing re-entrant database lock until temporary functions have
    # been removed, so background imports cannot observe a partially set up query.
    with db._lock:
        connection = db._connection
        connection.create_function('pp_global_score', 3, score, deterministic=True)
        connection.create_function('pp_global_subject', 1, lambda value: subjects.get(value, value or ''), deterministic=True)
        try:
            if kind in (None, 'document'):
                documents = db._rows('''
                    SELECT id,title,original_name,subject,description,created_at,
                        pp_global_score(title,original_name || ' ' || pp_global_subject(subject),description) AS relevance
                    FROM documents WHERE relevance>0
                    ORDER BY relevance DESC,created_at DESC,id DESC LIMIT ?
                ''', (limit + 1,))
                for row in documents:
                    rows.append(dict(kind='document', id=row['id'], title=row['title'] or row['original_name'],
                                     subtitle=tr('Document · {subject} · {name}', subject=subjects.get(row['subject'], row['subject']), name=row['original_name']),
                                     relevance=row['relevance'], stamp=row['created_at']))
            if kind in (None, 'grade'):
                year = ctx.year
                grades = db._rows('''
                    SELECT id,label,subject,kind,score,scale,graded_on,
                        pp_global_score(label,pp_global_subject(subject),kind || ' ' || graded_on) AS relevance
                    FROM grades WHERE graded_on>=? AND graded_on<? AND relevance>0
                    ORDER BY relevance DESC,graded_on DESC,id DESC LIMIT ?
                ''', (f'{year}-08-01', f'{year+1}-08-01', limit + 1))
                for row in grades:
                    rows.append(dict(kind='grade', id=row['id'], title=row['label'] or tr('Évaluation sans titre'),
                                     subtitle=tr('Note · {subject} · {score}/{scale} · {date}',
                                                 subject=subjects.get(row['subject'], row['subject']), score=format_number(row['score']),
                                                 scale=format_number(row['scale']), date=format_date(row['graded_on'])),
                                     relevance=row['relevance'], stamp=row['graded_on']))
            if kind in (None, 'memory'):
                memories = db._rows('''
                    SELECT key,value,pp_global_score(key,'',value) AS relevance
                    FROM memories WHERE relevance>0 ORDER BY relevance DESC,key COLLATE NOCASE LIMIT ?
                ''', (limit + 1,))
                for row in memories:
                    rows.append(dict(kind='memory', key=row['key'], title=row['key'],
                                     subtitle=tr('Repère · {text}', text=_single_line(_memory_text(row['value']))[:150]),
                                     relevance=row['relevance'], stamp=''))
        finally:
            connection.create_function('pp_global_score', 3, None)
            connection.create_function('pp_global_subject', 1, None)
    # Sort recency within each type, then keep a stable type order on equal rank.
    rows.sort(key=lambda row: (row['stamp'], str(row.get('id', row.get('key', '')))), reverse=True)
    rows.sort(key=lambda row: (-row['relevance'], KINDS.index(row['kind'])))
    return rows[:limit]


class GlobalSearchDialog(AnimatedDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.selected_result = None
        self.setWindowTitle(tr('Rechercher dans mon espace'))
        self.setWindowModality(Qt.WindowModal)
        self.resize(640, 570)
        self.setMinimumSize(430, 400)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)
        title = QLabel(tr('Retrouve ce qui compte.'), objectName='dialogTitle')
        title.setWordWrap(True)
        layout.addWidget(title)
        caption = QLabel(tr('Documents, notes et repères, réunis dans une recherche locale.'), objectName='muted')
        caption.setWordWrap(True)
        layout.addWidget(caption)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Un titre, une matière, un mot-clé…'))
        self.search.setAccessibleName(tr('Rechercher dans mon espace'))
        self.search.setClearButtonEnabled(True)
        self.search.setMaxLength(160)
        self.search.installEventFilter(self)
        row.addWidget(self.search, 1)
        self.kind_filter = QComboBox()
        self.kind_filter.setAccessibleName(tr('Type de résultat'))
        for label, kind in ((tr('Tout'), None), (tr('Documents'), 'document'), (tr('Notes'), 'grade'), (tr('Mes repères'), 'memory')):
            self.kind_filter.addItem(label, kind)
        row.addWidget(self.kind_filter)
        layout.addLayout(row)
        self.scope = QLabel(tr('Les notes correspondent à l’année scolaire sélectionnée.'), objectName='muted')
        self.scope.setWordWrap(True)
        self.scope.setStyleSheet('font-size:11px;')
        layout.addWidget(self.scope)
        self.results = QListWidget()
        self.results.setAccessibleName(tr('Résultats de la recherche'))
        self.results.setSelectionMode(QAbstractItemView.SingleSelection)
        self.results.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.results.setTextElideMode(Qt.ElideRight)
        self.results.setIconSize(QSize(22, 22))
        self.results.itemActivated.connect(self.activate_selected)
        self.results.itemClicked.connect(self.activate_selected)
        layout.addWidget(self.results, 1)
        self.empty = QLabel(objectName='muted')
        self.empty.setTextFormat(Qt.PlainText)
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        footer = QHBoxLayout()
        self.result_count = QLabel(objectName='muted')
        self.result_count.setWordWrap(True)
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
            'QListWidget::item { padding:10px 12px; border:1px solid transparent; }'
            f'QListWidget::item:selected {{ background:{colors["accent_soft"]}; border-color:{colors["accent"]}; }}'
            f'QListWidget::item:hover {{ background:{colors["surface2"]}; }}')
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(180)
        self.search_timer.timeout.connect(self.run_search)
        self.search.textChanged.connect(self._query_changed)
        self.kind_filter.currentIndexChanged.connect(self._query_changed)
        self.search.returnPressed.connect(self._submit)
        self._query_changed()

    def showEvent(self, event):
        super().showEvent(event)
        self.search.setFocus(Qt.OtherFocusReason)

    def _query_changed(self, *_):
        self.search_timer.stop()
        self.results.clear()
        self.open_button.setEnabled(False)
        self.result_count.clear()
        self.empty.show()
        if not search_text(self.search.text()).strip():
            self.empty.setText(tr('Saisis un mot pour retrouver un document, une note ou un repère.'))
        else:
            self.empty.setText(tr('Recherche dans ton espace…'))
            self.search_timer.start()

    def run_search(self):
        self.search_timer.stop()
        self.results.clear()
        try:
            rows = find_results(self.ctx, self.search.text(), kind=self.kind_filter.currentData())
        except (sqlite3.Error, ValueError, OSError):
            self.empty.setText(tr('La recherche n’a pas pu aboutir. Ferme cette fenêtre puis réessaie.'))
            self.empty.show()
            self.open_button.setEnabled(False)
            self.result_count.clear()
            return
        colors = palette_for(self.ctx.theme)
        for result in rows:
            title, subtitle = _single_line(result['title']), _single_line(result['subtitle'])
            symbol = {'document': 'book', 'grade': 'chart', 'memory': 'memory'}[result['kind']]
            item = QListWidgetItem(icon(symbol, colors['accent']), f'{title}\n{subtitle}')
            item.setData(Qt.UserRole, result)
            item.setToolTip(title + '\n' + subtitle)
            item.setSizeHint(QSize(0, 66))
            self.results.addItem(item)
        if rows:
            self.results.setCurrentRow(0)
        self.empty.setText(tr('Aucun résultat. Essaie un autre mot ou élargis le filtre.'))
        self.empty.setVisible(not rows)
        self.open_button.setEnabled(bool(rows))
        self.result_count.setText(tr('{count} résultat(s)', count=len(rows)) if len(rows) < MAX_RESULTS
                                  else tr('{count} résultats affichés · affine ta recherche', count=MAX_RESULTS))

    def _submit(self):
        if self.search_timer.isActive():
            self.run_search()
        self.activate_selected()

    def eventFilter(self, watched, event):
        if watched is self.search and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Up, Qt.Key_Down):
            if self.search_timer.isActive():
                self.run_search()
            if self.results.count():
                step = 1 if event.key() == Qt.Key_Down else -1
                row = min(self.results.count() - 1, max(0, self.results.currentRow() + step))
                self.results.setCurrentRow(row)
                self.results.scrollToItem(self.results.currentItem())
            return True
        return super().eventFilter(watched, event)

    def activate_selected(self, *_):
        selected = self.results.currentItem()
        if selected is not None and self.selected_result is None:
            self.selected_result = dict(selected.data(Qt.UserRole))
            self.accept()

    def done(self, result):
        self.search_timer.stop()
        super().done(result)
