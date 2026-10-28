"""Background updates with durable device preferences and an explicit install action."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QProgressBar

from . import __version__
from .app_updates import check_release, download_release
from .i18n import tr
from .page_chrome import AccentCard
from .widgets import button


def _utc_now():
    return datetime.now(timezone.utc)


class UpdateController(QObject):
    """The context owns this object, so downloads survive a page being rebuilt.

    No installer is launched here. The application handles ``install_requested``
    only after the download worker has finished and released its busy state.
    """
    changed = Signal()
    available = Signal(object)
    install_requested = Signal(object)
    _progress = Signal(int)

    def __init__(self, ctx, repository=None, *, current_version=__version__, installed=True,
                 cache_dir=None, check_func=None, download_func=None):
        super().__init__(ctx)
        self.ctx = ctx
        self.repository = repository
        self.current_version = current_version
        self.installed = installed
        self.cache_dir = Path(cache_dir or (ctx.data_dir / 'updates' / 'downloads'))
        self.preference_path = ctx.data_dir / 'updates' / 'preferences.json'
        self._preferences = self._read_preferences()
        self._check = check_func or check_release
        self._download = download_func or download_release
        self.state = 'idle' if repository else 'unavailable'
        self.release = None
        self.downloaded_path = None
        self.downloaded_sha256 = None
        self.progress_percent = 0
        self.error_code = None
        self._install_pending = False
        self._announced_version = None
        self._progress.connect(self._record_progress)

    @property
    def automatic(self):
        return self._preferences['automatic']

    @property
    def working(self):
        return self.state in ('checking', 'downloading')

    def _read_preferences(self):
        values = {'automatic': True, 'last_attempt': None}
        try:
            if self.preference_path.stat().st_size > 4096:
                return values
            saved = json.loads(self.preference_path.read_text(encoding='utf-8'))
        except (OSError, ValueError, RecursionError):
            return values
        if not isinstance(saved, dict):
            return values
        if type(saved.get('automatic')) is bool:
            values['automatic'] = saved['automatic']
        stamp = saved.get('last_attempt')
        if isinstance(stamp, str):
            try:
                parsed = datetime.fromisoformat(stamp)
                if parsed.tzinfo is not None:
                    values['last_attempt'] = parsed.astimezone(timezone.utc).isoformat()
            except ValueError:
                pass
        return values

    def _save_preferences(self, **changes):
        values = dict(self._preferences, **changes)
        self.preference_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preference_path.with_name('.preferences-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(values, indent=2), encoding='utf-8')
            temporary.replace(self.preference_path)
        finally:
            temporary.unlink(missing_ok=True)
        self._preferences = values

    def set_automatic(self, enabled):
        try:
            self._save_preferences(automatic=bool(enabled))
        except OSError:
            self.ctx.notice.emit(tr('Le réglage des mises à jour n’a pas pu être enregistré. Réessaie.'))
            self.changed.emit()
            return False
        self.changed.emit()
        return True

    def due(self, now=None):
        if not self.repository or not self.automatic or self.working:
            return False
        now = now or _utc_now()
        previous = self._preferences['last_attempt']
        if previous is None:
            return True
        previous = datetime.fromisoformat(previous)
        # A corrected device clock must not suppress checks indefinitely.
        return now < previous or now >= previous + timedelta(days=1)

    def check(self, automatic=False):
        if not self.repository or self.working or (automatic and not self.due()):
            return False
        try:
            self._save_preferences(last_attempt=_utc_now().isoformat())
        except OSError:
            # Still avoid repeated network attempts in this application session.
            self._preferences['last_attempt'] = _utc_now().isoformat()
        self.state, self.error_code = 'checking', None
        self.changed.emit()

        def work():
            try:
                return ('ok', self._check(self.repository, self.current_version))
            except Exception as exc:
                return ('error', getattr(exc, 'code', 'network'))

        self.ctx.run_job(work, self._checked, self._check_failed)
        return True

    @Slot(object)
    def _checked(self, result):
        status, value = result
        if status != 'ok':
            self.error_code, self.state = value, 'error'
            self.changed.emit()
            return
        self.release = value
        self.downloaded_path = None
        self.downloaded_sha256 = None
        self.state = 'available' if value is not None else 'current'
        self.changed.emit()
        if value is not None and value.version != self._announced_version:
            self._announced_version = value.version
            self.available.emit(value)

    @Slot(str)
    def _check_failed(self, _message):
        self.error_code, self.state = 'network', 'error'
        self.changed.emit()

    def download_and_install(self):
        if not self.installed or self.working or self.release is None or self.ctx.busy:
            return False
        if self.downloaded_path is not None and self.downloaded_path.is_file():
            self.install_requested.emit(self.downloaded_path)
            return True
        release = self.release
        self.downloaded_path = None
        self.downloaded_sha256 = None
        self._install_pending = True
        self.progress_percent = 0
        self.state, self.error_code = 'downloading', None
        self.changed.emit()

        def work():
            previous = [-1]

            def progress(done, total):
                percent = max(0, min(100, int(done * 100 / total))) if total else -1
                if percent != previous[0]:
                    previous[0] = percent
                    self._progress.emit(percent)
            try:
                path = Path(self._download(release, self.cache_dir, progress=progress))
                with path.open('rb') as stream:
                    checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
                return ('ok', (path, checksum))
            except Exception as exc:
                return ('error', getattr(exc, 'code', 'disk_error'))

        self.ctx.run_job(work, self._downloaded, self._download_failed, self._download_finished)
        return True

    def activate_release(self):
        if self.installed:
            return self.download_and_install()
        if self.release is None or self.working:
            return False
        return QDesktopServices.openUrl(QUrl(self.release.release_url))

    def invalidate_download(self):
        """Offer a fresh download after the final install check rejected its file."""
        if self.working:
            return False
        self.downloaded_path = None
        self.downloaded_sha256 = None
        self._install_pending = False
        self.state = 'available' if self.release is not None else 'idle'
        self.changed.emit()
        return True

    @Slot(int)
    def _record_progress(self, percent):
        if self.state == 'downloading':
            self.progress_percent = percent
            self.changed.emit()

    @Slot(object)
    def _downloaded(self, result):
        status, value = result
        if status != 'ok':
            self.error_code, self.state = value, 'error'
            self._install_pending = False
        else:
            path, checksum = value
            self.downloaded_path = Path(path)
            self.downloaded_sha256 = checksum
            self.state = 'ready'
            self.progress_percent = 100
        self.changed.emit()

    @Slot(str)
    def _download_failed(self, _message):
        self.error_code, self.state = 'disk_error', 'error'
        self._install_pending = False
        self.changed.emit()

    @Slot()
    def _download_finished(self):
        if self._install_pending and self.state == 'ready':
            self._install_pending = False
            self.install_requested.emit(self.downloaded_path)

    def status_text(self):
        if self.state == 'unavailable':
            return tr('Les mises à jour ne sont pas encore disponibles pour cette version.')
        if self.state == 'checking':
            return tr('Recherche d’une mise à jour…')
        if self.state == 'current':
            return tr('PrépaPilot est à jour.')
        if self.state == 'available':
            return tr('PrépaPilot {version} est disponible.', version=self.release.version)
        if self.state == 'downloading':
            return tr('Téléchargement et vérification de la mise à jour…')
        if self.state == 'ready':
            return tr('La mise à jour est prête à être installée.')
        if self.state == 'error':
            if self.error_code == 'network':
                return tr('Impossible de rechercher ou de télécharger la mise à jour. Vérifie ta connexion puis réessaie.')
            if self.error_code == 'rate_limited':
                return tr('Le service de mise à jour est temporairement occupé. Réessaie plus tard.')
            if self.error_code == 'disk_error':
                return tr('Le téléchargement n’a pas pu être enregistré. Vérifie l’espace disponible puis réessaie.')
            if self.error_code in ('invalid_checksum', 'checksum_mismatch', 'download_size', 'invalid_installer'):
                return tr('Le fichier téléchargé n’a pas pu être vérifié. Réessaie pour récupérer une copie complète.')
            return tr('Cette mise à jour n’est pas disponible pour le moment. Réessaie plus tard.')
        return tr('Recherche une nouvelle version quand tu le souhaites.')


class UpdatePanel(AccentCard):
    def __init__(self, ctx, controller, parent=None):
        super().__init__(ctx, 'settings', parent)
        self.controller = controller
        self.body.addWidget(QLabel(tr('MISES À JOUR'), objectName='colorEyebrow'))
        self.body.addWidget(QLabel(tr('PrépaPilot continue de progresser.'), objectName='sectionTitle'))
        self.version = QLabel(tr('Version installée : {version}', version=controller.current_version), objectName='muted')
        self.body.addWidget(self.version)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.PlainText)
        self.status.setAccessibleName(tr('État des mises à jour'))
        self.body.addWidget(self.status)
        self.automatic = QCheckBox(tr('Rechercher automatiquement les mises à jour une fois par jour'))
        self.automatic.toggled.connect(controller.set_automatic)
        self.body.addWidget(self.automatic)
        self.progress = QProgressBar()
        self.progress.setAccessibleName(tr('Téléchargement de la mise à jour'))
        self.body.addWidget(self.progress)
        row = QHBoxLayout()
        self.check_button = button(tr('Rechercher une mise à jour'), controller.check)
        self.install_button = button(tr('Télécharger et installer'), controller.activate_release, primary=True)
        row.addWidget(self.check_button)
        row.addWidget(self.install_button)
        row.addStretch()
        self.body.addLayout(row)
        detail = ('PrépaPilot se fermera pour installer la mise à jour. Tes données et tes réglages seront conservés.'
                  if controller.installed else
                  'Version portable : récupère la nouvelle version et transfère tes données depuis les réglages.')
        self.detail = QLabel(tr(detail), objectName='muted')
        self.detail.setWordWrap(True)
        self.body.addWidget(self.detail)
        controller.changed.connect(self.refresh)
        ctx.jobs_changed.connect(self.refresh)
        self.refresh()

    @Slot()
    def refresh(self, *_):
        controller = self.controller
        self.status.setText(controller.status_text())
        previous = self.automatic.blockSignals(True)
        self.automatic.setChecked(controller.automatic)
        self.automatic.blockSignals(previous)
        self.automatic.setEnabled(bool(controller.repository))
        self.check_button.setEnabled(bool(controller.repository) and not controller.working)
        self.install_button.setVisible(controller.release is not None)
        self.install_button.setEnabled(controller.release is not None and not controller.working and not self.ctx.busy)
        label = ('Voir la nouvelle version' if not controller.installed else
                 'Installer la mise à jour' if controller.downloaded_path else 'Télécharger et installer')
        self.install_button.setText(tr(label))
        self.detail.setVisible(controller.release is not None)
        self.progress.setVisible(controller.state == 'downloading')
        if controller.progress_percent < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(controller.progress_percent)
