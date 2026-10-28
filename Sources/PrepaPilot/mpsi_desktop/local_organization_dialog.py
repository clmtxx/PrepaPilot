"""A reviewed, local file hand-off to an assistant chosen by the user."""
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QProgressBar, QScrollArea, QVBoxLayout, QWidget,
)

from .i18n import tr
from .widgets import AnimatedDialog, button


def _text(value, name='muted'):
    result = QLabel(value, objectName=name)
    result.setTextFormat(Qt.PlainText)
    result.setWordWrap(True)
    result.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
    return result


def _path(value, name):
    result = QLineEdit(str(value))
    result.setReadOnly(True)
    result.setMinimumWidth(0)
    result.setAccessibleName(name)
    result.setToolTip(str(value))
    return result


class LocalOrganizationDialog(AnimatedDialog):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.workspace = None
        self.preview = None
        self._busy = False
        self.setWindowTitle(tr('Ranger avec une IA'))
        self.setWindowModality(Qt.WindowModal)
        self.resize(780, 690)
        self.setMinimumSize(560, 430)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(12)
        root.addWidget(_text(tr('Tes cours, prêts pour ton assistant.'), 'dialogTitle'))
        root.addWidget(_text(tr('Prépare un espace de fichiers lisible, confie-le à une IA ayant accès à tes fichiers, puis vérifie son classement ici.')))
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 4, 14, 12)
        body.setSpacing(12)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)

        body.addWidget(_text(tr('1 · Préparer les fichiers'), 'sectionTitle'))
        body.addWidget(_text(tr('Une copie de ta bibliothèque est rangée par dossier, matière et type, avec des noms lisibles. L’inventaire indique aussi l’emplacement exact de chaque fichier conservé par PrépaPilot.')))
        body.addWidget(_text(tr('Données de l’application'), ''))
        self.data_path = _path(ctx.data_dir.resolve(), tr('Dossier des données de l’application'))
        body.addWidget(self.data_path)
        body.addWidget(_text(tr('Fichiers conservés par PrépaPilot'), ''))
        self.originals_path = _path(ctx.db.document_directory.resolve(), tr('Dossier des fichiers conservés'))
        body.addWidget(self.originals_path)
        first_actions = QVBoxLayout()
        self.prepare_button = button(tr('Préparer un nouvel espace'), self.prepare)
        self.resume_button = button(tr('Reprendre un espace…'), self.choose_workspace)
        first_actions.addWidget(self.prepare_button, 0, Qt.AlignLeft)
        first_actions.addWidget(self.resume_button, 0, Qt.AlignLeft)
        body.addLayout(first_actions)
        body.addWidget(_text(tr('Espace de rangement'), ''))
        self.workspace_path = _path('', tr('Chemin de l’espace de rangement pour l’IA'))
        self.workspace_path.setPlaceholderText(tr('Prépare un espace pour afficher son emplacement.'))
        body.addWidget(self.workspace_path)
        second_actions = QVBoxLayout()
        self.open_button = button(tr('Ouvrir l’espace'), self.open_workspace)
        self.originals_button = button(tr('Ouvrir les originaux'), self.open_originals)
        second_actions.addWidget(self.open_button, 0, Qt.AlignLeft)
        second_actions.addWidget(self.originals_button, 0, Qt.AlignLeft)
        body.addLayout(second_actions)

        body.addWidget(_text(tr('2 · Donner la consigne à ton IA'), 'sectionTitle'))
        body.addWidget(_text(tr('L’espace contient NOTICE-IA.md, catalogue.json et proposition.json. Ton assistant lit la notice, propose des dossiers et complète la proposition. Pour ajouter des cours présents ailleurs sur ton PC, il les copie dans A-importer et les décrit dans la proposition.')))
        body.addWidget(_text(tr('Tu choisis et ouvres ton assistant séparément. PrépaPilot n’intègre aucun moteur IA et ne transmet aucun fichier. Un assistant ayant accès aux fichiers peut utiliser un service distant : ses propres réglages déterminent ce qui reste sur ton PC.')))
        self.copy_button = button(tr('Copier la consigne pour mon IA'), self.copy_instruction)
        body.addWidget(self.copy_button, 0, Qt.AlignLeft)

        body.addWidget(_text(tr('3 · Vérifier et appliquer'), 'sectionTitle'))
        body.addWidget(_text(tr('Quand ton assistant a terminé, lis sa proposition. L’aperçu montre les nouveaux imports et les changements de titre, matière, type ou dossier. Les copies déplacées dans l’espace ne modifient pas seules ta bibliothèque.')))
        self.read_button = button(tr('Lire la proposition'), self.read_proposal)
        body.addWidget(self.read_button, 0, Qt.AlignLeft)
        self.preview_summary = _text(tr('Aucune proposition vérifiée.'), '')
        body.addWidget(self.preview_summary)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(180)
        self.preview_text.setAccessibleName(tr('Aperçu du classement proposé'))
        self.preview_text.setPlaceholderText(tr('Les changements proposés apparaîtront ici.'))
        body.addWidget(self.preview_text)
        body.addStretch()

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        root.addWidget(self.progress)
        self.status = _text('', '')
        self.status.setAccessibleName(tr('État du rangement avec une IA'))
        root.addWidget(self.status)
        bottom = QHBoxLayout()
        self.close_button = button(tr('Fermer'), self.reject)
        self.apply_button = button(tr('Appliquer le classement'), self.apply, primary=True)
        bottom.addWidget(self.close_button)
        bottom.addStretch()
        bottom.addWidget(self.apply_button)
        root.addLayout(bottom)
        for control in self.findChildren(type(self.prepare_button)):
            control.setAutoDefault(False)
        saved = ctx.db.get_setting('documents_organization_workspace', '')
        if isinstance(saved, str) and saved and Path(saved).is_dir():
            self._set_workspace(Path(saved), remember=False)
        self.ctx.watch_data(self.invalidate_preview, 'documents', 'subjects')
        self.ctx.jobs_changed.connect(self._sync_controls)
        self._sync_controls()

    def _sync_controls(self, *_):
        available = not self._busy and not self.ctx.busy
        has_workspace = self.workspace is not None
        self.prepare_button.setEnabled(available)
        self.resume_button.setEnabled(available)
        self.open_button.setEnabled(available and has_workspace)
        self.originals_button.setEnabled(available)
        self.copy_button.setEnabled(available and has_workspace)
        self.read_button.setEnabled(available and has_workspace)
        self.apply_button.setEnabled(available and self.preview is not None and
                                     bool(self.preview['update_count'] or self.preview['import_count']))
        self.close_button.setEnabled(not self._busy)

    def invalidate_preview(self):
        had_preview = self.preview is not None
        self.preview = None
        self.preview_text.clear()
        self.preview_summary.setText(tr('Aucune proposition vérifiée.'))
        if had_preview:
            self.status.setText(tr('La bibliothèque a changé. Lis à nouveau la proposition ; si elle est périmée, prépare un nouvel espace.'))
        self._sync_controls()

    def _set_workspace(self, path, *, remember=True):
        self.invalidate_preview()
        self.workspace = Path(path).resolve()
        self.workspace_path.setText(str(self.workspace))
        self.workspace_path.setToolTip(str(self.workspace))
        if remember:
            self.ctx.db.set_setting('documents_organization_workspace', str(self.workspace))
        self._sync_controls()

    def _run(self, work, completed, message):
        if self._busy or self.ctx.busy:
            return
        self._busy = True
        self.status.setText(message)
        self.progress.show()
        self._sync_controls()

        def failed(error):
            self.preview = None
            self.preview_text.clear()
            self.preview_summary.setText(tr('Aucune proposition vérifiée.'))
            self.status.setText(error)

        def finished():
            self._busy = False
            self.progress.hide()
            self._sync_controls()

        self.ctx.run_job(work, completed, failed, finished)

    def prepare(self):
        from .local_organization import prepare_workspace
        self.invalidate_preview()

        def completed(path):
            self._set_workspace(path)
            self.status.setText(tr('Espace prêt. Ouvre-le ou copie la consigne pour ton assistant. Chaque préparation conserve les espaces précédents.'))

        self._run(lambda: prepare_workspace(self.ctx.db), completed, tr('Préparation des copies et de la notice…'))

    def choose_workspace(self):
        if self._busy or self.ctx.busy:
            return
        selected = QFileDialog.getExistingDirectory(self, tr('Reprendre un espace de rangement'),
                    str(self.workspace or self.ctx.data_dir / 'Rangement-IA'))
        if selected:
            self._set_workspace(Path(selected))
            self.status.setText(tr('Espace sélectionné. Lis la proposition pour vérifier sa validité.'))

    def _open(self, path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            self.status.setText(tr('Impossible d’ouvrir ce dossier. Tu peux copier son chemin ci-dessus.'))

    def open_workspace(self):
        if self.workspace is not None:
            self._open(self.workspace)

    def open_originals(self):
        self._open(self.ctx.db.document_directory.resolve())

    def copy_instruction(self):
        if self.workspace is None:
            return
        instruction = tr('Aide-moi à ranger mes cours dans PrépaPilot. L’espace préparé est ici :\n{workspace}\n\nLis d’abord AGENTS.md et NOTICE-IA.md, puis catalogue.json. Utilise les copies de Bibliotheque pour comprendre les cours. Complète proposition.json avec les titres, matières, types et dossiers adaptés. Pour de nouveaux fichiers que je te demande d’ajouter, copie-les dans A-importer puis ajoute les entrées imports correspondantes. Conserve les fichiers sources et les originaux de PrépaPilot. Ne modifie pas sa base de données. Signale les cours dont le classement est incertain. Je vérifierai et appliquerai la proposition dans l’application.', workspace=self.workspace)
        QApplication.clipboard().setText(instruction)
        self.status.setText(tr('Consigne copiée. Colle-la dans ton assistant et précise les cours à ranger.'))

    def read_proposal(self):
        from .local_organization import preview_plan
        if self.workspace is None:
            return
        workspace = self.workspace
        self.invalidate_preview()

        def completed(result):
            self.preview = result
            self.preview_summary.setText(tr('{updates} document(s) à reclasser · {imports} fichier(s) à importer · {folders} nouveau(x) dossier(s)',
                updates=result['update_count'], imports=result['import_count'], folders=result['folder_count']))
            entries = []
            for change in result['changes']:
                action = tr('Importer') if change['action'] == 'import' else tr('Reclasser')
                entries.append(tr('{action} : {title}\nAvant : {before}\nAprès : {after}',
                    action=action, title=change['title'], before=change['before'], after=change['after']))
            self.preview_text.setPlainText('\n\n'.join(entries))
            self.status.setText(tr('Vérifie chaque changement avant de l’appliquer.') if entries else tr('La proposition ne contient aucun changement.'))

        self._run(lambda: preview_plan(self.ctx.db, workspace), completed, tr('Vérification de la proposition…'))

    def apply(self):
        from .local_organization import apply_plan
        if self.workspace is None or self.preview is None:
            return
        workspace, digest = self.workspace, self.preview['digest']

        def completed(result):
            self.preview = None
            self.ctx.mark_changed('documents')
            self.status.setText(tr('Classement appliqué : {updates} document(s) reclassé(s), {imports} fichier(s) importé(s). Prépare un nouvel espace pour continuer.',
                updates=result['update_count'], imports=result['import_count']))
            self.ctx.notice.emit(tr('Le classement proposé par ton IA a été appliqué.'))

        self._run(lambda: apply_plan(self.ctx.db, workspace, digest), completed, tr('Application du classement…'))

    def reject(self):
        if self._busy:
            return
        super().reject()

    def closeEvent(self, event):
        if self._busy:
            event.ignore()
            return
        super().closeEvent(event)
