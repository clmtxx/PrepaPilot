"""Bilingual language choice, shown before the first personal setup screen."""
from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .i18n import LANGUAGES, set_language


class LanguageDialog(QDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("PrépaPilot · Français / English")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(18)
        heading = QLabel("Bienvenue / Welcome")
        heading.setObjectName("sectionTitle")
        layout.addWidget(heading)
        prompt = QLabel("Choisis ta langue.\nChoose your language.")
        layout.addWidget(prompt)
        self.language = QComboBox()
        self.language.setAccessibleName("Langue / Language")
        for key, label in LANGUAGES.items():
            self.language.addItem(label, key)
        system = "en" if QLocale.system().language() == QLocale.English else "fr"
        self.language.setCurrentIndex(self.language.findData(system))
        layout.addWidget(self.language)
        hint = QLabel("Tu pourras la changer dans les réglages.\nYou can change this later in Settings.")
        hint.setWordWrap(True)
        hint.setObjectName("muted")
        layout.addWidget(hint)
        buttons = QDialogButtonBox()
        self.continue_button = buttons.addButton("Continuer / Continue", QDialogButtonBox.AcceptRole)
        buttons.addButton("Quitter / Exit", QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        self.continue_button.setDefault(True)
        layout.addWidget(buttons)

    def save(self):
        self.ctx.set_language(self.language.currentData())
        self.accept()


def choose_language(ctx, parent=None):
    saved = ctx.db.get_setting("desktop_language")
    if saved in LANGUAGES:
        set_language(saved)
        return True
    return LanguageDialog(ctx, parent).exec() == QDialog.Accepted
