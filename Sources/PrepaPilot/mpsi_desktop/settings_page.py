from .i18n import tr, LANGUAGES, format_datetime
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLayout, QLineEdit, QComboBox, QFormLayout, QCheckBox, QFileDialog, QApplication
from .page_chrome import AccentCard, PageHero
from .widgets import button, show_error, confirm
from .transfers import export_archive, inspect_archive, apply_import
from .study_profile import validate_program
from .cloud_preferences import CloudPreferences, stamp
from .google_auth import GoogleConnection
from .update_panel import UpdatePanel


class SettingsPage(QWidget):
    cloud_changed = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.cloud_preferences = CloudPreferences(ctx.data_dir)
        self.google_connection = GoogleConnection(ctx.data_dir)
        try:
            self.cloud_preferences.ensure_started()
        except OSError:
            pass  # A reminder preference must never prevent access to local data.
        outer = QVBoxLayout(self)
        outer.setSizeConstraint(QLayout.SetMinimumSize)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(20)
        self.hero = PageHero(ctx, 'settings', tr('RÉGLAGES'), tr('Tes préférences'),
                             tr('Profil, apparence et sauvegardes de ton espace.'))
        outer.addWidget(self.hero)
        profile = AccentCard(ctx, 'settings')
        profile.body.setSizeConstraint(QLayout.SetMinimumSize)
        profile.body.addWidget(QLabel(tr('PERSONNALISATION'), objectName='colorEyebrow'))
        profile.body.addWidget(QLabel(tr('Ton espace, tes préférences.'), objectName='sectionTitle'))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(24)
        form.setSpacing(14)
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr('Ton prénom ou ton pseudo'))
        self.name.setMaxLength(40)
        form.addRow(tr('Comment t’appeler ?'), self.name)
        self.program = QLineEdit()
        self.program.setPlaceholderText(tr('Licence, BTS, lycée, formation…'))
        self.program.setMaxLength(80)
        form.addRow(tr('Ton parcours (facultatif)'), self.program)
        self.theme = QComboBox()
        self.theme.addItem(tr('Clair'), 'light')
        self.theme.addItem(tr('Sombre'), 'dark')
        form.addRow(tr('Apparence'), self.theme)
        self.language = QComboBox()
        for key, label in LANGUAGES.items():
            self.language.addItem(label, key)
        self.language.setAccessibleName(tr('Changer la langue de l’application'))
        self.language.setToolTip(tr('La langue s’applique à toute l’interface. Tes textes personnels restent inchangés.'))
        form.addRow(tr('Langue'), self.language)
        self.motion = QCheckBox(tr('Réduire les animations'))
        form.addRow(tr('Confort visuel'), self.motion)
        profile.body.addLayout(form)
        profile.body.addWidget(button(tr('Enregistrer mon profil'), self.save_profile, primary=True), 0, Qt.AlignLeft)
        outer.addWidget(profile)
        self.update_panel = UpdatePanel(ctx, ctx.updates)
        outer.addWidget(self.update_panel)
        transfer = AccentCard(ctx, 'home')
        transfer.body.setSizeConstraint(QLayout.SetMinimumSize)
        transfer.body.addWidget(QLabel(tr('SAUVEGARDE ET TRANSFERT'), objectName='colorEyebrow'))
        transfer.body.addWidget(QLabel(tr('Transférer mes données'), objectName='sectionTitle'))
        info = QLabel(tr('Un fichier .prepapilot rassemble tes notes, tes documents originaux, tes repères, ton emploi du temps, tes séances de travail et tes réglages. Exporte-le ici, puis importe-le sur l’autre PC.'))
        info.setWordWrap(True)
        info.setObjectName('muted')
        transfer.body.addWidget(info)
        row = QHBoxLayout()
        row.addWidget(button(tr('Exporter toutes mes données'), self.export_all, primary=True))
        row.addWidget(button(tr('Importer mes données'), self.import_all))
        row.addStretch()
        transfer.body.addLayout(row)
        detail = QLabel(tr('L’import remplace les données de ce PC après vérification et confirmation. Une sauvegarde automatique de l’état actuel permet de revenir en arrière. Le fichier d’export contient tes données personnelles : garde-le pour toi.'))
        detail.setWordWrap(True)
        detail.setObjectName('muted')
        transfer.body.addWidget(detail)
        outer.addWidget(transfer)
        cloud = AccentCard(ctx, 'progression')
        cloud.body.addWidget(QLabel(tr('GOOGLE DRIVE'), objectName='colorEyebrow'))
        cloud.body.addWidget(QLabel(tr('Sauvegardes Google Drive'), objectName='sectionTitle'))
        cloud_info = QLabel(tr('Sauvegarde les catégories de ton choix, retrouve-les sur un autre PC et garde un rappel chaque semaine. Les données et fichiers inchangés sont réutilisés.'))
        cloud_info.setWordWrap(True)
        cloud_info.setObjectName('muted')
        cloud.body.addWidget(cloud_info)
        self.cloud_status = QLabel('', objectName='muted')
        self.cloud_status.setWordWrap(True)
        self.cloud_status.setTextFormat(Qt.PlainText)
        cloud.body.addWidget(self.cloud_status)
        cloud.body.addWidget(button(tr('Gérer mes sauvegardes Google Drive'), self.open_cloud, primary=True), 0, Qt.AlignLeft)
        outer.addWidget(cloud)
        self.cloud_changed.connect(self.refresh_cloud)
        self.refresh_cloud()
        data = AccentCard(ctx, 'documents')
        data.body.setSizeConstraint(QLayout.SetMinimumSize)
        data.body.addWidget(QLabel(tr('STOCKAGE LOCAL'), objectName='colorEyebrow'))
        data.body.addWidget(QLabel(tr('Tes données, sur ton PC.'), objectName='sectionTitle'))
        location = QLabel(str(ctx.data_dir))
        location.setTextFormat(Qt.TextFormat.PlainText)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        location.setWordWrap(True)
        location.setObjectName('muted')
        data.body.addWidget(location)
        row = QHBoxLayout()
        row.addWidget(button(tr('Exporter mes notes (CSV)'), self.export_csv))
        row.addWidget(button(tr('Ouvrir le dossier'), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.data_dir)))))
        row.addStretch()
        data.body.addLayout(row)
        outer.addWidget(data)
        outer.addStretch()
        ctx.watch_data(self.refresh, 'profile')
        ctx.data_replaced.connect(self.reset_profile)
        ctx.theme_changed.connect(self.sync_theme)
        self.reset_profile()

    @property
    def preview_revision(self):
        return self.cloud_status.text()

    def refresh_cloud(self):
        values = self.cloud_preferences.read()
        previous = stamp(values['last_success'])
        configured = self.google_connection.configured
        unavailable = tr('La connexion Google n’est pas encore incluse dans cette version. Son éditeur doit la préparer une seule fois pour tous les utilisateurs. Tu peux déjà exporter tes données dans un fichier .prepapilot.')
        if previous:
            text = tr('Dernière sauvegarde vérifiée : ') + format_datetime(previous.astimezone())
        elif configured:
            text = tr('Connecte Google Drive pour préparer ta première sauvegarde.')
        else:
            text = unavailable
        if previous and not configured:
            text += '\n' + unavailable
        if configured and self.cloud_preferences.due():
            text += tr(' C’est le moment de faire une nouvelle sauvegarde.')
        self.cloud_status.setText(text)

    def open_cloud(self):
        if not self._ready():
            return
        from .cloud_dialog import CloudBackupDialog
        dialog = CloudBackupDialog(self.ctx, self)
        dialog.changed.connect(self.cloud_changed.emit)
        dialog.exec()
        dialog.deleteLater()
        self.cloud_changed.emit()

    def sync_theme(self, theme):
        self.theme.setCurrentIndex(max(0, self.theme.findData(theme)))

    def refresh(self):
        if not self.name.isModified() and not self.name.hasFocus():
            self.name.setText(self.ctx.db.get_setting('desktop_name', ''))
        if not self.program.isModified() and not self.program.hasFocus():
            self.program.setText(self.ctx.db.get_setting('desktop_program', ''))

    def reset_profile(self):
        self.name.setText(self.ctx.db.get_setting('desktop_name', ''))
        self.name.setModified(False)
        self.program.setText(self.ctx.db.get_setting('desktop_program', ''))
        self.program.setModified(False)
        self.motion.setChecked(self.ctx.db.get_setting('desktop_reduced_motion', False))
        self.sync_theme(self.ctx.theme)
        self.language.setCurrentIndex(self.language.findData(self.ctx.language))

    def save_profile(self):
        if self.ctx.busy and self.language.currentData() != self.ctx.language:
            show_error(self, tr('Attends la fin du traitement en cours avant de changer de langue.'))
            return
        try:
            program = validate_program(self.program.text())
        except ValueError as exc:
            show_error(self, str(exc))
            return
        self.ctx.db.set_setting('desktop_name', self.name.text().strip())
        self.ctx.db.set_setting('desktop_program', program)
        self.ctx.db.set_setting('desktop_reduced_motion', self.motion.isChecked())
        self.ctx.set_theme(self.theme.currentData())
        self.name.setModified(False)
        self.program.setModified(False)
        self.ctx.mark_changed('profile')
        self.ctx.notice.emit(tr('Ton espace a été personnalisé.'))
        try:
            self.ctx.set_language(self.language.currentData())
        except (OSError, ValueError) as exc:
            show_error(self, str(exc))

    def _ready(self):
        if self.ctx.busy:
            show_error(self, tr('Attends la fin du traitement en cours avant de transférer tes données.'))
            return False
        return True

    def export_all(self):
        if not self._ready():
            return
        path, _ = QFileDialog.getSaveFileName(self, tr('Exporter toutes mes données'), f'PrepaPilot-{datetime.now():%Y-%m-%d}.prepapilot', tr('Sauvegarde PrépaPilot (*.prepapilot)'))
        if not path:
            return
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            export_archive(self.ctx, path)
        except (OSError, ValueError) as exc:
            show_error(self, str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.ctx.notice.emit(tr('Export complet vérifié. Tu peux l’importer sur l’autre PC.'))

    def import_all(self):
        if not self._ready():
            return
        path, _ = QFileDialog.getOpenFileName(self, tr('Importer mes données'), '', tr('Sauvegarde PrépaPilot (*.prepapilot)'))
        if not path:
            return
        plan = None
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                plan = inspect_archive(path, type(self.ctx.db))
            finally:
                QApplication.restoreOverrideCursor()
            message = tr('Cette sauvegarde contient :\n\n') + plan.summary() + tr('\n\nCes données remplaceront celles de ce PC. Une copie de l’état actuel sera conservée dans le dossier backups. Elle sera incomplète si des documents locaux sont déjà manquants ou abîmés. Continuer ?')
            if not confirm(self, tr('Importer cette sauvegarde'), message):
                return
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                backup = apply_import(self.ctx, plan)
            finally:
                QApplication.restoreOverrideCursor()
            message = ('Données importées. Copie de récupération incomplète : {file}'
                       if backup.suffix == '.zip' else 'Données importées. Sauvegarde précédente : {file}')
            self.ctx.notice.emit(tr(message, file=backup.name))
        except (OSError, ValueError) as exc:
            show_error(self, str(exc))
        finally:
            if plan:
                plan.close()

    def export_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Exporter les notes'), tr('mes-notes.csv'), 'CSV (*.csv)')
        if path:
            try:
                Path(path).write_text(self.ctx.db.export_grades_csv(), encoding='utf-8-sig')
            except OSError as exc:
                show_error(self, str(exc))
                return
            self.ctx.notice.emit(tr('Notes exportées.'))
