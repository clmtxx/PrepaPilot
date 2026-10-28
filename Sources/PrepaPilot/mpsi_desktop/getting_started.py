"""Optional first steps that reflect saved data, without a separate task store."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QProgressBar

from .i18n import tr
from .page_chrome import AccentCard
from .theme import palette_for
from .widgets import button


class GettingStartedCard(AccentCard):
    def __init__(self, ctx, navigate, add_document, add_grade, start_focus, parent=None):
        super().__init__(ctx, 'settings', parent)
        self.navigate = navigate
        self.actions = (add_document, add_grade, start_focus)
        self.completed = (False, False, False)
        heading = QHBoxLayout()
        self.title = QLabel(objectName='sectionTitle')
        self.title.setWordWrap(True)
        heading.addWidget(self.title, 1)
        self.counter = QLabel(objectName='badge')
        heading.addWidget(self.counter)
        self.body.addLayout(heading)
        self.caption = QLabel(objectName='muted')
        self.caption.setWordWrap(True)
        self.body.addWidget(self.caption)
        self.progress = QProgressBar()
        self.progress.setRange(0, 3)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setAccessibleName(tr('Découverte de ton espace'))
        self.body.addWidget(self.progress)
        self.labels, self.buttons = [], []
        for index in range(3):
            row = QHBoxLayout()
            label = QLabel()
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            row.addWidget(label, 1)
            action = button('', lambda checked=False, i=index: self.activate(i))
            row.addWidget(action)
            self.labels.append(label)
            self.buttons.append(action)
            self.body.addLayout(row)
        self.body.addStretch()
        backup = button(tr('Sauvegarder mon espace  →'), lambda: navigate('settings'))
        backup.setProperty('role', 'link')
        self.body.addWidget(backup)
        ctx.theme_changed.connect(self._style_progress)
        self._style_progress()

    def _style_progress(self, *_):
        colors = palette_for(self.ctx.theme)
        self.progress.setStyleSheet(
            f'QProgressBar {{ background:{colors["surface2"]}; border:0; border-radius:3px; }}'
            f'QProgressBar::chunk {{ background:{colors["green"]}; border-radius:3px; }}')

    def refresh(self, *, documents, grades):
        categories = sorted(self.ctx.db.study_categories() | {'ds', 'cpge', 'permanence'})
        has_work = False
        if categories:
            placeholders = ','.join('?' for _ in categories)
            now = self.ctx.db._time_now().isoformat(timespec='minutes')
            has_work = bool(self.ctx.db._rows(
                "SELECT 1 FROM time_entries WHERE deleted=0 AND status='completed' AND source='manual' "
                f"AND category IN ({placeholders}) AND end_at<=? LIMIT 1", (*categories, now)))
        self.completed = (documents > 0, grades > 0, has_work)
        count = sum(self.completed)
        self.title.setText(tr('Ton espace est prêt.') if count == 3 else tr('Ton espace prend forme.'))
        self.caption.setText(tr('Tes essentiels sont à portée de main. Continue à ton rythme.') if count == 3
                             else tr('Trois idées à explorer, dans l’ordre qui te convient.'))
        self.counter.setText(f'{count}/3')
        self.counter.setAccessibleName(tr('{count} étapes découvertes sur 3', count=count))
        self.progress.setValue(count)
        pending = (tr('Ton premier document'), tr('Ta première note'), tr('Ta première séance'))
        done = (tr('Document ajouté'), tr('Note enregistrée'), tr('Séance réalisée'))
        action = (tr('Importer'), tr('Ajouter'), tr('Démarrer'))
        destinations = (tr('Documents'), tr('Notes'), tr('Journal'))
        for index, completed in enumerate(self.completed):
            self.labels[index].setText(('✓  ' + done[index]) if completed else f'{index + 1}  ' + pending[index])
            self.buttons[index].setText(destinations[index] if completed else action[index])
            self.buttons[index].setAccessibleName(destinations[index] if completed else pending[index])

    def activate(self, index):
        if self.completed[index]:
            self.navigate(('documents', 'notes', 'time')[index])
        else:
            self.actions[index]()
