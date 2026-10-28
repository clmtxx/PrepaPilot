"""Opt-in Google Drive backup controls. Network work never runs on the GUI thread."""
from .i18n import tr, format_datetime
from pathlib import Path
import re
import threading
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal, Slot, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QComboBox, QCheckBox, QLineEdit, QFileDialog, QInputDialog, QProgressBar, QApplication)

from .widgets import AnimatedDialog, button, show_error, confirm, scroll_page
from .cloud_preferences import CloudPreferences, stamp
from .google_auth import GoogleConnection
from .cloud_backup import CATEGORIES, backup_to_drive, list_snapshots, prepare_drive_restore, validate_restore_target
from .transfers import apply_import


def display_date(value):
    parsed = stamp(value)
    return format_datetime(parsed.astimezone()) if parsed else tr('Date inconnue')


def folder_identifier(value):
    value = str(value).strip()
    if value.startswith('https://'):
        parsed = urlparse(value)
        if parsed.hostname != 'drive.google.com':
            raise ValueError(tr('Utilise le lien d’un dossier Google Drive de PrépaPilot.'))
        match = re.fullmatch(r'/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)/*', parsed.path)
        value = match.group(1) if match else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise ValueError(tr('Le lien ou l’identifiant du dossier Google Drive est invalide.'))
    return value


class CloudBackupDialog(AnimatedDialog):
    changed = Signal()
    progress_message = Signal(str)

    def __init__(self, ctx, parent=None, *, connection=None):
        super().__init__(parent)
        self.ctx = ctx
        self.connection = connection or GoogleConnection(ctx.data_dir)
        self.preferences = CloudPreferences(ctx.data_dir)
        self.running = False
        self.cancel_event = None
        self._pending = None
        self._failure = None
        self._handler = None
        self.setWindowTitle(tr('Sauvegarde Google Drive · PrépaPilot'))
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(min(790, screen.width() - 60), min(850, screen.height() - 80))
        self.setMinimumSize(630, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(14, 12, 14, 14)
        self.body.setSpacing(14)
        self._text('GOOGLE DRIVE', 'colorEyebrow')
        self._text(tr('Tes données te suivent.'), 'pageTitle')
        self._text(tr('Choisis ce que tu souhaites sauvegarder. Les éléments inchangés sont réutilisés, et les versions précédentes restent disponibles.'))
        self.connection_status = self._text('')
        row = QHBoxLayout()
        self.connect_button = button(tr('Se connecter à Google'), self.connect_google, primary=True)
        self.disconnect_button = button(tr('Déconnecter ce PC'), self.disconnect_google)
        row.addWidget(self.connect_button)
        row.addWidget(self.disconnect_button)
        row.addStretch()
        self.body.addLayout(row)

        self._text(tr('Ton dossier de sauvegarde'), 'sectionTitle')
        self.folders = QComboBox()
        self.folders.setAccessibleName(tr('Dossier Google Drive des sauvegardes'))
        self.folders.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.folders.setMinimumContentsLength(20)
        self.folders.addItem(tr('Choisir un dossier…'), '')
        saved = self.preferences.read()
        if saved['folder_id']:
            self.folders.addItem(saved['folder_name'] or tr('Mon dossier PrépaPilot'), saved['folder_id'])
            self.folders.setCurrentIndex(1)
        self.folders.currentIndexChanged.connect(self.folder_changed)
        self.body.addWidget(self.folders)
        row = QHBoxLayout()
        self.find_button = button(tr('Retrouver mes dossiers'), self.find_folders)
        self.create_button = button(tr('Nouveau dossier'), self.create_folder)
        self.open_button = button(tr('Ouvrir dans Drive ↗'), self.open_folder)
        for control in (self.find_button, self.create_button):
            row.addWidget(control)
        row.addStretch()
        self.body.addLayout(row)
        self.body.addWidget(self.open_button, 0, Qt.AlignLeft)
        row = QHBoxLayout()
        self.folder_link = QLineEdit()
        self.folder_link.setPlaceholderText(tr('Ou colle le lien de ton dossier PrépaPilot'))
        self.folder_link.setMaxLength(500)
        self.folder_link.setAccessibleName(tr('Lien d’un dossier de sauvegardes PrépaPilot'))
        self.link_button = button(tr('Utiliser ce dossier'), self.use_folder_link)
        row.addWidget(self.folder_link, 1)
        row.addWidget(self.link_button)
        self.body.addLayout(row)
        self._text(tr('PrépaPilot accède uniquement aux fichiers et dossiers qu’il crée. Sur un autre PC, ouvre PrépaPilot et reconnecte-toi au même compte Google pour retrouver tes sauvegardes.'))

        self._text(tr('Ce que tu emportes'), 'sectionTitle')
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)
        self.choices = {}
        for i, (key, label) in enumerate(CATEGORIES.items()):
            choice = QCheckBox(tr(label))
            choice.setChecked(key in saved['selection'])
            choice.toggled.connect(self.refresh_controls)
            grid.addWidget(choice, i, 0)
            self.choices[key] = choice
        self.body.addLayout(grid)
        self._text(tr('Les succès et les quêtes accomplis sont toujours sauvegardés, même sans le journal ou le sommeil. Les matières et les années nécessaires sont incluses automatiquement. Les connexions Google restent sur ce PC.'))
        self.backup_button = button(tr('Sauvegarder maintenant'), self.backup, primary=True)
        self.body.addWidget(self.backup_button, 0, Qt.AlignLeft)
        self.last_backup = self._text('')

        self._text(tr('Garder le réflexe'), 'sectionTitle')
        row = QHBoxLayout()
        self.reminders = QCheckBox(tr('Me rappeler de sauvegarder'))
        self.reminders.setChecked(saved['reminders'])
        self.interval = QComboBox()
        for days, label in ((7, tr('Chaque semaine')), (3, tr('Tous les 3 jours')), (1, tr('Chaque jour'))):
            self.interval.addItem(label, days)
        self.interval.setCurrentIndex(max(0, self.interval.findData(saved['reminder_days'])))
        self.interval.setAccessibleName(tr('Fréquence du rappel de sauvegarde'))
        row.addWidget(self.reminders)
        row.addWidget(self.interval)
        row.addStretch()
        self.body.addLayout(row)
        self.save_button = button(tr('Enregistrer mes choix'), self.save_preferences)
        self.body.addWidget(self.save_button, 0, Qt.AlignLeft)
        self._text(tr('Le rappel apparaît dans l’application. Si elle est fermée, il apparaît à la prochaine ouverture. Rien n’est envoyé sans ton action.'))

        self._text(tr('Retrouver une sauvegarde'), 'sectionTitle')
        self.snapshots = QComboBox()
        self.snapshots.setAccessibleName(tr('Version de la sauvegarde à restaurer'))
        self.snapshots.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.snapshots.setMinimumContentsLength(20)
        self.snapshots.addItem(tr('Afficher les sauvegardes du dossier choisi…'), None)
        self.snapshots.currentIndexChanged.connect(self.snapshot_changed)
        self.body.addWidget(self.snapshots)
        self.snapshot_detail = self._text('')
        row = QHBoxLayout()
        self.history_button = button(tr('Afficher les sauvegardes'), self.load_history)
        self.restore_button = button(tr('Vérifier et importer…'), self.restore)
        row.addWidget(self.history_button)
        row.addWidget(self.restore_button)
        row.addStretch()
        self.body.addLayout(row)
        self._text(tr('Tu verras un récapitulatif avant de confirmer. Seules les catégories incluses seront remplacées ; les autres resteront sur ce PC. Les succès sauvegardés rejoignent ta collection sans retirer ceux déjà obtenus ici. Une copie de sécurité locale sera créée avant l’import.'))
        self.advanced_button = button(tr('Options avancées'), self.toggle_advanced)
        self.advanced_button.setCheckable(True)
        self.advanced_button.setAccessibleName(tr('Afficher les options avancées de connexion Google'))
        self.body.addWidget(self.advanced_button, 0, Qt.AlignLeft)
        self.advanced_options = QWidget()
        advanced = QVBoxLayout(self.advanced_options)
        advanced.setContentsMargins(0, 0, 0, 0)
        advanced.setSpacing(10)
        advanced_text = QLabel(tr('La connexion Google fournie avec PrépaPilot suffit normalement. Cette option permet à l’éditeur ou aux utilisateurs expérimentés d’utiliser leur propre configuration Google. Si tu en utilises une, conserve la même sur tes différents PC pour retrouver tes sauvegardes.'), objectName='muted')
        advanced_text.setTextFormat(Qt.PlainText)
        advanced_text.setWordWrap(True)
        advanced.addWidget(advanced_text)
        self.configure_button = button(tr('Importer une configuration personnelle…'), self.configure_google)
        advanced.addWidget(self.configure_button, 0, Qt.AlignLeft)
        self.advanced_options.hide()
        self.body.addWidget(self.advanced_options)
        self.body.addStretch()
        layout.addWidget(scroll_page(content), 1)

        self.status = QLabel(tr('Prêt lorsque tu le souhaites.'), objectName='muted')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.hide()
        layout.addWidget(self.progress)
        footer = QHBoxLayout()
        self.cancel_button = button(tr('Annuler le transfert'), self.cancel_work)
        self.cancel_button.hide()
        footer.addWidget(self.cancel_button)
        footer.addStretch()
        self.close_button = button(tr('Fermer'), self.reject)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)
        self.progress_message.connect(self.status.setText)
        self.refresh_controls()

    def _text(self, text, style='muted'):
        label = QLabel(text, objectName=style)
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        self.body.addWidget(label)
        return label

    def selected(self):
        return [key for key, choice in self.choices.items() if choice.isChecked()]

    def folder_id(self):
        return self.folders.currentData() or ''

    def refresh_controls(self, *_):
        if not hasattr(self, 'close_button'):
            return
        available = not self.running
        connected = self.connection.connected
        configured = self.connection.configured
        self.connect_button.setEnabled(available and configured and not connected)
        self.connect_button.setVisible(not connected)
        self.disconnect_button.setEnabled(available and connected)
        self.disconnect_button.setVisible(connected)
        self.configure_button.setEnabled(available and not connected)
        self.advanced_button.setEnabled(available)
        for control in (self.folders, self.find_button, self.create_button, self.folder_link, self.link_button):
            control.setEnabled(available and connected)
        for control in (self.open_button, self.history_button):
            control.setEnabled(available and connected and bool(self.folder_id()))
        self.backup_button.setEnabled(available and connected and bool(self.folder_id()) and bool(self.selected()))
        self.restore_button.setEnabled(available and connected and bool(self.snapshots.currentData()))
        self.snapshots.setEnabled(available)
        for control in (*self.choices.values(), self.reminders, self.interval, self.save_button):
            control.setEnabled(available)
        self.cancel_button.setVisible(self.running)
        self.cancel_button.setEnabled(self.running and not (self.cancel_event and self.cancel_event.is_set()))
        self.close_button.setEnabled(available)
        self.progress.setVisible(self.running)
        if connected:
            self.connection_status.setText(tr('Google est connecté sur ce PC. PrépaPilot accède uniquement à ses propres fichiers et dossiers.'))
        elif configured:
            self.connection_status.setText(tr('La connexion est prête. Connecte-toi avec ton compte Google dans ton navigateur habituel pour autoriser PrépaPilot.'))
        else:
            self.connection_status.setText(tr('Cette version de PrépaPilot ne contient pas encore la connexion Google. L’éditeur doit la préparer pour tous les utilisateurs : tu n’as aucun compte développeur à créer. En attendant, utilise Réglages → Exporter toutes mes données pour sauvegarder ton espace.'))
        latest = self.preferences.read()['last_success']
        self.last_backup.setText(tr('Dernière sauvegarde vérifiée : ') + display_date(latest) if latest else tr('Aucune sauvegarde Google Drive vérifiée sur ce PC.'))

    def save_preferences(self):
        if not self.selected():
            show_error(self, tr('Choisis au moins une catégorie à sauvegarder.'))
            return False
        try:
            self.preferences.update(selection=self.selected(), reminders=self.reminders.isChecked(),
                                    reminder_days=self.interval.currentData())
        except OSError:
            show_error(self, tr('Les préférences n’ont pas pu être enregistrées sur ce PC.'))
            return False
        self.changed.emit()
        self.status.setText(tr('Tes choix de sauvegarde sont enregistrés.'))
        return True

    def toggle_advanced(self, checked=False):
        self.advanced_options.setVisible(checked)

    def configure_google(self):
        if self.running or self.connection.connected:
            return
        message = tr('Cette option avancée remplace la configuration Google de cette installation. Elle est destinée à l’éditeur et aux utilisateurs qui possèdent leur propre client OAuth de type « Application de bureau ». Elle n’est pas nécessaire pour se connecter avec une version déjà préparée par l’éditeur.\n\nUtilise la même configuration sur tes autres PC pour retrouver les sauvegardes créées avec cet accès.\n\nSouhaites-tu importer ton fichier de configuration JSON ?')
        if not confirm(self, tr('Configurer Google pour PrépaPilot'), message):
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Configuration OAuth Google · Application de bureau'), '', tr('Configuration Google (*.json)'))
        if not path:
            return
        try:
            self.connection.configure(Path(path))
        except (OSError, ValueError) as exc:
            show_error(self, str(exc))
            return
        self.refresh_controls()
        self.status.setText(tr('Configuration ajoutée. Tu peux maintenant te connecter à Google.'))

    def _start(self, work, handler, message):
        if self.running or self.ctx.busy:
            show_error(self, tr('Attends la fin du traitement en cours.'))
            return
        self.running = True
        self.cancel_event = threading.Event()
        self._pending = self._failure = None
        self._handler = handler
        self.status.setText(message)
        self.refresh_controls()
        cancel = self.cancel_event
        self.ctx.run_job(lambda: work(cancel), self._success, self._error, self._finished)

    @Slot(object)
    def _success(self, value):
        self._pending = value

    @Slot(str)
    def _error(self, value):
        self._failure = value

    @Slot()
    def _finished(self):
        self.running = False
        value, failure, handler = self._pending, self._failure, self._handler
        self._pending = self._failure = self._handler = None
        cancelled = self.cancel_event is not None and self.cancel_event.is_set()
        self.refresh_controls()
        if failure:
            self.status.setText(tr('Opération annulée. Les sauvegardes précédentes sont conservées.') if cancelled else failure)
            return
        try:
            if cancelled and hasattr(value, 'close'):
                value.close()
                self.status.setText(tr('Import annulé. Les données de ce PC sont inchangées.'))
            elif handler:
                handler(value)
        except (OSError, ValueError) as exc:
            if hasattr(value, 'close'):
                value.close()
            self.status.setText(str(exc))
            show_error(self, str(exc))
        finally:
            self.refresh_controls()

    def connect_google(self):
        self.preferences.update(folder_id='', folder_name='', last_success=None, snapshot_id='')
        self._set_folders([])
        def work(cancel):
            self.connection.connect(cancel=cancel)
            return self.connection.client(cancel=cancel).list_backup_folders()
        def connected(folders):
            self.preferences.update(folder_id='', folder_name='', last_success=None, snapshot_id='')
            self._set_folders(folders)
            self.status.setText(tr('Connexion établie. Choisis un dossier existant ou crée ton premier dossier.'))
            self.changed.emit()
        self._start(work, connected, tr('Termine la connexion dans ton navigateur…'))

    def disconnect_google(self):
        if not confirm(self, tr('Déconnecter Google'), tr('Déconnecter ce PC ? Tes sauvegardes resteront dans Google Drive.')):
            return
        self.preferences.update(folder_id='', folder_name='', last_success=None, snapshot_id='')
        self._set_folders([])
        self.changed.emit()
        def disconnected(_):
            self.preferences.update(folder_id='', folder_name='', last_success=None, snapshot_id='')
            self._set_folders([])
            self.changed.emit()
            self.status.setText(tr('Ce PC est déconnecté. Les sauvegardes restent dans Google Drive.'))
        self._start(lambda cancel: self.connection.disconnect(), disconnected, tr('Déconnexion…'))

    def _set_folders(self, folders, selected=None):
        selected = selected or self.preferences.read()['folder_id']
        self.folders.blockSignals(True)
        self.folders.clear()
        self.folders.addItem(tr('Choisir un dossier…'), '')
        for folder in folders:
            self.folders.addItem(str(folder['name'])[:120], folder['id'])
        found = self.folders.findData(selected) if selected else -1
        self.folders.setCurrentIndex(found if found >= 0 else 1 if len(folders) == 1 else 0)
        self.folders.blockSignals(False)
        self.folder_changed()

    def find_folders(self):
        self._start(lambda cancel: self.connection.client(cancel=cancel).list_backup_folders(),
                    self._set_folders, tr('Recherche de tes dossiers PrépaPilot…'))

    def create_folder(self):
        name, accepted = QInputDialog.getText(self, tr('Nouveau dossier Google Drive'), tr('Nom du dossier'), text=tr('PrépaPilot · Mes sauvegardes'))
        name = ''.join(c for c in name.strip() if ord(c) >= 32)[:120]
        if not accepted or not name:
            return
        self._start(lambda cancel: self.connection.client(cancel=cancel).create_folder(name, properties={'prepapilot': 'backup-v1'}),
                    self._add_folder, tr('Création du dossier PrépaPilot…'))

    def _add_folder(self, folder):
        index = self.folders.findData(folder['id'])
        if index < 0:
            self.folders.addItem(str(folder['name'])[:120], folder['id'])
            index = self.folders.count() - 1
        self.folders.setCurrentIndex(index)
        self.folder_link.clear()
        self.status.setText(tr('Dossier prêt pour les sauvegardes et la restauration.'))

    def use_folder_link(self):
        try:
            identity = folder_identifier(self.folder_link.text())
        except ValueError as exc:
            show_error(self, str(exc))
            return
        def work(cancel):
            folder = self.connection.client(cancel=cancel).get_file(identity)
            if folder.get('mimeType') != 'application/vnd.google-apps.folder' or folder.get('appProperties', {}).get('prepapilot') != 'backup-v1':
                raise ValueError(tr('Ce dossier n’est pas un dossier de sauvegardes créé par PrépaPilot.'))
            return folder
        self._start(work, self._add_folder, tr('Vérification du dossier Google Drive…'))

    def folder_changed(self, *_):
        if not hasattr(self, 'snapshots'):
            return
        self.snapshots.clear()
        self.snapshots.addItem(tr('Afficher les sauvegardes du dossier choisi…'), None)
        self.refresh_controls()

    def open_folder(self):
        if self.folder_id():
            QDesktopServices.openUrl(QUrl('https://drive.google.com/drive/folders/' + folder_identifier(self.folder_id())))

    def backup(self):
        if not self.save_preferences():
            return
        folder, name, selection = self.folder_id(), self.folders.currentText(), self.selected()
        def work(cancel):
            return backup_to_drive(self.ctx, self.connection.client(cancel=cancel), folder, selection,
                                   progress=self.progress_message.emit, cancel=cancel)
        def completed(result):
            self.preferences.record_success(result, folder, name, selection)
            self.changed.emit()
            message = (tr('Sauvegarde vérifiée : {v0} nouvel(s) élément(s), {v1} réutilisé(s).', v0=result["uploaded"], v1=result["reused"])
                       if result['changed'] else tr('Tout est déjà sauvegardé. Aucun doublon ajouté ; vérification réussie.'))
            self.status.setText(message)
            self.ctx.notice.emit(message)
        self._start(work, completed, tr('Préparation d’une copie cohérente de tes données…'))

    def load_history(self):
        folder = self.folder_id()
        def loaded(rows):
            self.snapshots.clear()
            if not rows:
                self.snapshots.addItem(tr('Aucune sauvegarde dans ce dossier'), None)
            for row in rows:
                labels = ', '.join(tr(CATEGORIES[key]) for key in row['categories'] if key in CATEGORIES)
                self.snapshots.addItem(display_date(row['created_at']) + ' · ' + labels, row)
            self.snapshot_changed()
            self.status.setText(tr('{count} sauvegarde(s) disponible(s).', count=len(rows)))
        self._start(lambda cancel: list_snapshots(self.connection.client(cancel=cancel), folder), loaded,
                    tr('Recherche des sauvegardes vérifiées…'))

    def snapshot_changed(self, *_):
        if not hasattr(self, 'snapshot_detail'):
            return
        row = self.snapshots.currentData()
        labels = ', '.join(tr(CATEGORIES[key]) for key in row['categories'] if key in CATEGORIES) if row else ''
        self.snapshot_detail.setText(tr('Cette version contient : ') + labels if labels else '')
        self.refresh_controls()

    def restore(self):
        row = self.snapshots.currentData()
        if not row:
            return
        folder, snapshot = self.folder_id(), row['id']
        self._start(lambda cancel: prepare_drive_restore(self.ctx, self.connection.client(cancel=cancel), folder, snapshot,
                    progress=self.progress_message.emit, cancel=cancel), self._confirm_restore,
                    tr('Téléchargement et vérification de la sauvegarde…'))

    def _confirm_restore(self, plan):
        try:
            categories = ', '.join(tr(CATEGORIES[key]) for key in plan.cloud_selection)
            counts = '\n'.join(f'• {plan.cloud_counts[key]} : {tr(CATEGORIES[key])}' for key in plan.cloud_selection
                               if key in plan.cloud_counts and key not in ('preferences', 'timetable'))
            message = (tr('Catégories à restaurer : ') + categories + '\n\n' + counts +
                       tr('\n\nCes catégories remplaceront celles de ce PC. Les autres seront conservées. '
                       'Les succès sauvegardés seront ajoutés à ta collection, sans doublon. '
                       'Une copie locale de l’état actuel sera créée avant le remplacement. Elle sera incomplète si des documents locaux sont déjà manquants ou abîmés. Continuer ?'))
            if not confirm(self, tr('Importer depuis Google Drive'), message):
                self.status.setText(tr('Import annulé. Les données de ce PC sont inchangées.'))
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                validate_restore_target(self.ctx, plan)
                backup = apply_import(self.ctx, plan)
            finally:
                QApplication.restoreOverrideCursor()
            if backup.suffix == '.zip':
                self.status.setText(tr('Import terminé. Copie de récupération incomplète : {file}', file=backup.name))
            else:
                self.status.setText(tr('Import terminé. Copie de sécurité locale : ') + backup.name)
            self.ctx.notice.emit(tr('Données restaurées depuis Google Drive.'))
            self.changed.emit()
        finally:
            plan.close()

    def cancel_work(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.cancel_button.setEnabled(False)
            self.status.setText(tr('Annulation en cours… Le transfert en cours va se terminer proprement.'))

    def reject(self):
        if self.running:
            self.cancel_work()
            return
        super().reject()

    def closeEvent(self, event):
        if self.running:
            self.cancel_work()
            event.ignore()
        else:
            super().closeEvent(event)
