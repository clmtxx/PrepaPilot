"""Render cloud settings with fictitious state, without a Google account or network."""
import os
from pathlib import Path
import sys
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from contextlib import ExitStack

from chemins import WORKSPACE, local_root

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, str(WORKSPACE / 'Sources' / 'PrepaPilot'))
from PySide6.QtCore import QLocale
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea
from mpsi_desktop.context import AppContext
from mpsi_desktop.cloud_dialog import CloudBackupDialog
from mpsi_desktop.cloud_preferences import utc_now
from mpsi_desktop.theme import apply_theme
from mpsi_desktop.window import MainWindow

app = QApplication([])
app.setStyle('Fusion')
for font in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf', 'seguiemj.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + font)
app.setFont(QFont('Segoe UI', 10))
QLocale.setDefault(QLocale('fr_FR'))
app.setQuitOnLastWindowClosed(False)
out = local_root() / 'Verification' / 'Interface'
out.mkdir(parents=True, exist_ok=True)
failures = []
def capture_error(kind, value, tb):
    failures.append(kind.__name__ + ': ' + str(value))
    sys.__excepthook__(kind, value, tb)
sys.excepthook = capture_error

with tempfile.TemporaryDirectory(prefix='prepapilot-google-ui-') as temporary, ExitStack() as cleanup:
    ctx = AppContext(Path(temporary) / 'data')
    cleanup.callback(ctx.close)
    ctx.db.set_setting('desktop_reduced_motion', True)
    window = MainWindow(ctx, show_welcome=False)
    cleanup.callback(window.close)
    window.resize(1024, 680)
    window.show()
    for theme in ('light', 'dark'):
        ctx.set_theme(theme)
        apply_theme(app, theme)
        window.navigate('settings', animate=False)
        window.pages['settings'].cloud_preferences.update(first_seen=(utc_now()-timedelta(days=8)).isoformat())
        window.refresh_backup_reminder()
        app.processEvents()
        wrapper = window.wrappers['settings']
        wrapper.ensureWidgetVisible(window.pages['settings'].cloud_status, 0, 100)
        app.processEvents()
        window.grab().save(str(out / f'google-settings-{theme}.png'))
        dialog = CloudBackupDialog(ctx, window, connection=SimpleNamespace(configured=False, connected=False))
        dialog.resize(740, 600)
        dialog.show()
        app.processEvents()
        if dialog.backup_button.isEnabled():
            raise RuntimeError('An unconnected account must not offer an upload')
        dialog.grab().save(str(out / f'google-setup-{theme}.png'))
        dialog.connection.configured = dialog.connection.connected = True
        dialog._set_folders([{'id': 'demo_folder', 'name': 'Mes sauvegardes · Démonstration'}])
        dialog.refresh_controls()
        area = dialog.findChild(QScrollArea)
        area.verticalScrollBar().setValue(area.verticalScrollBar().maximum())
        app.processEvents()
        if not dialog.backup_button.isEnabled():
            raise RuntimeError('The fictitious connected state did not enable backup')
        if area.horizontalScrollBar().maximum() != 0:
            raise RuntimeError('The cloud dialog overflows horizontally')
        dialog.grab().save(str(out / f'google-restore-{theme}.png'))
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
    window.close()
    app.processEvents()
if failures:
    raise RuntimeError('; '.join(failures))
print('Google Drive : réglages, connexion requise, restauration et rappel rendus dans les deux thèmes, sans compte ni réseau.')
print(out)
