from .i18n import tr, set_language, language, load_saved_language
import argparse
from pathlib import Path
import sys
import tempfile
import traceback
import os

from PySide6.QtCore import QLocale, QTimer, QLockFile, QAbstractAnimation, QEventLoop
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from .context import AppContext, prepare_data, app_root
from .theme import apply_theme
from .window import MainWindow
from .onboarding import run_initial_setup


def main(startup=None):
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-dir")
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--language", choices=("fr", "en"))
    args=parser.parse_args()
    app=QApplication(sys.argv[:1])
    app.setApplicationName("PrépaPilot")
    app.setOrganizationName("PrépaPilot")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI",10))
    if args.language:
        set_language(args.language)
    temporary=None
    if args.self_test:
        temporary=tempfile.TemporaryDirectory(prefix="mpsi-app-test-")
        data,migrated=prepare_data(temporary.name,migrate=False)
    elif args.data_dir:
        data,migrated=Path(args.data_dir),False
    else:
        data,migrated=prepare_data()
    data.mkdir(parents=True,exist_ok=True)
    set_language(args.language or load_saved_language(data))
    if startup is not None:
        startup.update(tr('Retrouver tes données…'), language=language())
    lock=QLockFile(str(data/"application.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        if startup is not None:
            startup.close()
        QMessageBox.information(None,tr("Application déjà ouverte"),tr("PrépaPilot est déjà ouvert. Retrouve sa fenêtre dans la barre des tâches."))
        return 0
    ctx=None
    failures=[]
    previous_hook=sys.excepthook
    try:
        ctx=AppContext(data)
        ctx.update_checks_enabled = not args.self_test
        if args.self_test:
            ctx.set_language(args.language or 'fr')
        elif args.language:
            ctx.set_language(args.language)
        else:
            from .language_choice import choose_language
            if ctx.db.get_setting('desktop_language') not in ('fr', 'en') and startup is not None:
                startup.close()
            if not choose_language(ctx):
                return 0
        if startup is not None:
            startup.update(tr('Préparation de tes pages…'), theme=ctx.theme,
                           reduced_motion=ctx.db.get_setting('desktop_reduced_motion', False), language=ctx.language)
        if migrated:
            ctx.db.set_setting("desktop_migrated",True)
        apply_theme(app,ctx.theme)
        if args.self_test:
            # A native smoke test has no human to complete the startup wizard.
            # Only its temporary database receives the example configuration.
            from .schedule_setup import SetupDialog
            setup = SetupDialog(ctx, first_run=True)
            setup.use_example()
            setup.next_step()
            setup.save()
            if setup.result() != QDialog.Accepted or not ctx.db.get_setting("setup_completed", False):
                raise RuntimeError("Initial configuration did not complete")
            setup.deleteLater()
        else:
            if startup is not None and not ctx.db.get_setting('setup_completed', False):
                startup.close()
            if not run_initial_setup(ctx):
                return 0
        window=MainWindow(ctx,show_welcome=not args.self_test,migrated=migrated)
        app._prepapilot_window = window
        def exception_hook(kind,value,tb):
            failures.append(kind.__name__)
            # Diagnostic contains stack locations/types only, no keys or data values.
            locations="\n".join(f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in traceback.extract_tb(tb))
            with (data/"diagnostic.log").open("a",encoding="utf-8") as log:
                log.write(f"{kind.__name__}\n{locations}\n")
            app._prepapilot_window.notify(tr("Cette action n'a pas abouti ({error}). Consulte diagnostic.log dans le dossier de données.", error=kind.__name__),kind='error')
        sys.excepthook=exception_hook
        window.show()
        if startup is not None:
            # Let the real window paint before withdrawing the loading screen.
            app.processEvents(QEventLoop.ExcludeUserInputEvents)
            startup.close()
        if args.self_test:
            def finish_test():
                try:
                    for key in window.pages:
                        window.navigate(key,animate=False)
                        app.processEvents()
                        hero = getattr(window.pages[key], 'hero', None)
                        if hero is not None and (hero.figure.grab().isNull() or hero.grab().isNull()):
                            raise RuntimeError(f'Illustrated header did not render: {key}')
                    from . import __version__
                    update_panel = window.pages['settings'].update_panel
                    if (ctx.update_checks_enabled or ctx.updates.working
                            or window.update_start_timer.isActive() or window.update_check_timer.isActive()
                            or __version__ not in update_panel.version.text() or update_panel.grab().isNull()):
                        raise RuntimeError('Update controls did not render safely without network access')
                    # Grade comparisons use only this disposable database, like the report below.
                    from .notes import GradeDialog
                    notes_page = window.pages['notes']
                    window.navigate('notes', animate=False)
                    notes_page.set_subject('maths')
                    grade_dialog = GradeDialog(ctx, subject='maths', parent=window)
                    if grade_dialog.class_average_enabled.isChecked() or grade_dialog.rank_enabled.isChecked():
                        raise RuntimeError('Grade comparisons should be optional by default')
                    grade_dialog.score.setValue(16)
                    grade_dialog.scale.setValue(40)
                    grade_dialog.label.setText('Évaluation de contrôle')
                    grade_dialog.class_average_enabled.setChecked(True)
                    grade_dialog.class_average.setValue(24)
                    grade_dialog.rank_enabled.setChecked(True)
                    grade_dialog.rank.setValue(5)
                    grade_dialog.class_size.setValue(32)
                    grade_dialog.detail_buttons[1].click()
                    grade_dialog.show()
                    app.processEvents()
                    if grade_dialog.grab().isNull():
                        raise RuntimeError('Optional grade comparison fields did not render')
                    grade_dialog.save()
                    if grade_dialog.result() != QDialog.Accepted or grade_dialog.saved_id is None:
                        raise RuntimeError('Grade comparisons did not save')
                    saved_grade = next(row for row in ctx.grades('maths') if row['id'] == grade_dialog.saved_id)
                    if (saved_grade['class_average'], saved_grade['rank'], saved_grade['class_size']) != (24, 5, 32):
                        raise RuntimeError('Grade comparisons did not persist on the original scale')
                    for mode in ('ranking', 'grades'):
                        notes_page.chart_mode_buttons[mode].click()
                        app.processEvents()
                        if notes_page.chart.mode != mode or notes_page.chart.grab().isNull():
                            raise RuntimeError(f'Grade chart mode did not render: {mode}')
                    if not notes_page.chart._class_series or notes_page.chart._class_series[0][1] != 12:
                        raise RuntimeError('Class average did not normalize to the chart scale')
                    edit_grade = GradeDialog(ctx, grade=saved_grade, parent=window)
                    if not edit_grade.class_average_enabled.isChecked() or not edit_grade.rank_enabled.isChecked():
                        raise RuntimeError('Grade comparisons did not reopen for editing')
                    edit_grade.class_average_enabled.setChecked(False)
                    edit_grade.rank_enabled.setChecked(False)
                    edit_grade.save()
                    cleared_grade = next(row for row in ctx.grades('maths') if row['id'] == saved_grade['id'])
                    if edit_grade.result() != QDialog.Accepted or any(cleared_grade[key] is not None for key in ('class_average', 'rank', 'class_size')):
                        raise RuntimeError('Optional grade comparisons could not be cleared')
                    if notes_page.chart._class_series or notes_page.chart._ranking_series:
                        raise RuntimeError('Cleared grade comparisons remain in the charts')
                    grade_dialog.deleteLater()
                    edit_grade.deleteLater()
                    # Folder organisation and global filename search use only
                    # files inside this disposable self-test workspace.
                    from .documents_page import MoveDocumentsDialog, DocumentFolderDialog
                    source_document = Path(temporary.name) / 'recherche-native.txt'
                    source_document.write_text('Document de contrôle conservé intégralement.', encoding='utf-8')
                    chapter = ctx.db.create_document_folder('Chapitre de contrôle')
                    project = ctx.db.create_document_folder('Projet de contrôle')
                    document_id = ctx.db.import_document(source_document, 'maths', 'cours', title='Titre personnalisé', folder_id=chapter)
                    ctx.mark_changed('documents')
                    documents_page = window.pages['documents']
                    window.navigate('documents', animate=False)
                    documents_page.folder_filter.setCurrentIndex(documents_page.folder_filter.findData(project))
                    documents_page.subject_filter.setCurrentIndex(documents_page.subject_filter.findData('physique'))
                    documents_page.kind_filter.setCurrentIndex(documents_page.kind_filter.findData('td'))
                    documents_page.search.setText('recherche-native')
                    documents_page.refresh()
                    if documents_page.documents.count() != 1 or documents_page._selected_id != document_id:
                        raise RuntimeError('Global filename search did not cross folder and subject filters')
                    move = MoveDocumentsDialog(ctx, [document_id], project, parent=window)
                    move.show()
                    app.processEvents()
                    if move.grab().isNull():
                        raise RuntimeError('Document folder dialog did not render')
                    move.save()
                    if move.result() != QDialog.Accepted or ctx.db.get_document(document_id)['folder_id'] != project:
                        raise RuntimeError('Document could not be moved into its folder')
                    rename = DocumentFolderDialog(ctx, ctx.db.get_document_folder(project), parent=window)
                    rename.name.setText('Projet renommé')
                    rename.save()
                    if rename.result() != QDialog.Accepted or ctx.db.get_document_folder(project)['name'] != 'Projet renommé':
                        raise RuntimeError('Document folder could not be renamed')
                    ctx.db.delete_document_folder(project)
                    if ctx.db.get_document(document_id)['folder_id'] is not None or ctx.db.document_path(document_id).read_bytes() != source_document.read_bytes():
                        raise RuntimeError('Removing a folder did not preserve its document')
                    documents_page.reset_selection()
                    ctx.mark_changed('documents')
                    move.deleteLater()
                    rename.deleteLater()
                    # Check the assistant hand-off in the frozen bundle, using
                    # only the original and database created for this smoke test.
                    import json
                    from .local_organization import prepare_workspace, preview_plan, apply_plan
                    from .local_organization_dialog import LocalOrganizationDialog
                    workspace = prepare_workspace(ctx.db)
                    proposal_path = workspace / 'proposition.json'
                    proposal = json.loads(proposal_path.read_text(encoding='utf-8'))
                    proposal['documents'][0]['folder'] = 'Rangement IA de contrôle'
                    proposal_path.write_text(json.dumps(proposal, ensure_ascii=False), encoding='utf-8')
                    proposal_preview = preview_plan(ctx.db, workspace)
                    apply_plan(ctx.db, workspace, proposal_preview['digest'])
                    organized = ctx.db.get_document(document_id)
                    if (ctx.db.get_document_folder(organized['folder_id'])['name'] != 'Rangement IA de contrôle'
                            or ctx.db.document_path(document_id).read_bytes() != source_document.read_bytes()):
                        raise RuntimeError('Local assistant organisation did not preserve the original')
                    organization_dialog = LocalOrganizationDialog(ctx, window)
                    organization_dialog.resize(600, 440)
                    organization_dialog.show()
                    app.processEvents()
                    if organization_dialog.grab().isNull() or organization_dialog.scroll.horizontalScrollBar().maximum():
                        raise RuntimeError('Local assistant organisation dialog did not render')
                    organization_dialog.close()
                    organization_dialog.deleteLater()
                    ctx.mark_changed('documents')
                    # Exercise the new report against only the disposable test journal.
                    from datetime import datetime, time, timedelta
                    from .focus_session import FocusSession
                    from .focus_dialogs import FocusReviewDialog
                    focus_clock = [datetime.combine(datetime.now().date() - timedelta(days=1), time(22)), 1000.0]
                    home = window.pages['home']
                    home.focus_session = FocusSession(ctx.db, now=lambda: focus_clock[0], monotonic=lambda: focus_clock[1])
                    home.focus_session.start('maths', minutes=2, title='Séance de contrôle')
                    for _ in range(120):
                        focus_clock[0] += timedelta(seconds=1)
                        focus_clock[1] += 1
                        home.focus_session.tick()
                    home._sync_focus()
                    if home.focus_session.status != 'review' or home.timer.isActive():
                        raise RuntimeError('Focus session did not finish for review')
                    review = FocusReviewDialog(ctx, home.focus_session, parent=window)
                    review.show()
                    app.processEvents()
                    if review.grab().isNull():
                        raise RuntimeError('Focus review did not render')
                    review.save()
                    if review.result() != QDialog.Accepted or len(review.saved_ids) != 1:
                        raise RuntimeError('Focus session did not save to the journal')
                    if home.focus_session.save() != review.saved_ids:
                        raise RuntimeError('Focus session save is not idempotent')
                    review.deleteLater()
                    from .progression import build_report, save_targets, acknowledge
                    previous_day = datetime.now().date() - timedelta(days=1)
                    start = datetime.combine(previous_day, time(20))
                    # Evening avoids the example timetable's daytime lessons.
                    ctx.db.add_time_entry('maths', start.isoformat(), (start + timedelta(hours=1)).isoformat(), 'Activité de contrôle')
                    save_targets(ctx.db, dict(work=2100, sleep=3360, sport=150, rest=420))
                    report = build_report(ctx.db, 'month', anchor=previous_day)
                    if report['totals']['work'] < 60 or report['scores']['global'] is None:
                        raise RuntimeError('Progression report did not include the completed activity')
                    acknowledge(ctx.db, report['period_key'], 'work')
                    if 'work' not in build_report(ctx.db, 'month', anchor=previous_day)['acknowledged']:
                        raise RuntimeError('Progression acknowledgement did not persist')
                    ctx.mark_changed()
                    window.navigate('progression', animate=False)
                    if window.pages['progression'].grab().isNull():
                        raise RuntimeError('Progression page did not render')
                    progress_page = window.pages['progression']
                    for figure in progress_page.figures.values():
                        if figure.grab().isNull():
                            raise RuntimeError('Progression illustration did not render')
                    if progress_page.score_orb.grab().isNull() or progress_page.chart.grab().isNull():
                        raise RuntimeError('Progression score or chart did not render')
                    # A separate past date avoids existing sample lessons.
                    from .achievements import SETTING as ACHIEVEMENT_SETTING
                    reward_start = datetime.combine(previous_day - timedelta(days=30), time(0))
                    ctx.db.add_time_entry('sport', reward_start.isoformat(),
                                          (reward_start + timedelta(hours=1)).isoformat(), 'Contrôle des succès sportifs')
                    ctx.mark_changed('activities')
                    if 'sport_total:1' not in ctx.db.get_setting(ACHIEVEMENT_SETTING, {}).get('awards', {}):
                        raise RuntimeError('Sport achievement did not persist')
                    progress_page.set_mode('achievements')
                    app.processEvents()
                    if progress_page.achievement_panel.grab().isNull() or not progress_page.hero_card.isHidden():
                        raise RuntimeError('Achievements mode did not render')
                    if len(progress_page.achievement_panel.family_cards) != 6:
                        raise RuntimeError('Study, sleep and sport collections are incomplete')
                    families = {family['id']: family for family in progress_page.achievement_panel.report['families']}
                    for family_id, targets in (('work_week', (25, 40, 55, 65, 80)),
                                               ('work_month', (100, 160, 220, 260, 320))):
                        if tuple(tier['target'] for tier in families[family_id]['tiers']) != tuple(hours * 60 for hours in targets):
                            raise RuntimeError('Weekly or monthly achievement thresholds are outdated')
                    ctx.set_theme("light")
                    ctx.set_theme("dark")
                    progress_page.set_mode('summary')
                    window.navigate("notes")
                    window.animation.setCurrentTime(window.animation.duration() // 2)
                    if window.transition.isVisible():
                        if window.transition.grab().isNull():
                            raise RuntimeError("Page transition did not render")
                    window.transition.finish()
                    if window.navigation_preview._thumbnail("documents").isNull():
                        raise RuntimeError("Navigation preview did not render")
                    window.navigate("home", animate=False)
                    if window.pages["home"].sculpture.grab().isNull():
                        raise RuntimeError("Study illustration did not render")
                    window.navigation_accent.animation.setCurrentTime(window.navigation_accent.animation.duration())
                    if (window.navigation_accent.grab().isNull()
                            or not window.sidebar.rect().contains(window.navigation_accent.geometry())):
                        raise RuntimeError("Navigation accent did not render within its bounds")
                    # The same card-level pointer route is shipped on all seven
                    # pages. This check only drives the disposable test window.
                    from PySide6.QtCore import QEvent, QPointF
                    from PySide6.QtGui import QHoverEvent
                    from .progression_visuals import axis_palette
                    for key, page in window.pages.items():
                        window.navigate(key, animate=False)
                        card = page.hero_card if key == 'progression' else page.hero
                        point = QPointF(card.width() * .68, card.height() * .55)
                        app.sendEvent(card, QHoverEvent(QEvent.HoverMove, point,
                                                       QPointF(card.mapToGlobal(point.toPoint())), QPointF()))
                        if card.light_animation.state() != QAbstractAnimation.Running:
                            raise RuntimeError('Pointer light did not follow on page: ' + key)
                    for key, card in progress_page.metric_cards.items():
                        if card.property('materialAccent') != axis_palette(key, ctx.theme)['accent']:
                            raise RuntimeError('Progression axis lost its own colour')
                    ctx.db.set_setting("desktop_reduced_motion", True)
                    ctx.mark_changed()
                    if window.navigation_accent.animation.state() == QAbstractAnimation.Running:
                        raise RuntimeError('Reduced motion did not stop the navigation accent')
                    if any(animation.state() == QAbstractAnimation.Running for animation in progress_page.findChildren(QAbstractAnimation)):
                        raise RuntimeError('Reduced motion did not stop progression effects')
                    for page in window.pages.values():
                        hero = getattr(page, 'hero', None)
                        if hero is not None and any(animation.state() == QAbstractAnimation.Running for animation in hero.findChildren(QAbstractAnimation)):
                            raise RuntimeError('Reduced motion did not stop page illustrations')
                    window.navigate("settings")
                    if window.transition.isVisible():
                        raise RuntimeError("Reduced motion did not stop transitions")
                    # No account or network is used by this compiled UI check.
                    from .cloud_dialog import CloudBackupDialog
                    from .cloud_preferences import utc_now
                    cloud = CloudBackupDialog(ctx, window)
                    cloud.resize(740, 580)
                    cloud.show()
                    app.processEvents()
                    if cloud.grab().isNull() or cloud.backup_button.isEnabled():
                        raise RuntimeError('Google backup dialog did not render safely without a connection')
                    cloud.close()
                    cloud.deleteLater()
                    from types import SimpleNamespace
                    settings_page = window.pages['settings']
                    settings_page.cloud_preferences.update(first_seen=(utc_now() - timedelta(days=8)).isoformat())
                    real_connection = settings_page.google_connection
                    settings_page.google_connection = SimpleNamespace(configured=False)
                    window.refresh_backup_reminder()
                    if window.backup_reminder.isVisible():
                        raise RuntimeError('Unconfigured Google connection showed an unusable reminder')
                    settings_page.google_connection = SimpleNamespace(configured=True)
                    window.refresh_backup_reminder()
                    if not window.backup_reminder.isVisible():
                        raise RuntimeError('Weekly backup reminder did not appear')
                    window.snooze_backup()
                    if window.backup_reminder.isVisible():
                        raise RuntimeError('Backup reminder did not snooze')
                    settings_page.google_connection = real_connection
                    window.refresh_backup_reminder()
                    # Search/help/session navigation are checked in the frozen
                    # bundle as well as unit tests, using only this temporary DB.
                    from .global_search import GlobalSearchDialog
                    from .help_center import HelpCenterDialog
                    search = GlobalSearchDialog(ctx, window)
                    search.search.setText('recherche-native')
                    search.run_search()
                    search.show()
                    app.processEvents()
                    if search.results.count() != 1 or search.grab().isNull():
                        raise RuntimeError('Global content search did not render its document result')
                    search.activate_selected()
                    if search.result() != QDialog.Accepted or search.selected_result['id'] != document_id:
                        raise RuntimeError('Global search selected an incorrect document')
                    window.open_search_result(search.selected_result)
                    if window.pages['documents']._selected_id != document_id:
                        raise RuntimeError('Global search did not reach the real document')
                    search.deleteLater()
                    help_dialog = HelpCenterDialog(ctx, window.navigate, window)
                    help_dialog.show()
                    for index in range(help_dialog.tabs.count()):
                        help_dialog.tabs.setCurrentIndex(index)
                        app.processEvents()
                        if help_dialog.grab().isNull():
                            raise RuntimeError('Offline help did not render')
                    help_dialog.open_space('notes')
                    if window.current_key != 'notes':
                        raise RuntimeError('Help did not open the requested space')
                    help_dialog.deleteLater()
                    # The frozen program also renders a real navigation frame,
                    # not only the final pages. Only this disposable UI is used.
                    ctx.db.set_setting('desktop_reduced_motion', False)
                    ctx.mark_changed('profile')
                    window.navigate('notes', animate=False)
                    window.navigate('documents', animate=True)
                    layer = window.transition
                    if not layer.isVisible():
                        raise RuntimeError('Directional page transition did not start')
                    layer.animation.pause()
                    layer.advance(.5)
                    if layer.grab().isNull():
                        raise RuntimeError('Directional page transition did not render')
                    layer.finish()
                    ctx.db.set_setting('desktop_reduced_motion', True)
                    ctx.mark_changed('profile')
                    window.notify('Message de contrôle <texte> conservé intégralement.', kind='info')
                    if (window.toast.text() != 'Message de contrôle <texte> conservé intégralement.'
                            or window.toast.height() > window.central.height()
                            or window.toast.grab().isNull()):
                        raise RuntimeError('Readable notification did not render')
                    window.toast.close_button.click()
                    if window.toast.isVisible():
                        raise RuntimeError('Notification could not be dismissed')
                    home.focus_session.start('maths', minutes=2, title='Séance de contrôle de la barre')
                    home._sync_focus()
                    window.navigate('documents', animate=False)
                    if not window.focus_bar.isVisible() or window.focus_bar.grab().isNull():
                        raise RuntimeError('Persistent focus controls did not appear outside home')
                    home.focus_session.pause()
                    home._sync_focus()
                    window.return_to_focus()
                    if home.focus_session.status != 'paused' or window.focus_bar.isVisible():
                        raise RuntimeError('Returning to focus changed the session state')
                    home.focus_session.discard()
                    home._sync_focus()
                    window.showMaximized()
                    app.processEvents()
                    app.processEvents()
                    if not window.isFullScreen():
                        raise RuntimeError("Maximize did not enter full screen")
                    if app.platformName()=="windows":
                        if window.geometry()!=window.screen().geometry():
                            raise RuntimeError("Full screen does not cover the screen")
                        # Qt can retain cached frame margins after maximizing.
                        # Inspect the actual native caption style, not those margins.
                        import ctypes
                        from ctypes import wintypes
                        getter=ctypes.WinDLL("user32",use_last_error=True).GetWindowLongW
                        getter.argtypes=[wintypes.HWND,ctypes.c_int]
                        getter.restype=ctypes.c_long
                        if getter(int(window.winId()),-16) & 0x00C00000:
                            raise RuntimeError("Full screen still has a Windows title bar")
                    window.exit_fullscreen()
                    app.processEvents()
                    if window.isFullScreen() or window.isMaximized():
                        raise RuntimeError("Full screen did not restore the window")
                    if not failures:
                        (app_root()/"self-test-ok.txt").write_text("Application construite : configuration initiale, 7 pages, illustrations, progression, succès (déblocage, persistance, collection et thèmes), moyenne de classe et classement facultatifs, séance de travail, dossiers de documents (rangement, renommage, suppression sans perte et recherche globale par nom), thèmes, aperçus, animations réduites, plein écran et retour en fenêtre, dialogue Google Drive sans connexion réseau et rappel hebdomadaire vérifiés.\n",encoding="utf-8")
                except Exception as exc:
                    failures.append(f"{type(exc).__name__}: {exc}")
                finally:
                    window.close()
                    app.quit()
            QTimer.singleShot(600,finish_test)
        result=app.exec()
        if args.self_test and failures:
            raise RuntimeError("Qt self-test failed: " + ", ".join(failures))
    except Exception as exc:
        if startup is not None:
            startup.close()
        if args.self_test: raise
        QMessageBox.critical(None,tr("Démarrage impossible"),tr("L’application n’a pas pu démarrer ({error}). Vérifie que le dossier est accessible en écriture.", error=type(exc).__name__))
        result=1
    finally:
        if startup is not None:
            startup.close()
        sys.excepthook=previous_hook
        if ctx:ctx.close()
        lock.unlock()
        if temporary:temporary.cleanup()
    if ctx is not None and ctx.pending_installer is not None and result == 0:
        from .update_install import launch_update
        try:
            launch_update(ctx.pending_installer, ctx.language)
        except (OSError, ValueError):
            QMessageBox.warning(None, tr('À vérifier'),
                tr('L’installation n’a pas pu démarrer. Relance PrépaPilot pour réessayer.'))
            result = 1
    return result


if __name__=="__main__":
    raise SystemExit(main())
