"""Capture the assistant workflow with disposable courses in both languages."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Sources' / 'PrepaPilot'))

from PySide6.QtCore import QEvent
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from mpsi_desktop.context import AppContext
from mpsi_desktop.i18n import set_language
from mpsi_desktop.local_organization import prepare_workspace
from mpsi_desktop.local_organization_dialog import LocalOrganizationDialog
from mpsi_desktop.theme import apply_theme
from mpsi_desktop.window import MainWindow


def main():
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
    app.setFont(QFont('Segoe UI', 10))
    output = ROOT / '.local' / 'Verification' / 'Rangement-IA'
    output.mkdir(parents=True, exist_ok=True)
    errors, captures = [], []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, traceback: errors.append((kind.__name__, str(value)))

    def capture(widget, name):
        if not widget.grab().save(str(output / name)):
            errors.append(('Capture', name))
        captures.append(name)

    try:
        for locale in ('fr', 'en'):
            with tempfile.TemporaryDirectory(prefix='ia-qa-') as temporary:
                ctx = AppContext(Path(temporary) / 'data')
                ctx.db.set_setting('desktop_language', locale)
                ctx.language = locale
                set_language(locale)
                ctx.db.set_setting('desktop_reduced_motion', True)
                folder = ctx.db.create_document_folder('Mathématiques · Suites et limites')
                source = Path(temporary) / 'Suites numériques.txt'
                source.write_text('Cours fictif : suites arithmétiques et géométriques.', encoding='utf-8')
                ctx.db.import_document(source, 'maths', 'cours', folder_id=folder)
                workspace = prepare_workspace(ctx.db)
                path = workspace / 'proposition.json'
                plan = json.loads(path.read_text(encoding='utf-8'))
                plan['documents'][0]['folder'] = 'Mathématiques · Analyse'
                plan['documents'][0]['title'] = 'Suites et limites · Cours'
                (workspace / 'A-importer' / 'td.txt').write_text('Exercices fictifs.', encoding='utf-8')
                plan['imports'].append(dict(source='A-importer/td.txt', title='Suites · TD corrigé',
                    subject='maths', kind='td', description='', folder='Mathématiques · Analyse'))
                path.write_text(json.dumps(plan, ensure_ascii=False), encoding='utf-8')
                ctx.db.set_setting('documents_organization_workspace', str(workspace))
                window = MainWindow(ctx, show_welcome=False)
                window.show()
                window.navigate('documents', animate=False)
                page, wrapper = window.pages['documents'], window.wrappers['documents']
                for theme in ('light', 'dark'):
                    ctx.set_theme(theme)
                    apply_theme(app, theme)
                    for width, height in ((1360, 900), (1024, 680)):
                        window.resize(width, height)
                        app.processEvents()
                        stamp = f'{locale}-{theme}-{width}'
                        wrapper.verticalScrollBar().setValue(0)
                        capture(window, f'documents-{stamp}.png')
                        if page.width() > wrapper.viewport().width() or wrapper.horizontalScrollBar().maximum():
                            errors.append(('PageOverflow', stamp))
                        dialog = LocalOrganizationDialog(ctx, window)
                        dialog.resize(760 if width > 1024 else 600, 640 if height > 680 else 440)
                        dialog.show()
                        app.processEvents()
                        capture(dialog, f'notice-{stamp}.png')
                        dialog.read_proposal()
                        deadline = time.monotonic() + 15
                        while ctx.busy and time.monotonic() < deadline:
                            app.processEvents()
                            QTest.qWait(10)
                        app.processEvents()
                        dialog.scroll.verticalScrollBar().setValue(dialog.scroll.verticalScrollBar().maximum())
                        capture(dialog, f'proposition-{stamp}.png')
                        if not dialog.apply_button.isEnabled():
                            errors.append(('Proposal', dialog.status.text()))
                        if dialog.scroll.horizontalScrollBar().maximum():
                            errors.append(('DialogOverflow', stamp))
                        dialog.close()
                        dialog.deleteLater()
                        app.sendPostedEvents(None, QEvent.DeferredDelete)
                window.close()
                window.deleteLater()
                app.sendPostedEvents(None, QEvent.DeferredDelete)
                app.processEvents()
                ctx.close()
    finally:
        sys.excepthook = previous_hook
        set_language('fr')
    (output / 'rapport.json').write_text(json.dumps(dict(errors=errors, captures=captures), ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(captures)} captures, {len(errors)} erreur(s) : {output}')
    for error in errors:
        print(error)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
