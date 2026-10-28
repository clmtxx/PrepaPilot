"""Offline help and a deliberately small, non-personal support summary."""
import platform

from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QScrollArea,
                              QTabWidget, QVBoxLayout, QWidget)

from . import __version__
from .i18n import tr
from .widgets import AnimatedDialog, button


def technical_summary(ctx):
    """Only these five fields can reach the clipboard; never inspect the store."""
    return '\n'.join((f'PrépaPilot {__version__}',
                      f'OS: {platform.system()} {platform.release()}',
                      f'Qt: {qVersion()}',
                      f'Language: {ctx.language}', f'Theme: {ctx.theme}'))


def _text(value, name='muted'):
    label = QLabel(value, objectName=name)
    label.setTextFormat(Qt.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    return label


class HelpCenterDialog(AnimatedDialog):
    """Short guides remain usable at a small window size and without a network."""

    def __init__(self, ctx, on_navigate, parent=None):
        super().__init__(parent)
        self.ctx, self.on_navigate = ctx, on_navigate
        self.setWindowTitle(tr('Aide et raccourcis'))
        self.setWindowModality(Qt.WindowModal)
        self.resize(740, 570)
        self.setMinimumSize(560, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(14)
        heading = QHBoxLayout()
        heading.addWidget(_text(tr('Un coup de main, quand tu veux.'), 'dialogTitle'), 1)
        heading.addWidget(_text('F1', 'badge'))
        root.addLayout(heading)
        root.addWidget(_text(tr('Des repères simples pour profiter de ton espace d’études.')))
        self.tabs = QTabWidget()
        self.tabs.setAccessibleName(tr('Rubriques de l’aide'))
        self.tabs.setDocumentMode(True)
        root.addWidget(self.tabs, 1)
        self.pages = {}
        self.destination_buttons = {}
        self._start_page()
        self._shortcuts_page()
        self._data_page()
        self._about_page()
        bottom = QHBoxLayout()
        bottom.addWidget(_text(tr('Cette aide est disponible sans connexion.')), 1)
        close = button(tr('Fermer'), self.reject)
        close.setAutoDefault(False)
        bottom.addWidget(close)
        root.addLayout(bottom)

    def _page(self, key, title):
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setAccessibleName(title)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(4, 16, 14, 12)
        layout.setSpacing(16)
        scroll.setWidget(content)
        self.tabs.addTab(scroll, title)
        self.pages[key] = scroll
        return layout

    def _section(self, layout, title, body):
        copy = QVBoxLayout()
        copy.setSpacing(5)
        copy.addWidget(_text(title, 'sectionTitle'))
        copy.addWidget(_text(body))
        layout.addLayout(copy)

    def _destination(self, layout, label, key):
        action = button(label, lambda checked=False, target=key: self.open_space(target))
        action.setAutoDefault(False)
        self.destination_buttons[key] = action
        layout.addWidget(action, 0, Qt.AlignLeft)

    def _start_page(self):
        layout = self._page('start', tr('Débuter'))
        self._section(layout, tr('1 · Retrouve tes cours'),
                      tr('Ajoute tes fichiers dans Documents. Range-les par dossier, matière ou type, puis retrouve-les avec la recherche. L’original reste à sa place.'))
        self._destination(layout, tr('Découvrir mes documents  →'), 'documents')
        self._section(layout, tr('2 · Garde une trace de tes résultats'),
                      tr('Dans Notes, choisis une matière puis ajoute une évaluation. Tu peux préciser le barème, le coefficient et, si tu les connais, la moyenne de classe ou ton classement.'))
        self._destination(layout, tr('Ouvrir mes notes  →'), 'notes')
        self._section(layout, tr('3 · Avance à ton rythme'),
                      tr('Depuis Aujourd’hui, commence une séance avec une durée et un objectif facultatif. Pause conserve ton travail. À la fin, vérifie le bilan avant de l’ajouter au journal.'))
        self._destination(layout, tr('Retrouver mon accueil  →'), 'home')
        self._section(layout, tr('Comprendre ton temps'),
                      tr('Gestion du temps réunit les activités prévues et réalisées. Progression utilise le travail déjà réalisé pour présenter tes bilans et tes objectifs personnels.'))
        self._destination(layout, tr('Ouvrir mon journal  →'), 'time')
        layout.addStretch()

    def _shortcuts_page(self):
        layout = self._page('shortcuts', tr('Raccourcis'))
        self._section(layout, tr('Moins de clics, plus de repères.'),
                      tr('Les raccourcis ci-dessous fonctionnent dans la fenêtre principale. Dans une boîte de dialogue, Échap permet généralement de revenir sans valider.'))
        self._section(layout, tr('Navigation et lecture'),
                      tr('Les pages glissent dans le sens des onglets. Tu peux agir immédiatement pour interrompre la transition. Les notifications se mettent en pause au survol ou pendant la sélection ; leur bouton de copie reprend le message entier. Réglages → Réduire les animations ouvre les pages directement.'))
        shortcuts = (
            ('Ctrl+K', tr('Rechercher une action ou un espace')),
            ('Ctrl+F', tr('Rechercher dans mes documents, notes et repères')),
            ('Ctrl+N', tr('Ajouter dans l’espace ouvert : note, document ou repère ; ailleurs, une activité')),
            ('Ctrl+1', tr('Aujourd’hui')), ('Ctrl+2', tr('Gestion du temps')),
            ('Ctrl+3', tr('Progression')), ('Ctrl+4', tr('Notes')),
            ('Ctrl+5', tr('Documents')), ('Ctrl+6', tr('Mes repères')),
            ('Ctrl+7', tr('Réglages')), ('F1', tr('Ouvrir cette aide')),
            ('F11', tr('Passer en plein écran ou revenir à la fenêtre')),
            (tr('Échap'), tr('Quitter le plein écran')),
        )
        for key, description in shortcuts:
            row = QHBoxLayout()
            shortcut = _text(key, 'badge')
            shortcut.setFixedWidth(94)
            row.addWidget(shortcut, 0, Qt.AlignTop)
            row.addWidget(_text(description, ''), 1)
            layout.addLayout(row)
        layout.addStretch()

    def _data_page(self):
        layout = self._page('data', tr('Mes données'))
        self._section(layout, tr('Ton espace reste sur ce PC.'),
                      tr('Tes notes, ton journal, tes repères et les copies de tes documents sont enregistrés localement. L’aide et la recherche dans ton espace fonctionnent sans connexion.'))
        self._section(layout, tr('Préparer une sauvegarde'),
                      tr('Dans Réglages, Exporter toutes mes données crée un fichier .prepapilot. Garde-en une copie en lieu sûr. Sur un autre PC, importe ce fichier et vérifie que tu retrouves ton espace avant de supprimer l’ancienne copie.'))
        self._section(layout, tr('Google Drive est facultatif.'),
                      tr('Dans une version avec Google Drive, ouvre Réglages → Gérer mes sauvegardes Google Drive, puis Se connecter à Google. Choisis ton compte et autorise PrépaPilot. La configuration commune est fournie par l’éditeur ; tu n’as pas à créer de projet Google Cloud. Si cette version n’est pas encore configurée, l’export complet reste disponible.'))
        self._section(layout, tr('Ranger mes cours avec une IA'),
                      tr('Dans Documents, Ranger avec une IA prépare des copies lisibles de tes cours, un inventaire des chemins et une notice pour ton assistant. Copie la consigne dans une IA ayant accès aux fichiers, puis reviens lire et appliquer sa proposition. Les nouveaux cours sont copiés dans A-importer. PrépaPilot ne transmet rien ; le fonctionnement local ou distant de l’assistant dépend de celui que tu choisis.'))
        self._section(layout, tr('Garder l’application à jour'),
                      tr('Réglages indique la version et la disponibilité des mises à jour. La recherche en ligne nécessite un canal de publication configuré. En mode portable, télécharge la nouvelle version puis transfère tes données avec l’export complet.'))
        self._destination(layout, tr('Ouvrir les réglages  →'), 'settings')
        layout.addStretch()

    def _about_page(self):
        layout = self._page('about', tr('À propos'))
        self._section(layout, 'PrépaPilot', tr('Version {version}', version=__version__))
        layout.addWidget(_text(tr('Un espace pour organiser tes études, retrouver tes documents et suivre tes progrès à ton rythme.')))
        self._section(layout, tr('Besoin de décrire un problème ?'),
                      tr('Tu peux copier un résumé technique contenant uniquement la version de l’application, le système, la version de Qt, la langue et le thème. Tes notes, documents, identifiants et chemins personnels ne sont pas inclus. Rien n’est envoyé automatiquement.'))
        self.copy_button = button(tr('Copier les informations techniques'), self.copy_technical_summary)
        self.copy_button.setAutoDefault(False)
        layout.addWidget(self.copy_button, 0, Qt.AlignLeft)
        self.copy_status = _text('')
        self.copy_status.setAccessibleName(tr('État de la copie des informations techniques'))
        layout.addWidget(self.copy_status)
        layout.addStretch()

    def open_space(self, key):
        self.accept()
        self.on_navigate(key)

    def copy_technical_summary(self):
        QApplication.clipboard().setText(technical_summary(self.ctx))
        self.copy_status.setText(tr('Informations techniques copiées. Tu choisis où les partager.'))
