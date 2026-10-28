"""Render document folders and global search with disposable demonstration data."""
import os
from pathlib import Path
import sys
import tempfile

from chemins import local_root


def main():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'Sources' / 'PrepaPilot'))
    from PySide6.QtCore import QEvent, QLocale
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    from mpsi_desktop.context import AppContext
    from mpsi_desktop.documents_page import DocumentFolderDialog, DocumentMetadataDialog, MoveDocumentsDialog
    from mpsi_desktop.window import MainWindow

    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    app.setStyle('Fusion')
    QLocale.setDefault(QLocale('fr_FR'))
    for name in ('segoeui.ttf', 'segoeuib.ttf', 'seguisb.ttf', 'segoeuil.ttf'):
        QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + name)
    output = local_root() / 'Verification' / 'Dossiers'
    output.mkdir(parents=True, exist_ok=True)
    errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: errors.append((kind.__name__, str(value)))
    try:
        with tempfile.TemporaryDirectory(prefix='prepapilot-dossiers-qa-') as temporary:
            temporary = Path(temporary)
            ctx = AppContext(temporary / 'data')
            ctx.db.set_setting('desktop_reduced_motion', True)
            ctx.db.set_setting('desktop_name', 'Camille')
            folders = [ctx.db.create_document_folder(name) for name in (
                'Mathématiques · Intégrales',
                'Anglais · Expression orale',
                'Révisions ' + 'x' * 90,
            )]
            identities = []
            for filename, subject, kind, title, folder_id, content in (
                ('cours-integrales.txt', 'maths', 'cours', 'Intégrales · Cours et méthodes', folders[0],
                 'CHAPITRE 4 — INTÉGRALES\n\n1. Primitives et théorème fondamental\n2. Intégration par parties\n3. Changement de variable\n\nRepères : identifier la méthode, poser les bornes et vérifier le résultat.'),
                ('td-integrales.txt', 'maths', 'td', 'Intégrales · Exercices corrigés', folders[0],
                 'Exercices 1 à 12\n\nFaire un premier essai sans regarder la correction.'),
                ('oral-anglais.txt', 'anglais', 'cours', 'Préparer une présentation', folders[1],
                 'Introduction, arguments, exemples et conclusion.'),
                ('fiche-physique.txt', 'physique', 'tp', 'Mesures et incertitudes', None,
                 'Compte rendu de travaux pratiques et méthode de calcul.'),
            ):
                source = temporary / filename
                source.write_text(content, encoding='utf-8')
                identities.append(ctx.db.import_document(source, subject, kind, title=title, folder_id=folder_id))
            window = MainWindow(ctx, show_welcome=False)
            window.show()
            window.navigate('documents', animate=False)
            page = window.pages['documents']
            wrapper = window.wrappers['documents']
            for width, height in ((1360, 900), (1024, 680)):
                window.resize(width, height)
                for theme in ('light', 'dark'):
                    ctx.set_theme(theme)
                    page.search.clear()
                    page.folder_filter.setCurrentIndex(page.folder_filter.findData(folders[0]))
                    wrapper.verticalScrollBar().setValue(0)
                    QTest.qWait(30)
                    window.grab().save(str(output / f'dossiers-{theme}-{width}.png'))
                    if page.width() > wrapper.viewport().width():
                        errors.append(('PageOverflow', f'{theme}/{width}: {page.width()}/{wrapper.viewport().width()}'))
                    wrapper.verticalScrollBar().setValue(wrapper.verticalScrollBar().maximum())
                    QTest.qWait(20)
                    window.grab().save(str(output / f'dossiers-bas-{theme}-{width}.png'))
                    page.search.setText('oral-anglais')
                    QTest.qWait(150)
                    window.grab().save(str(output / f'recherche-globale-{theme}-{width}.png'))
                    if page.documents.count() != 1 or page.folder_filter.isEnabled():
                        errors.append(('GlobalSearch', f'{theme}/{width}'))
                    page.search.clear()
                    page.folder_filter.setCurrentIndex(page.folder_filter.findData(folders[2]))
                    QTest.qWait(150)
                    window.grab().save(str(output / f'dossier-long-{theme}-{width}.png'))
                    if page.width() > wrapper.viewport().width():
                        errors.append(('LongFolderOverflow', f'{theme}/{width}'))
                    dialogs = (
                        ('creer', DocumentFolderDialog(ctx, parent=window)),
                        ('renommer', DocumentFolderDialog(ctx, {'id': folders[2], 'name': 'Révisions ' + 'x' * 90}, parent=window)),
                        ('ranger', MoveDocumentsDialog(ctx, identities[:2], folders[2], parent=window)),
                        ('importer', DocumentMetadataDialog(ctx, count=2, parent=window, folder_id=folders[2])),
                        ('modifier', DocumentMetadataDialog(ctx, ctx.db.get_document(identities[0]), parent=window)),
                    )
                    for name, dialog in dialogs:
                        dialog.show()
                        QTest.qWait(20)
                        dialog.grab().save(str(output / f'{name}-{theme}-{width}.png'))
                        if dialog.height() > 640 or dialog.width() > 1024:
                            errors.append(('DialogOverflow', f'{name}/{theme}/{width}: {dialog.width()}x{dialog.height()}'))
                        button_bottom = dialog.save_button.mapTo(dialog, dialog.save_button.rect().bottomRight()).y()
                        if button_bottom >= dialog.height() or not dialog.save_button.isVisible():
                            errors.append(('SaveButtonClipped', f'{name}/{theme}/{width}'))
                        dialog.reject()
                        dialog.deleteLater()
            window.close()
            window.deleteLater()
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            ctx.close()
    finally:
        sys.excepthook = previous_hook
    print('Captures :', output)
    print('Qt/layout errors:', errors)
    return bool(errors)


if __name__ == '__main__':
    raise SystemExit(main())
