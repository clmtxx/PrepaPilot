"""Personal study goals and reference notes."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLayout, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QSplitter,
    QVBoxLayout, QWidget,
)

from .i18n import tr

from .page_chrome import AccentCard, PageHero
from .widgets import button, confirm, show_error




def _label(text: str, name: str = "") -> QLabel:
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    if name:
        label.setObjectName(name)
    return label


def _display(value) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


class MemoryPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._selected_key: str | None = None
        self._memories: dict = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(18)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.hero = PageHero(
            ctx, "memory", tr("CARNET PERSONNEL"), tr("Idées et repères"),
            tr("Méthodes, objectifs et notes à retrouver entre deux séances."),
        )
        layout.addWidget(self.hero)
        layout.addWidget(self._build_memories(), 1)
        ctx.data_replaced.connect(self.new_memory)
        ctx.watch_data(self.refresh, 'memories')
        self.refresh()

    def _build_memories(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        index = AccentCard(self.ctx, "memory")
        index.setMinimumWidth(225)
        top = QHBoxLayout()
        top.addWidget(_label(tr("MES REPÈRES"), "colorEyebrow"))
        top.addStretch(1)
        self.new_button = button(tr("+ Nouveau"), self.new_memory)
        top.addWidget(self.new_button)
        index.body.addLayout(top)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Rechercher un repère…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._populate_memories)
        index.body.addWidget(self.search)
        self.memory_list = QListWidget()
        self.memory_list.setSpacing(5)
        self.memory_list.setWordWrap(True)
        self.memory_list.currentItemChanged.connect(self._select_memory)
        index.body.addWidget(self.memory_list, 1)
        self.empty_label = _label(tr("Ajoute ton premier repère à droite."), "muted")
        index.body.addWidget(self.empty_label)
        split.addWidget(index)

        editor = AccentCard(self.ctx, "home")
        editor.setMinimumWidth(330)
        self.editor_title = _label(tr("Nouveau repère"), "sectionTitle")
        editor.body.addWidget(self.editor_title)
        editor.body.addWidget(_label(
            tr("Un objectif à atteindre, une méthode qui fonctionne, une idée à retrouver…"), "muted"))
        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        form.setVerticalSpacing(12)
        self.key_input = QLineEdit()
        self.key_input.setMaxLength(80)
        self.key_input.setPlaceholderText(tr("Ex. Méthode de travail préférée"))
        self.value_input = QPlainTextEdit()
        self.value_input.setPlaceholderText(tr("Ex. Je retiens mieux avec un exemple corrigé, puis un exercice seul."))
        self.value_input.setMinimumHeight(180)
        form.addRow(tr("Nom du repère"), self.key_input)
        form.addRow(tr("Ce que tu veux garder en mémoire"), self.value_input)
        editor.body.addLayout(form, 1)
        self.feedback = _label(tr("Inclus dans la sauvegarde complète de tes données."), "muted")
        editor.body.addWidget(self.feedback)
        actions = QHBoxLayout()
        self.save_button = button(tr("Enregistrer"), self.save_memory, primary=True)
        self.delete_button = button(tr("Supprimer"), self.delete_memory, danger=True)
        actions.addWidget(self.save_button)
        actions.addStretch(1)
        actions.addWidget(self.delete_button)
        editor.body.addLayout(actions)
        split.addWidget(editor)
        split.setStretchFactor(0, 2)
        split.setStretchFactor(1, 3)
        split.setSizes([300, 500])
        layout.addWidget(split, 1)
        return page

    def refresh(self):
        self._memories = self.ctx.db.memories()
        self._populate_memories()
        self.delete_button.setEnabled(self._selected_key is not None)

    def _populate_memories(self, *_):
        needle = self.search.text().strip().casefold()
        self.memory_list.blockSignals(True)
        self.memory_list.clear()
        selected = None
        for key, value in self._memories.items():
            text = _display(value)
            if needle and needle not in key.casefold() and needle not in text.casefold():
                continue
            preview = " ".join(text.split())
            item = QListWidgetItem(key + "\n" + (preview[:87] + "…" if len(preview) > 88 else preview))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setToolTip(key)
            self.memory_list.addItem(item)
            if key == self._selected_key:
                selected = item
        if selected:
            self.memory_list.setCurrentItem(selected)
        self.memory_list.blockSignals(False)
        self.empty_label.setVisible(self.memory_list.count() == 0)
        self.empty_label.setText(tr("Aucun repère ne correspond à cette recherche.") if needle else tr("Ajoute ton premier repère à droite."))
        self.delete_button.setEnabled(self._selected_key is not None)

    def _select_memory(self, current, _previous):
        if not current:
            return
        key = current.data(Qt.ItemDataRole.UserRole)
        if key not in self._memories:
            return
        self._selected_key = key
        self.editor_title.setText(tr("Modifier ce repère"))
        self.key_input.setText(key)
        self.key_input.setReadOnly(True)
        self.value_input.setPlainText(_display(self._memories[key]))
        self.delete_button.setEnabled(True)
        self.feedback.setText(tr("Modifie le contenu puis enregistre. Le nom identifie ce repère."))

    def new_memory(self):
        self._selected_key = None
        self.memory_list.clearSelection()
        self.editor_title.setText(tr("Nouveau repère"))
        self.key_input.setReadOnly(False)
        self.key_input.clear()
        self.value_input.clear()
        self.delete_button.setEnabled(False)
        self.feedback.setText(tr("Inclus dans la sauvegarde complète de tes données."))
        self.key_input.setFocus()

    def save_memory(self):
        key = self.key_input.text().strip()
        value = self.value_input.toPlainText().strip()
        if not key or not value:
            show_error(self, tr("Repère incomplet"), tr("Ajoute un nom et un contenu avant d’enregistrer."))
            return
        if len(value) > 4000:
            show_error(self, tr("Repère trop long"), tr("Limite ce repère à 4 000 caractères ; tu peux en créer plusieurs."))
            return
        if self._selected_key is None and key in self.ctx.db.memories():
            if not confirm(self, tr("Remplacer ce repère ?"), tr("Un repère nommé « {key} » existe déjà. Son contenu sera remplacé.", key=key)):
                return
        self.ctx.db.remember(key, value)
        self._selected_key = key
        self.key_input.setReadOnly(True)
        self.editor_title.setText(tr("Modifier ce repère"))
        self.feedback.setText(tr("Repère enregistré."))
        self.ctx.mark_changed('memories')
        self.ctx.notice.emit(tr("Repère enregistré."))

    def delete_memory(self):
        key = self._selected_key
        if key is None:
            return
        if not confirm(self, tr("Supprimer ce repère ?"), tr("Le repère « {key} » et son contenu seront supprimés.", key=key)):
            return
        self.ctx.db.forget(key)
        self.new_memory()
        self.ctx.mark_changed('memories')
        self.ctx.notice.emit(tr("Repère supprimé."))

