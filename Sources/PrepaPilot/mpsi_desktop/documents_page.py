"""A local library of original files, organised by subject and document type."""
from pathlib import Path
import sqlite3

from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLayout, QLineEdit,
    QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QSplitter,
    QSizePolicy, QTextBrowser, QVBoxLayout, QWidget,
)

from .i18n import tr, format_date, format_number

from .catalog import DOCUMENT_KINDS
from .document_store import ALLOWED_EXTENSIONS, ALL_DOCUMENT_FOLDERS
from .page_chrome import AccentCard, PageHero
from .widgets import AnimatedDialog, button, confirm, show_error


def label(text, name=''):
    result=QLabel(text)
    result.setTextFormat(Qt.PlainText)
    result.setWordWrap(True)
    if name:result.setObjectName(name)
    return result


def size_text(size):
    if size < 1024:return tr('{size} octets', size=size)
    if size < 1024*1024:return tr('{size} Ko', size=format_number(size/1024, decimals=0))
    return tr('{size} Mo', size=format_number(size/(1024*1024), decimals=1))


def subject_icon(color):
    pixmap = QPixmap(18, 18)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(QColor('#8A8A8A'))
    painter.setBrush(QColor(color))
    painter.drawEllipse(3, 3, 12, 12)
    painter.end()
    return QIcon(pixmap)


def folder_combo():
    control = QComboBox()
    control.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    control.setMinimumContentsLength(16)
    control.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    control.setAccessibleName(tr('Dossier de documents'))
    control.currentIndexChanged.connect(lambda *_: control.setToolTip(control.currentText()))
    return control


def fill_folders(control, folders, selected=None, *, browsing=False):
    control.blockSignals(True)
    control.clear()
    if browsing:
        control.addItem(tr('Tous les documents'), None)
        control.addItem(tr('Sans dossier'), 0)
    else:
        control.addItem(tr('Sans dossier'), None)
    for folder in folders:
        control.addItem(folder['name'], folder['id'])
    control.setCurrentIndex(max(0, control.findData(selected)))
    control.blockSignals(False)
    control.setToolTip(control.currentText())


class DocumentFolderDialog(AnimatedDialog):
    def __init__(self, ctx, folder=None, parent=None):
        super().__init__(parent)
        self.ctx, self.folder = ctx, folder
        self.saved_id = None
        self.setWindowTitle(tr('Renommer le dossier') if folder else tr('Nouveau dossier'))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        layout.addWidget(label(tr('Une place pour chaque chapitre.'), 'dialogTitle'))
        layout.addWidget(label(tr('Regroupe tes documents par chapitre, projet ou thème. Leurs matières et types restent disponibles.'), 'muted'))
        self.name = QLineEdit(folder['name'] if folder else '')
        self.name.setMaxLength(100)
        self.name.setPlaceholderText(tr('Ex. Mathématiques · Intégrales'))
        self.name.setAccessibleName(tr('Nom du dossier'))
        layout.addWidget(self.name)
        self.error = label('', 'error')
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addWidget(button(tr('Annuler'), self.reject))
        actions.addStretch()
        self.save_button = button(tr('Renommer') if folder else tr('Créer le dossier'), self.save, primary=True)
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def save(self):
        if self.saved_id is not None:
            return
        try:
            if self.folder:
                if not self.ctx.db.rename_document_folder(self.folder['id'], self.name.text()):
                    raise ValueError(tr('Ce dossier n’existe plus.'))
                self.saved_id = self.folder['id']
            else:
                self.saved_id = self.ctx.db.create_document_folder(self.name.text())
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.ctx.mark_changed('documents')
        self.accept()


class MoveDocumentsDialog(AnimatedDialog):
    def __init__(self, ctx, identities, folder_id=None, parent=None):
        super().__init__(parent)
        self.ctx, self.identities = ctx, list(identities)
        self.saved = False
        self.setWindowTitle(tr('Ranger les documents'))
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)
        count = len(self.identities)
        layout.addWidget(label(tr('Ranger {count} document' if count == 1 else 'Ranger {count} documents', count=count), 'dialogTitle'))
        layout.addWidget(label(tr('Choisis leur dossier. Les fichiers et leurs informations sont conservés.'), 'muted'))
        self.folder = folder_combo()
        fill_folders(self.folder, ctx.db.list_document_folders(), folder_id)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(button(tr('+ Dossier'), self.new_folder))
        layout.addLayout(row)
        self.error = label('', 'error')
        self.error.hide()
        layout.addWidget(self.error)
        actions = QHBoxLayout()
        actions.addWidget(button(tr('Annuler'), self.reject))
        actions.addStretch()
        self.save_button = button(tr('Ranger'), self.save, primary=True)
        self.save_button.setDefault(True)
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def new_folder(self):
        dialog = DocumentFolderDialog(self.ctx, parent=self)
        if dialog.exec() == QDialog.Accepted:
            fill_folders(self.folder, self.ctx.db.list_document_folders(), dialog.saved_id)

    def save(self):
        if self.saved:
            return
        try:
            self.ctx.db.move_documents(self.identities, self.folder.currentData())
        except (ValueError, OSError, sqlite3.Error) as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.saved = True
        self.ctx.mark_changed('documents')
        self.ctx.notice.emit(tr('Documents rangés.') if len(self.identities) != 1 else tr('Document rangé.'))
        self.accept()


class DocumentMetadataDialog(AnimatedDialog):
    def __init__(self, ctx, document=None, count=1, parent=None, *, folder_id=None):
        super().__init__(parent)
        self.ctx=ctx
        self.document=document
        self.setWindowTitle(tr('Modifier le document') if document else tr('Ranger les documents'))
        self.setMinimumWidth(460)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(28,28,28,28)
        layout.setSpacing(18)
        layout.addWidget(label(tr('Tout à sa place.'), 'pageTitle'))
        layout.addWidget(label(tr('Classe ce document.') if document else
                               tr('{count} fichier à ajouter à ta bibliothèque.' if count == 1 else '{count} fichiers à ajouter à ta bibliothèque.', count=count), 'muted'))
        form=QFormLayout()
        form.setSpacing(14)
        self.title=QLineEdit(document['title'] if document else '')
        self.title.setMaxLength(240)
        if document:form.addRow(tr('Titre'),self.title)
        else:self.title.hide()
        self.subject=QComboBox()
        subjects = ctx.db.subject_labels(include_archived=False)
        all_subjects = ctx.db.subject_labels(include_archived=True)
        if document and document['subject'] not in subjects and document['subject'] in all_subjects:
            subjects[document['subject']] = all_subjects[document['subject']] + tr(' · archivée')
        for key,text in subjects.items():
            self.subject.addItem(subject_icon(ctx.db.category_color(key)), text, key)
        self.kind=QComboBox()
        for key,text in DOCUMENT_KINDS.items():self.kind.addItem(tr(text),key)
        for control,key,default in ((self.subject,'subject',next(iter(subjects),None)),(self.kind,'kind','cours')):
            current=document[key] if document else ctx.db.get_setting('documents_last_'+key,default)
            control.setCurrentIndex(max(0,control.findData(current)))
        form.addRow(tr('Matière'),self.subject)
        form.addRow(tr('Type'),self.kind)
        self.folder = folder_combo()
        fill_folders(self.folder, ctx.db.list_document_folders(), document.get('folder_id') if document else folder_id)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(button(tr('+ Dossier'), self.new_folder))
        form.addRow(tr('Dossier'), folder_row)
        self.description=QPlainTextEdit(document['description'] if document else '')
        self.description.setPlaceholderText(tr('Chapitre, précisions, mots-clés…'))
        self.description.setMaximumHeight(100)
        form.addRow(tr('Description'),self.description)
        layout.addLayout(form)
        self.error=label('', 'error')
        layout.addWidget(self.error)
        actions=QHBoxLayout()
        actions.addWidget(button(tr('Annuler'),self.reject))
        actions.addStretch()
        self.save_button = button(tr('Enregistrer') if document else tr('Ajouter'),self.save,primary=True)
        self.save_button.setEnabled(bool(subjects))
        if not subjects:
            self.error.setText(tr('Active au moins une matière dans les réglages pour ranger un document.'))
        actions.addWidget(self.save_button)
        layout.addLayout(actions)

    def new_folder(self):
        dialog = DocumentFolderDialog(self.ctx, parent=self)
        if dialog.exec() == QDialog.Accepted:
            fill_folders(self.folder, self.ctx.db.list_document_folders(), dialog.saved_id)

    def save(self):
        try:
            self.ctx.db._document_metadata(self.title.text() if self.document else 'Import',
                self.subject.currentData(),self.kind.currentData(),self.description.toPlainText(),
                retained_subject=self.document['subject'] if self.document else None)
            if self.document:
                if not self.ctx.db.update_document(self.document['id'],self.title.text(),
                        self.subject.currentData(),self.kind.currentData(),self.description.toPlainText(),
                        folder_id=self.folder.currentData()):
                    raise ValueError(tr('Ce document n’existe plus.'))
            else:
                self.ctx.db.set_setting('documents_last_subject',self.subject.currentData())
                self.ctx.db.set_setting('documents_last_kind',self.kind.currentData())
        except (ValueError,OSError,sqlite3.Error) as exc:
            self.error.setText(str(exc))
            return
        if self.document:
            self.ctx.mark_changed('documents')
            self.ctx.notice.emit(tr('Document mis à jour.'))
        self.accept()


class DocumentsPage(QWidget):
    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx=ctx
        self._selected_id=None
        self._folders = {}
        self._busy=False
        layout=QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(18)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        self.import_button=button(tr('+ Ajouter des documents'),self.add_documents,primary=True)
        self.hero=PageHero(ctx, 'documents', tr('BIBLIOTHÈQUE'), tr('Cours et documents'),
                          tr('Tes cours et exercices, classés par matière ou chapitre.'),
                          actions=[self.import_button])
        layout.addWidget(self.hero)
        organization = QHBoxLayout()
        organization.addWidget(label(tr('Une IA peut t’aider à classer tes cours grâce à un espace de fichiers lisible et une notice.'), 'muted'), 1)
        self.organization_button = button(tr('Ranger avec une IA'), self.organize_with_ai)
        organization.addWidget(self.organization_button)
        layout.addLayout(organization)
        folders = QHBoxLayout()
        folders.addWidget(label(tr('Dossier'), 'muted'))
        self.folder_filter = folder_combo()
        folders.addWidget(self.folder_filter, 1)
        layout.addLayout(folders)
        folder_actions = QHBoxLayout()
        self.new_folder_button = button(tr('+ Nouveau dossier'), self.new_folder)
        self.rename_folder_button = button(tr('Renommer'), self.rename_folder)
        self.delete_folder_button = button(tr('Retirer le dossier'), self.delete_folder)
        for control in (self.new_folder_button, self.rename_folder_button, self.delete_folder_button):
            folder_actions.addWidget(control)
        folder_actions.addStretch()
        layout.addLayout(folder_actions)
        filters=QHBoxLayout()
        self.search=QLineEdit()
        self.search.setPlaceholderText(tr('Rechercher un nom de fichier, un titre ou un mot-clé…'))
        self.search.setAccessibleName(tr('Rechercher des documents par nom, titre ou mot-clé'))
        self.search.setClearButtonEnabled(True)
        self.subject_filter=QComboBox()
        self.subject_filter.addItem(tr('Toutes les matières'),None)
        self.kind_filter=QComboBox()
        self.kind_filter.addItem(tr('Tous les types'),None)
        for key,text in DOCUMENT_KINDS.items():self.kind_filter.addItem(tr(text),key)
        filters.addWidget(self.search,2)
        filters.addWidget(self.subject_filter,1)
        filters.addWidget(self.kind_filter,1)
        layout.addLayout(filters)
        search_scope = QHBoxLayout()
        self.search_everywhere = QCheckBox(tr('Rechercher partout'))
        self.search_everywhere.setChecked(True)
        self.search_everywhere.setToolTip(tr('Chercher dans tous les dossiers, matières et types. Décoche pour utiliser les filtres choisis.'))
        search_scope.addWidget(self.search_everywhere)
        self.search_hint = label(tr('Ctrl ou Maj pour sélectionner plusieurs documents.'), 'muted')
        search_scope.addWidget(self.search_hint, 1)
        layout.addLayout(search_scope)
        self.progress=QProgressBar()
        self.progress.setRange(0,0)
        self.progress.setMaximumHeight(5)
        self.progress.setTextVisible(False)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status=label('', 'muted')
        self.status.hide()
        layout.addWidget(self.status)
        splitter=QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        index=AccentCard(ctx, 'documents')
        index.setMinimumWidth(240)
        self.count=label('', 'colorEyebrow')
        index.body.addWidget(self.count)
        self.documents=QListWidget()
        self.documents.setSpacing(5)
        self.documents.setWordWrap(True)
        self.documents.setMinimumHeight(260)
        self.documents.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.documents.currentItemChanged.connect(self._selection_changed)
        self.documents.itemSelectionChanged.connect(lambda: self._selection_changed(self.documents.currentItem()))
        self.documents.itemDoubleClicked.connect(lambda *_:self.open_selected())
        index.body.addWidget(self.documents,1)
        self.move_button = button(tr('Ranger'), self.move_selected)
        index.body.addWidget(self.move_button)
        self.empty=label(tr('Ta bibliothèque commence ici.\nAjoute tes premiers documents.'), 'muted')
        index.body.addWidget(self.empty)
        splitter.addWidget(index)
        details=AccentCard(ctx, 'home')
        details.setMinimumWidth(300)
        self.title_label=label(tr('Tout ton travail, au même endroit.'), 'sectionTitle')
        self.meta_label=label(tr('Sélectionne un document pour le consulter.'), 'muted')
        self.description_label=label('', 'muted')
        details.body.addWidget(self.title_label)
        details.body.addWidget(self.meta_label)
        details.body.addWidget(self.description_label)
        self.stored_path = QLineEdit()
        self.stored_path.setReadOnly(True)
        self.stored_path.setMinimumWidth(0)
        self.stored_path.setAccessibleName(tr('Emplacement du fichier conservé'))
        self.stored_path.setPlaceholderText(tr('Emplacement du fichier conservé'))
        details.body.addWidget(self.stored_path)
        self.reader=QTextBrowser()
        self.reader.setOpenLinks(False)
        self.reader.setOpenExternalLinks(False)
        self.reader.setMinimumHeight(160)
        self.reader.setPlaceholderText(tr('Les fichiers sont copiés dans PrépaPilot avec leur contenu original.\n\nPDF, images, documents Office, fichiers texte…'))
        details.body.addWidget(self.reader,1)
        self.open_button=button(tr('Ouvrir le fichier'),self.open_selected,primary=True)
        self.export_button=button(tr('Enregistrer une copie'),self.export_selected)
        self.edit_button=button(tr('Modifier'),self.edit_selected)
        self.delete_button=button(tr('Supprimer'),self.delete_selected,danger=True)
        main_actions=QVBoxLayout()
        main_actions.addWidget(self.open_button)
        main_actions.addWidget(self.export_button)
        details.body.addLayout(main_actions)
        actions=QHBoxLayout()
        actions.addWidget(self.edit_button)
        actions.addStretch()
        actions.addWidget(self.delete_button)
        details.body.addLayout(actions)
        splitter.addWidget(details)
        splitter.setSizes([310,620])
        splitter.setStretchFactor(0,2)
        splitter.setStretchFactor(1,3)
        layout.addWidget(splitter,1)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(120)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda *_: self.search_timer.start())
        self.search.returnPressed.connect(self.refresh)
        self.subject_filter.currentIndexChanged.connect(self.refresh)
        self.kind_filter.currentIndexChanged.connect(self.refresh)
        self.folder_filter.currentIndexChanged.connect(self.refresh)
        self.search_everywhere.toggled.connect(self.refresh)
        ctx.watch_data(self.refresh, 'documents', 'subjects')
        ctx.data_replaced.connect(self.reset_selection)
        ctx.jobs_changed.connect(self._sync_organization_button)
        self.refresh()

    def reset_selection(self):
        self._selected_id=None
        self.search.clear()
        self.subject_filter.setCurrentIndex(0)
        self.kind_filter.setCurrentIndex(0)
        self.folder_filter.setCurrentIndex(0)
        self.search_everywhere.setChecked(True)
        self.refresh()

    def refresh(self,*_):
        self.search_timer.stop()
        selected_ids = set(self.selected_document_ids())
        folder_id = self.folder_filter.currentData()
        folders = self.ctx.db.list_document_folders()
        self._folders = {folder['id']: folder for folder in folders}
        fill_folders(self.folder_filter, folders, folder_id, browsing=True)
        folder_id = self.folder_filter.currentData()
        subjects = self.ctx.db.get_subjects(include_archived=True)
        labels = {subject['id']: subject['name'] for subject in subjects}
        icons = {subject['id']: subject_icon(subject['color']) for subject in subjects}
        filtered_subject = self.subject_filter.currentData()
        self.subject_filter.blockSignals(True)
        self.subject_filter.clear()
        self.subject_filter.addItem(tr('Toutes les matières'), None)
        for subject in subjects:
            caption = subject['name'] + ('' if subject['active'] else tr(' · archivée'))
            self.subject_filter.addItem(icons[subject['id']], caption, subject['id'])
        self.subject_filter.setCurrentIndex(max(0, self.subject_filter.findData(filtered_subject)))
        self.subject_filter.blockSignals(False)
        active_subjects = any(subject['active'] for subject in subjects)
        self.import_button.setEnabled(active_subjects and not self._busy)
        self.organization_button.setEnabled(not self._busy and not self.ctx.busy)
        self.import_button.setToolTip('' if active_subjects else tr('Active une matière dans les réglages pour ajouter des documents.'))
        global_search = bool(self.search.text().strip()) and self.search_everywhere.isChecked()
        for control in (self.folder_filter, self.subject_filter, self.kind_filter):
            control.setEnabled(not global_search)
        self.new_folder_button.setEnabled(not self._busy)
        has_folder = bool(folder_id) and not global_search and not self._busy
        self.rename_folder_button.setEnabled(has_folder)
        self.delete_folder_button.setEnabled(has_folder)
        self.search_hint.setText(tr('Résultats dans toute la bibliothèque, quels que soient les filtres.') if global_search else
                                tr('Ctrl ou Maj pour sélectionner plusieurs documents.'))
        selected_folder = ALL_DOCUMENT_FOLDERS if folder_id is None else (None if folder_id == 0 else folder_id)
        rows=self.ctx.db.list_documents(None if global_search else self.subject_filter.currentData(),
            None if global_search else self.kind_filter.currentData(),self.search.text(),
            folder_id=ALL_DOCUMENT_FOLDERS if global_search else selected_folder)
        self.documents.blockSignals(True)
        self.documents.clear()
        selected=None
        restored=[]
        for row in rows:
            folder_name = self._folders.get(row.get('folder_id'), {}).get('name', tr('Sans dossier'))
            item=QListWidgetItem(f"{row['title']}\n{labels.get(row['subject'],row['subject'])} · {tr(DOCUMENT_KINDS.get(row['kind'],row['kind']))}\n{folder_name}")
            item.setIcon(icons.get(row['subject'], QIcon()))
            item.setData(Qt.UserRole,row['id'])
            item.setToolTip(tr('{name}\nDossier : {folder}', name=row['original_name'], folder=folder_name))
            self.documents.addItem(item)
            if row['id']==self._selected_id:selected=item
            if row['id'] in selected_ids:restored.append(item)
        if selected:self.documents.setCurrentItem(selected)
        elif rows:self.documents.setCurrentRow(0)
        if restored:
            self.documents.clearSelection()
            for item in restored:item.setSelected(True)
        self.documents.blockSignals(False)
        self.count.setText(tr('{count} DOCUMENT' if len(rows) == 1 else '{count} DOCUMENTS', count=len(rows)) + (tr(' · PARTOUT') if global_search else ''))
        self.documents.setVisible(bool(rows))
        self.empty.setVisible(not rows)
        filtered=bool(self.search.text() or self.subject_filter.currentData() or self.kind_filter.currentData() or folder_id is not None)
        self.empty.setText(tr('Aucun document ne correspond à ces filtres.') if filtered else
                           tr('Ta bibliothèque commence ici.\nAjoute tes premiers documents.'))
        self._selection_changed(self.documents.currentItem(),None)

    def selected_document_ids(self):
        return [item.data(Qt.UserRole) for item in self.documents.selectedItems()]

    def _update_actions(self):
        count = len(self.selected_document_ids())
        for control in (self.open_button, self.export_button, self.edit_button, self.delete_button):
            control.setEnabled(count == 1 and not self._busy)
        self.move_button.setEnabled(count > 0 and not self._busy)
        self.move_button.setText(tr('Ranger la sélection ({count})', count=count) if count > 1 else tr('Ranger dans un dossier'))

    def _selection_changed(self,current,*_):
        selected = self.documents.selectedItems()
        if len(selected) == 1:
            current = selected[0]
        elif not selected:
            current = None
        elif current not in selected:
            current = selected[0]
        row=self.ctx.db.get_document(current.data(Qt.UserRole)) if current else None
        self._selected_id=row['id'] if row else None
        self._update_actions()
        self.reader.clear()
        self.description_label.clear()
        self.stored_path.clear()
        self.stored_path.setToolTip('')
        if not row:
            self.title_label.setText(tr('Tout ton travail, au même endroit.'))
            self.meta_label.setText(tr('Sélectionne un document pour le consulter.'))
            return
        self.title_label.setText(row['title'])
        subject_name = self.ctx.db.subject_labels(include_archived=True).get(row['subject'], row['subject'])
        folder_name = self._folders.get(row.get('folder_id'), {}).get('name', tr('Sans dossier'))
        self.meta_label.setText(tr('{subject} · {kind}\nDossier : {folder}\n{name}\n{size} · Ajouté le {date}',
            subject=subject_name, kind=tr(DOCUMENT_KINDS.get(row['kind'], row['kind'])), folder=folder_name,
            name=row['original_name'], size=size_text(row['size_bytes']), date=format_date(row['created_at'][:10])))
        self.description_label.setText(row['description'])
        try:
            path=self.ctx.db.document_path(row['id'])
            self.stored_path.setText(str(path))
            self.stored_path.setToolTip(tr('Emplacement du fichier conservé') + '\n' + str(path))
            if path.suffix.lower() in {'.txt','.md','.csv','.tex'}:
                with path.open('rb') as handle:raw=handle.read(100001)
                text=raw[:100000].decode('utf-8-sig',errors='replace')
                self.reader.setPlainText(text+(tr('\n\nAperçu limité. Ouvre le fichier pour lire la suite.') if len(raw)>100000 else ''))
            else:
                self.reader.setPlainText(tr('Ce document est conservé dans son format original.\n\nOuvre-le pour le consulter dans ton application habituelle.'))
        except (ValueError,OSError) as exc:
            self.reader.setPlainText(str(exc))
            self.open_button.setEnabled(False)
            self.export_button.setEnabled(False)

    def organize_with_ai(self):
        if self._busy or self.ctx.busy:
            return
        from .local_organization_dialog import LocalOrganizationDialog
        LocalOrganizationDialog(self.ctx, self).exec()

    def _sync_organization_button(self, *_):
        self.organization_button.setEnabled(not self._busy and not self.ctx.busy)

    def add_documents(self):
        if self._busy:return
        patterns=' '.join('*'+ext for ext in sorted(ALLOWED_EXTENSIONS))
        paths,_=QFileDialog.getOpenFileNames(self,tr('Ajouter des documents'),'',tr('Documents ({patterns})', patterns=patterns))
        if not paths:return
        folder_id = self.folder_filter.currentData() or None
        dialog=DocumentMetadataDialog(self.ctx,count=len(paths),parent=self,folder_id=folder_id)
        if dialog.exec()==QDialog.Accepted:
            self.import_documents(paths,dialog.subject.currentData(),dialog.kind.currentData(),dialog.description.toPlainText(),folder_id=dialog.folder.currentData())

    def import_documents(self, paths, subject='maths', kind='cours', description='', *, folder_id=None):
        if self._busy:return
        self._busy=True
        self.import_button.setEnabled(False)
        self.progress.show()
        self.status.setText(tr('Copie des fichiers en cours…'))
        self.status.show()
        self._selection_changed(self.documents.currentItem())
        for control in (self.new_folder_button, self.rename_folder_button, self.delete_folder_button):
            control.setEnabled(False)
        def finish():
            self._busy=False
            self.import_button.setEnabled(bool(self.ctx.db.subject_labels(include_archived=False)))
            self.progress.hide()
        def completed(identities):
            finish()
            self.documents.clearSelection()
            self._selected_id=identities[-1]
            self.search.clear()
            self.subject_filter.setCurrentIndex(0)
            self.kind_filter.setCurrentIndex(0)
            self.folder_filter.setCurrentIndex(max(0, self.folder_filter.findData(folder_id or 0)))
            self.ctx.mark_changed('documents')
            text=tr('{count} document ajouté.' if len(identities) == 1 else '{count} documents ajoutés.', count=len(identities))
            self.status.setText(text)
            self.ctx.notice.emit(text)
        def failed(message):
            finish()
            self.status.setText(message)
            self.refresh()
        self.ctx.run_job(lambda:self.ctx.db.import_documents(paths,subject,kind,description=description,folder_id=folder_id),completed,failed)

    def new_folder(self):
        if self._busy:return
        dialog = DocumentFolderDialog(self.ctx, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.search.clear()
            self.folder_filter.setCurrentIndex(self.folder_filter.findData(dialog.saved_id))
            self.ctx.notice.emit(tr('Dossier créé. Ajoute des documents ou range ceux de ta bibliothèque.'))

    def rename_folder(self):
        if self._busy:return
        folder = self._folders.get(self.folder_filter.currentData())
        if folder:
            DocumentFolderDialog(self.ctx, folder, parent=self).exec()

    def delete_folder(self):
        if self._busy:return
        folder = self._folders.get(self.folder_filter.currentData())
        if not folder:return
        if not confirm(self, tr('Retirer ce dossier ?'),
                tr('Le dossier « {name} » sera retiré. Ses documents resteront disponibles dans « Sans dossier ». Aucun fichier ne sera supprimé.', name=folder['name'])):
            return
        try:
            self.ctx.db.delete_document_folder(folder['id'])
            self.ctx.mark_changed('documents')
            self.folder_filter.setCurrentIndex(self.folder_filter.findData(0))
            self.ctx.notice.emit(tr('Dossier retiré. Ses documents sont conservés.'))
        except (ValueError, OSError, sqlite3.Error) as exc:
            show_error(self, str(exc))

    def move_selected(self):
        identities = self.selected_document_ids()
        if self._busy or not identities:return
        row = self.ctx.db.get_document(identities[0])
        dialog = MoveDocumentsDialog(self.ctx, identities, row.get('folder_id') if row else None, parent=self)
        dialog.exec()

    def open_selected(self):
        if self._selected_id is None:return
        try:
            path=self.ctx.db.document_path(self._selected_id)
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
                raise ValueError(tr('Aucune application n’a pu ouvrir ce format. Enregistre une copie pour le consulter ailleurs.'))
        except (ValueError,OSError) as exc:show_error(self,str(exc))

    def export_selected(self):
        row=self.ctx.db.get_document(self._selected_id) if self._selected_id is not None else None
        if row is None:return
        suffix=Path(row['original_name']).suffix
        target,_=QFileDialog.getSaveFileName(self,tr('Enregistrer une copie'),row['original_name'],tr('Fichier original (*{suffix})', suffix=suffix))
        if not target:return
        if not Path(target).suffix:target+=suffix
        try:
            self.ctx.db.export_document(row['id'],target)
            self.ctx.notice.emit(tr('Copie enregistrée.'))
        except (ValueError,OSError) as exc:show_error(self,str(exc))

    def edit_selected(self):
        row=self.ctx.db.get_document(self._selected_id) if self._selected_id is not None else None
        if row:DocumentMetadataDialog(self.ctx,document=row,parent=self).exec()

    def delete_selected(self):
        row=self.ctx.db.get_document(self._selected_id) if self._selected_id is not None else None
        if row is None:return
        if not confirm(self,tr('Supprimer ce document ?'),tr('« {title} » sera retiré de PrépaPilot. Le fichier utilisé lors de l’import restera à sa place.', title=row['title'])):
            return
        try:
            removed=self.ctx.db.delete_document(row['id'])
            self._selected_id=None
            self.ctx.mark_changed('documents')
            if removed:self.ctx.notice.emit(tr('Document supprimé.'))
        except (ValueError,OSError) as exc:show_error(self,str(exc))
