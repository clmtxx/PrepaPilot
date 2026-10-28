from .i18n import tr
import sqlite3

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QSize, QPoint, QRect, QAbstractAnimation, QSignalBlocker, QEvent
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QStackedWidget, QGraphicsOpacityEffect, QComboBox, QDialog, QLineEdit,
    QSystemTrayIcon, QStyle, QLayout)

from .widgets import button, scroll_page, AnimatedDialog, show_error, confirm
from .study_profile import validate_program
from .theme import apply_theme, palette_for
from .icons import icon
from .dashboard import DashboardPage
from .notes import NotesPage, GradeDialog
from .time_tracking import TimeTrackingPage
from .documents_page import DocumentsPage
from .memory import MemoryPage
from .settings_page import SettingsPage
from .context import MAX_SCHOOL_YEAR
from .page_transition import PageTransition
from .page_figures import page_palette
from .navigation_preview import NavigationPreview
from .navigation_accent import NavigationAccent
from .notice_card import NoticeCard
from .progression_page import ProgressionPage
from .language_state import capture_inputs, restore_inputs
from .global_search import GlobalSearchDialog
from .focus_bar import FocusSessionBar
from .help_center import HelpCenterDialog
from .quick_actions import QuickAction, QuickActionsDialog


def notice_duration(text):
    """Leave time to read longer messages; interaction can pause this timer."""
    text = str(text)
    reading_units = max(len(text.split()), (len(text) + 6) // 7)
    return max(4200, min(12000, 1800 + 200 * reading_units))


class WelcomeDialog(AnimatedDialog):
    def __init__(self,ctx,parent=None):
        super().__init__(parent)
        self.ctx=ctx
        self.setWindowTitle(tr("Bienvenue dans PrépaPilot"))
        self.setFixedWidth(510)
        layout=QVBoxLayout(self)
        layout.setContentsMargins(34,32,34,32)
        layout.setSpacing(20)
        badge=QLabel(tr("PRÉPAPILOT  /  TON ESPACE D’ÉTUDES"),objectName="eyebrow")
        layout.addWidget(badge)
        title=QLabel(tr("Tes études. À ton rythme."),objectName="pageTitle")
        title.setWordWrap(True)
        layout.addWidget(title)
        text=QLabel(tr("Tes documents, tes progrès et tes journées. Un espace pour prendre du recul et avancer à ton rythme."))
        text.setWordWrap(True)
        text.setObjectName("muted")
        layout.addWidget(text)
        layout.addWidget(QLabel(tr("Comment dois-je t’appeler ?")))
        self.name=QLineEdit()
        self.name.setPlaceholderText(tr("Ton prénom ou ton pseudo"))
        self.name.setMaxLength(40)
        layout.addWidget(self.name)
        layout.addWidget(QLabel(tr("Ton parcours (facultatif)")))
        self.program=QLineEdit()
        self.program.setPlaceholderText(tr("Licence, BTS, lycée, formation…"))
        self.program.setMaxLength(80)
        layout.addWidget(self.program)
        layout.addWidget(button(tr("C’est parti  →"),self.save,primary=True))
        self.name.returnPressed.connect(self.save)

    def save(self):
        try:
            program=validate_program(self.program.text())
        except ValueError as exc:
            show_error(self,str(exc))
            return
        self.ctx.db.set_setting("desktop_name",self.name.text().strip())
        self.ctx.db.set_setting("desktop_program",program)
        self.ctx.db.set_setting("desktop_welcomed",True)
        self.ctx.mark_changed('profile')
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self,ctx,*,show_welcome=True,migrated=False):
        super().__init__()
        self.ctx=ctx
        self.setWindowTitle("PrépaPilot")
        self.setWindowIcon(icon("pilot"))
        screen=QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(1024,680)
        self.resize(min(1390,max(1024,screen.width()-60)),min(930,max(680,screen.height()-60)))
        self._closing=False
        self._windowed_geometry=None
        self.maximize_timer=QTimer(self)
        self.maximize_timer.setSingleShot(True)
        self.maximize_timer.timeout.connect(self.convert_maximized)
        self.nav={}
        self.current_key="home"
        self.central=QWidget()
        self.setCentralWidget(self.central)
        root=QVBoxLayout(self.central)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)
        self.sidebar=QFrame(objectName="Navigation")
        side=QHBoxLayout(self.sidebar)
        side.setContentsMargins(32,12,32,12)
        side.setSpacing(4)
        brand=QHBoxLayout()
        self.brand_icon=QLabel()
        self.brand_icon.setPixmap(icon("pilot",size=30).pixmap(QSize(30,30)))
        brand.addWidget(self.brand_icon)
        brand_labels=QVBoxLayout()
        brand_labels.setSpacing(1)
        name=QLabel("PrépaPilot")
        name.setStyleSheet("font-size:22px; font-weight:650; letter-spacing:-0.8px;")
        brand_labels.addWidget(name)
        brand.addLayout(brand_labels)
        side.addLayout(brand)
        side.addStretch()
        nav_items=[("home",tr("Aujourd’hui"),"home"),("time",tr("Gestion du temps"),"calendar"),
                   ("progression",tr("Progression"),"chart"),("notes",tr("Notes"),"chart"),("documents",tr("Documents"),"book"),
                   ("memory",tr("Mes repères"),"memory")]
        for index,(key,label,symbol) in enumerate(nav_items, 1):
            btn=button(label,lambda checked=False,k=key:self.navigate(k))
            btn.setCheckable(True)
            btn.setProperty("role","nav")
            tooltip = {"notes":tr("Notes et progrès"), "memory":tr("Mes repères")}.get(key,label)
            btn.setToolTip(tr('{title} · Ctrl+{index}', title=tooltip, index=index))
            btn.setAccessibleDescription(tr('Ouvrir avec Ctrl+{index}', index=index))
            side.addWidget(btn)
            self.nav[key]=(btn,symbol)
        side.addStretch()
        self.mode_label=QLabel(tr("●  Enregistré sur ce PC"),objectName="muted")
        self.mode_label.setStyleSheet("font-size:11px;")
        settings=button("",lambda:self.navigate("settings"))
        settings.setFixedSize(42,42)
        settings.setToolTip(tr("Réglages · Ctrl+7"))
        settings.setAccessibleName(tr("Réglages"))
        settings.setCheckable(True)
        settings.setProperty("role","nav")
        settings.setIcon(icon("settings"))
        self.nav["settings"]=(settings,"settings")
        side.addWidget(settings)
        self.navigation_accent=NavigationAccent(self.sidebar,{key:control for key,(control,_) in self.nav.items()})
        root.addWidget(self.sidebar)
        right=QWidget()
        right_layout=QVBoxLayout(right)
        right_layout.setContentsMargins(38,18,38,26)
        right_layout.setSpacing(24)
        topbar=QHBoxLayout()
        self.year=QComboBox()
        self.year.setMinimumWidth(162)
        self.year.setAccessibleName(tr("Année scolaire"))
        self.year.currentIndexChanged.connect(self.select_school_year)
        topbar.addWidget(self.year)
        self.add_year_button=button(tr("+ Année"),self.add_school_year)
        self.add_year_button.setAccessibleName(tr("Ajouter l’année scolaire suivante"))
        topbar.addWidget(self.add_year_button)
        self.sync_year_selector()
        topbar.addSpacing(12)
        topbar.addWidget(self.mode_label)
        topbar.addStretch()
        self.search_button=button('',self.open_global_search)
        self.search_button.setFixedSize(40,40)
        self.search_button.setAccessibleName(tr('Rechercher dans mon espace · Ctrl+F'))
        self.search_button.setToolTip(self.search_button.accessibleName())
        topbar.addWidget(self.search_button)
        self.quick_actions_button=button(tr('Actions rapides · Ctrl+K'),self.open_quick_actions)
        self.quick_actions_button.setAccessibleName(tr('Actions rapides · Ctrl+K'))
        self.quick_actions_button.setToolTip(tr('Rechercher une action ou un espace'))
        topbar.addWidget(self.quick_actions_button)
        self.job_label=QLabel("",objectName="muted")
        topbar.addWidget(self.job_label)
        self.theme_button=button("",self.toggle_theme)
        self.theme_button.setFixedWidth(44)
        self.theme_button.setIconSize(QSize(18,18))
        topbar.addWidget(self.theme_button)
        self.fullscreen_button=button("",self.toggle_fullscreen)
        self.fullscreen_button.setFixedSize(44,40)
        self.fullscreen_button.setIconSize(QSize(18,18))
        self.fullscreen_button.setCheckable(True)
        topbar.addWidget(self.fullscreen_button)
        self.help_button=button('',self.open_help)
        self.help_button.setFixedSize(40,40)
        self.help_button.setAccessibleName(tr('Aide et raccourcis · F1'))
        self.help_button.setToolTip(self.help_button.accessibleName())
        topbar.addWidget(self.help_button)
        right_layout.addLayout(topbar)
        self.backup_reminder = QFrame(objectName='Card')
        reminder_layout = QHBoxLayout(self.backup_reminder)
        reminder_layout.setContentsMargins(16, 10, 16, 10)
        reminder_text = QLabel(tr('Un petit geste pour tes données : pense à faire une sauvegarde Google Drive.'))
        reminder_text.setWordWrap(True)
        reminder_layout.addWidget(reminder_text, 1)
        reminder_layout.addWidget(button(tr('Sauvegarder'), self.open_cloud_backup, primary=True))
        reminder_layout.addWidget(button(tr('Demain'), self.snooze_backup))
        self.backup_reminder.hide()
        right_layout.addWidget(self.backup_reminder)
        self.update_notice = QFrame(objectName='Card')
        update_row = QHBoxLayout(self.update_notice)
        update_row.setContentsMargins(16, 10, 16, 10)
        self.update_notice_text = QLabel()
        self.update_notice_text.setWordWrap(True)
        self.update_notice_text.setTextFormat(Qt.PlainText)
        update_row.addWidget(self.update_notice_text, 1)
        update_row.addWidget(button(tr('Voir la mise à jour'), self.open_update_settings, primary=True))
        self.update_notice.hide()
        right_layout.addWidget(self.update_notice)
        self.stack=QStackedWidget()
        self.pages={
            "home":DashboardPage(ctx,self.navigate), "time":TimeTrackingPage(ctx),
            "progression":ProgressionPage(ctx,self.navigate),
            "notes":NotesPage(ctx), "documents":DocumentsPage(ctx),
            "memory":MemoryPage(ctx), "settings":SettingsPage(ctx),
        }
        home=self.pages['home']
        self.focus_bar=FocusSessionBar(ctx,self.return_to_focus,home.toggle_focus,home.review_focus)
        right_layout.addWidget(self.focus_bar)
        home.focus_updated.connect(self.sync_focus_bar)
        self.wrappers={}
        for key,page in self.pages.items():
            wrapper=scroll_page(page)
            self.stack.addWidget(wrapper)
            self.wrappers[key]=wrapper
        self.transition=PageTransition(self)
        self.animation=self.transition.animation
        right_layout.addWidget(self.stack,1)
        root.addWidget(right,1)
        self.toast=NoticeCard(self.central)
        self.toast.dismissed.connect(self.dismiss_notice)
        self.toast.hide()
        self.toast_animation=QPropertyAnimation(self.toast,b"pos",self)
        self.toast_animation.setDuration(320)
        self.toast_animation.setEasingCurve(QEasingCurve.OutCubic)
        self.toast_timer=QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_fade=QGraphicsOpacityEffect(self.toast)
        self.toast.setGraphicsEffect(self.toast_fade)
        self.toast_exit=QPropertyAnimation(self.toast_fade,b"opacity",self)
        self.toast_exit.setDuration(200)
        self.toast_exit.finished.connect(self.toast.hide)
        self.toast_timer.timeout.connect(self.dismiss_notice)
        self._notice_hold_active = False
        self._notice_remaining_ms = 4200
        self.toast.interaction_changed.connect(self.hold_notice)
        ctx.notice.connect(self.notify)
        ctx.watch_data(self.motion_updated, 'profile')
        ctx.data_changed.connect(self.transition.finish)
        ctx.watch_data(self.sync_year_selector, 'year')
        ctx.data_changed.connect(self.settle_page_layouts)
        ctx.theme_changed.connect(self.theme_updated)
        ctx.data_replaced.connect(self.data_replaced)
        ctx.jobs_changed.connect(self.jobs_updated)
        ctx.language_changed.connect(self.request_language_refresh)
        self.theme_updated(ctx.theme)
        self.motion_updated()
        self.navigate("home",animate=False)
        for i,key in enumerate(self.pages,1):
            QShortcut(QKeySequence(f"Ctrl+{i}"),self,activated=lambda k=key:self.navigate(k))
        QShortcut(QKeySequence("Ctrl+N"),self,activated=self.quick_add)
        self.quick_actions_shortcut=QShortcut(QKeySequence('Ctrl+K'),self,activated=self.open_quick_actions)
        self.search_shortcut=QShortcut(QKeySequence('Ctrl+F'),self,activated=self.open_global_search)
        self.help_shortcut=QShortcut(QKeySequence('F1'),self,activated=self.open_help)
        self.fullscreen_shortcut=QShortcut(QKeySequence("F11"),self,activated=self.toggle_fullscreen)
        self.exit_fullscreen_shortcut=QShortcut(QKeySequence("Escape"),self,activated=self.exit_fullscreen)
        self.sync_fullscreen_control()
        self.tray=None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray=QSystemTrayIcon(self.windowIcon(),self)
            self.tray.setToolTip("PrépaPilot")
            self.tray.activated.connect(lambda *_:self.restore_window())
            self.tray.show()
        self.welcome_timer=QTimer(self)
        self.welcome_timer.setSingleShot(True)
        self.welcome_timer.timeout.connect(lambda:WelcomeDialog(ctx,self).exec())
        if show_welcome and not ctx.db.get_setting("desktop_welcomed",False):
            self.welcome_timer.start(350)
        self.migration_timer=QTimer(self)
        self.migration_timer.setSingleShot(True)
        self.migration_timer.timeout.connect(lambda:self.notify(tr("Tes notes, tes repères et tes documents ont été repris dans PrépaPilot.")))
        if migrated:
            self.migration_timer.start(1000)
        self.school_year_timer=QTimer(self)
        self.school_year_timer.setInterval(60000)
        self.school_year_timer.timeout.connect(ctx.sync_school_years)
        self.school_year_timer.start()
        self.navigation_preview=NavigationPreview(self)
        self.pages['settings'].cloud_changed.connect(self.refresh_backup_reminder)
        self.backup_timer = QTimer(self)
        self.backup_timer.setInterval(60000)
        self.backup_timer.timeout.connect(self.refresh_backup_reminder)
        self.backup_timer.start()
        self.refresh_backup_reminder()
        ctx.updates.changed.connect(self.refresh_update_notice)
        ctx.updates.available.connect(self.announce_update)
        ctx.updates.install_requested.connect(self.install_update)
        self.refresh_update_notice()
        self.update_check_timer = QTimer(self)
        self.update_check_timer.setInterval(60 * 60 * 1000)
        self.update_check_timer.timeout.connect(self.check_updates_automatically)
        self.update_start_timer = QTimer(self)
        self.update_start_timer.setSingleShot(True)
        self.update_start_timer.timeout.connect(self.check_updates_automatically)
        if ctx.update_checks_enabled:
            self.update_check_timer.start()
            self.update_start_timer.start(4000)

    def check_updates_automatically(self):
        if not self._closing and self.ctx.update_checks_enabled and not self.ctx.busy:
            self.ctx.updates.check(automatic=True)

    def refresh_update_notice(self):
        if self._closing:
            return
        release = self.ctx.updates.release
        self.update_notice.setVisible(release is not None)
        if release is not None:
            self.update_notice_text.setText(tr('Une mise à jour est disponible : PrépaPilot {version}.', version=release.version))

    def announce_update(self, release):
        if not self._closing:
            self.notify(tr('Une mise à jour est disponible : PrépaPilot {version}.', version=release.version))

    def open_update_settings(self):
        self.navigate('settings')
        QTimer.singleShot(0, self.scroll_to_updates)

    def scroll_to_updates(self):
        if not self._closing:
            self.wrappers['settings'].ensureWidgetVisible(self.pages['settings'].update_panel)

    def install_update(self, path):
        if self._closing or self.ctx.busy or not self.ctx.updates.installed:
            return
        controller = self.ctx.updates
        from .update_install import prepare_install
        try:
            request = prepare_install(path, controller.release.version,
                                      controller.cache_dir, controller.downloaded_sha256)
        except (OSError, ValueError, AttributeError):
            controller.invalidate_download()
            show_error(self, tr('L’installation n’a pas pu être préparée. Télécharge à nouveau la mise à jour.'))
            return
        if not confirm(self, tr('Installer PrépaPilot {version} ?', version=request.version),
                tr('La mise à jour est prête. Enregistre tes saisies avant de continuer. PrépaPilot va se fermer ; tes données enregistrées et ta séance de travail seront conservées.')):
            return
        # closeEvent checkpoints the focus session and may refuse to close on a
        # storage failure. Only a successful close may schedule the installer.
        if self.close():
            self.ctx.pending_installer = request
            QApplication.instance().quit()

    def jobs_updated(self, count):
        self.job_label.setText(tr("Traitement en cours…") if count else "")

    def request_language_refresh(self, *_):
        QTimer.singleShot(0, self.refresh_language)

    def refresh_language(self):
        if self._closing:
            return
        # Rebuilding every page can exceed the timer's interruption threshold on
        # a slow PC. Exclude that UI work and resume the same session afterwards.
        home = self.pages['home']
        session = home.focus_session
        home.timer.stop()
        resume = False
        try:
            if session.status == 'running':
                session.pause()
                resume = session.status == 'paused' and not session.state.get('interrupted')
            self._rebuild_language_window()
        finally:
            try:
                if resume and session.status == 'paused':
                    session.resume()
            finally:
                target = getattr(self, '_replacement', self)
                target.pages['home']._sync_focus()

    def _rebuild_language_window(self):
        drafts = {key: capture_inputs(page) for key, page in self.pages.items()}
        geometry = self.saveGeometry()
        current, full = self.current_key, self.isFullScreen()
        replacement = MainWindow(self.ctx, show_welcome=False)
        replacement.restoreGeometry(geometry)
        selected_note = self.pages['memory']._selected_key
        if selected_note is not None:
            memory = replacement.pages['memory']
            for index in range(memory.memory_list.count()):
                item = memory.memory_list.item(index)
                if item.data(Qt.UserRole) == selected_note:
                    memory.memory_list.setCurrentItem(item)
                    break
        for key, draft in drafts.items():
            restore_inputs(replacement.pages[key], draft)
        documents = replacement.pages['documents']
        documents._selected_id = self.pages['documents']._selected_id
        documents.refresh()
        selected_documents = set(self.pages['documents'].selected_document_ids())
        documents.documents.blockSignals(True)
        documents.documents.clearSelection()
        for index in range(documents.documents.count()):
            item = documents.documents.item(index)
            item.setSelected(item.data(Qt.UserRole) in selected_documents)
        documents.documents.blockSignals(False)
        documents._selection_changed(documents.documents.currentItem())
        progress = replacement.pages['progression']
        progress.anchor = self.pages['progression'].anchor
        progress.set_mode(self.pages['progression'].mode)
        replacement.pages['notes'].set_chart_mode(self.pages['notes'].chart.mode)
        replacement.pages['settings'].language.setCurrentIndex(
            replacement.pages['settings'].language.findData(self.ctx.language))
        replacement.navigate(current, animate=False)
        if full:
            replacement.showFullScreen()
        else:
            replacement.show()
        QApplication.instance()._prepapilot_window = replacement
        self._replacement = replacement
        self._language_rebuild = True
        self.close()
        self.deleteLater()

    def refresh_backup_reminder(self):
        settings = self.pages['settings']
        self.backup_reminder.setVisible(settings.google_connection.configured and settings.cloud_preferences.due())
        settings.refresh_cloud()

    def snooze_backup(self):
        try:
            self.pages['settings'].cloud_preferences.snooze()
        except OSError:
            self.notify(tr('Le rappel n’a pas pu être reporté. Vérifie l’espace disponible sur ce PC.'))
        self.refresh_backup_reminder()

    def open_cloud_backup(self):
        self.navigate('settings')
        self.pages['settings'].open_cloud()

    def settle_page_layouts(self, *_):
        # Apply fonts and wrapped-text sizes during actual UI updates, including
        # to unvisited pages. A later hover preview must only paint that state.
        domains = self.ctx.change_domains
        dependencies = {
            'home': {'profile', 'activities', 'timetable', 'subjects', 'grades', 'documents', 'year', 'progression'},
            'time': {'activities', 'timetable', 'subjects'},
            'progression': {'activities', 'timetable', 'subjects', 'year', 'progression', 'achievements'},
            'notes': {'grades', 'subjects', 'year'},
            'documents': {'documents', 'subjects'},
            'memory': {'memories'}, 'settings': {'profile'},
        }
        for key, page in self.pages.items():
            if domains is not None and not dependencies[key].intersection(domains):
                continue
            page.ensurePolished()
            for layout in reversed(page.findChildren(QLayout)):
                layout.activate()
            # Qt finalises hidden scroll-page geometry at its first render.
            # A one-pixel warm-up does that here, without allocating a page image
            # or waiting for an unrelated hover to change the layout.
            if not page.isVisible():
                page.grab(QRect(0, 0, 1, 1))
        QApplication.sendPostedEvents(None, QEvent.LayoutRequest)

    def navigate(self,key,animate=True):
        if key not in getattr(self,"pages",{}): return
        if hasattr(self,'navigation_preview'):
            self.navigation_preview.dismiss()
        previous=self.current_key
        if hasattr(self, 'navigation_preview'):
            self.navigation_preview.invalidate(previous)
        moving=animate and previous!=key and self.isVisible() and not self.ctx.db.get_setting("desktop_reduced_motion",False)
        # A second navigation starts from the panel currently on screen rather
        # than flashing the first destination's settled page into view.
        before = self.transition.capture(self.transition if self.transition.isVisible() else self.stack) if moving else None
        self.transition.finish()
        self.current_key=key
        self.stack.setCurrentWidget(self.wrappers[key])
        self.sync_focus_bar()
        for k,(btn,_) in self.nav.items():
            btn.setChecked(k==key)
        self.navigation_accent.select(key,animate=animate)
        self.nav[key][0].setFocus(Qt.OtherFocusReason)
        if moving:
            parent_layout = self.stack.parentWidget().layout()
            if parent_layout is not None:
                parent_layout.activate()
            self.stack.layout().activate()
            after=self.transition.capture(self.stack)
            keys=list(self.pages)
            direction=1 if keys.index(key)>keys.index(previous) else -1
            self.transition.configure(accent=page_palette(key,self.ctx.theme)['accent'])
            self.transition.start(before,after,QRect(self.stack.mapTo(self.central,QPoint()),self.stack.size()),direction)
            if self.toast.isVisible():
                self.toast.raise_()

    def motion_updated(self):
        closing_notice = self.toast_exit.state() == QAbstractAnimation.Running
        reduced=self.ctx.db.get_setting("desktop_reduced_motion",False)
        QApplication.instance().setProperty("reducedMotion",reduced)
        if reduced:
            self.transition.finish()
            self.toast_animation.stop()
            self.toast_exit.stop()
            self.toast_fade.setOpacity(1)
            if closing_notice:
                self.toast.hide()
            elif self.toast.isVisible():
                self.position_notice()

    def open_quick_actions(self):
        if self._closing:
            return
        if hasattr(self,'navigation_preview'):
            self.navigation_preview.dismiss()
        self.transition.finish()
        home=self.pages['home']
        focus_title={
            'running':tr('Mettre la séance en pause'),
            'paused':tr('Reprendre la séance'),
            'review':tr('Voir le bilan de la séance'),
        }.get(home.focus_session.status,tr('Démarrer une séance'))
        actions=[
            QuickAction('focus',focus_title,tr('Concentration · minuteur et objectif de travail'),'bolt',
                        tr('Séance, focus, concentration, minuteur, pomodoro')),
            QuickAction('add_activity',tr('Noter une activité'),tr('Journal · travail, sommeil, sport et détente'),'calendar',
                        tr('Activité, journal, travail, sport, sommeil')),
            QuickAction('add_grade',tr('Ajouter une note'),tr('Notes · évaluation, barème et coefficient'),'chart',
                        tr('Note, évaluation, résultat, moyenne')),
            QuickAction('add_document',tr('Ajouter un document'),tr('Bibliothèque · importer des fichiers'),'book',
                        tr('Document, fichier, importer, bibliothèque, cours')),
            QuickAction('add_memory',tr('Créer un repère'),tr('Mes repères · idées et objectifs personnels'),'memory',
                        tr('Repère, mémoire, idée, objectif')),
            QuickAction('search',tr('Rechercher dans mon espace'),tr('Documents, évaluations et repères · Ctrl+F'),'search'),
            QuickAction('help',tr('Aide et raccourcis'),tr('Guides pratiques et informations sur l’application · F1'),'help'),
        ]
        for key,(control,symbol) in self.nav.items():
            title=control.text() if key!='settings' else tr('Réglages')
            actions.append(QuickAction('page:'+key,title,tr('Ouvrir cet espace'),symbol))
        dialog=QuickActionsDialog(self.ctx,actions,self)
        if dialog.exec()==QDialog.Accepted:
            selected=dialog.selected_key
            if selected and selected.startswith('page:'):
                self.navigate(selected[5:])
            elif selected=='focus':
                self.navigate('home')
                home.toggle_focus()
            elif selected=='add_activity':
                home.add_activity()
            elif selected=='add_grade':
                self.navigate('notes')
                self.pages['notes'].add_note()
            elif selected=='add_document':
                home.add_document()
            elif selected=='add_memory':
                self.navigate('memory')
                self.pages['memory'].new_memory()
            elif selected=='search':
                self.open_global_search()
            elif selected=='help':
                self.open_help()
        dialog.deleteLater()

    def sync_focus_bar(self):
        if hasattr(self, 'focus_bar') and not self._closing:
            self.focus_bar.refresh(self.pages['home'].focus_session, visible=self.current_key != 'home')

    def return_to_focus(self):
        self.navigate('home')
        self.wrappers['home'].ensureWidgetVisible(self.pages['home'].focus_card, 0, 24)

    def open_help(self):
        if self._closing:
            return
        if hasattr(self,'navigation_preview'):
            self.navigation_preview.dismiss()
        self.transition.finish()
        dialog=HelpCenterDialog(self.ctx,self.navigate,self)
        dialog.exec()
        dialog.deleteLater()

    def open_global_search(self):
        if self._closing:
            return
        if hasattr(self,'navigation_preview'):
            self.navigation_preview.dismiss()
        self.transition.finish()
        dialog=GlobalSearchDialog(self.ctx,self)
        if dialog.exec()==QDialog.Accepted and dialog.selected_result:
            self.open_search_result(dialog.selected_result)
        dialog.deleteLater()

    def open_search_result(self, result):
        kind=result.get('kind')
        if kind=='document':
            page=self.pages['documents']
            if page._busy:
                self.notify(tr('Attends la fin de l’import avant d’ouvrir un autre document.'))
                return
            if not self.ctx.db.get_document(result.get('id')):
                self.notify(tr('Ce résultat n’est plus disponible. Relance la recherche.'))
                return
            controls=(page.search,page.subject_filter,page.kind_filter,page.folder_filter)
            blockers=[QSignalBlocker(control) for control in controls]
            page.search.clear()
            for control in controls[1:]:
                control.setCurrentIndex(0)
            del blockers
            page.documents.clearSelection()
            page._selected_id=result['id']
            page.refresh()
            self.navigate('documents')
            if page.documents.currentItem():
                page.documents.scrollToItem(page.documents.currentItem())
            self.wrappers['documents'].ensureWidgetVisible(page.documents,0,24)
        elif kind=='grade':
            grade=next((row for row in self.ctx.grades() if row['id']==result.get('id')),None)
            if grade is None:
                self.notify(tr('Ce résultat n’est plus disponible. Relance la recherche.'))
                return
            page=self.pages['notes']
            page.set_subject(grade['subject'])
            self.navigate('notes')
            for index in range(page.table.rowCount()):
                item=page.table.item(index,0)
                if item and item.data(Qt.UserRole)==grade['id']:
                    page.table.selectRow(index)
                    page.table.scrollToItem(item)
                    self.wrappers['notes'].ensureWidgetVisible(page.table,0,24)
                    break
        elif kind=='memory':
            page=self.pages['memory']
            key=result.get('key')
            if not self.ctx.db._rows('SELECT 1 FROM memories WHERE key=?',(key,)):
                self.notify(tr('Ce résultat n’est plus disponible. Relance la recherche.'))
                return
            from .memory import _display
            selected=page._selected_key
            saved=page._memories.get(selected)
            dirty=(page.value_input.toPlainText()!=_display(saved)) if selected is not None else bool(
                page.key_input.text().strip() or page.value_input.toPlainText().strip())
            if dirty and selected != key and not confirm(self,tr('Ouvrir un autre repère ?'),
                    tr('Ton repère contient des modifications non enregistrées. Continuer les abandonnera.')):
                return
            page.search.clear()
            page.refresh()
            self.navigate('memory')
            for index in range(page.memory_list.count()):
                item=page.memory_list.item(index)
                if item.data(Qt.UserRole)==key:
                    page.memory_list.setCurrentItem(item)
                    page.memory_list.scrollToItem(item)
                    self.wrappers['memory'].ensureWidgetVisible(page.value_input,0,24)
                    break

    def quick_add(self):
        if self.current_key=="notes":
            self.pages["notes"].add_note()
        elif self.current_key=="documents":
            self.pages["documents"].add_documents()
        elif self.current_key=="memory":
            self.pages["memory"].new_memory()
        else:
            self.navigate("time")
            self.pages["time"].add_activity()

    def data_replaced(self):
        self.transition.finish()
        self.pages["home"].reload_focus()
        self.sync_year_selector()
        self.motion_updated()

    def sync_year_selector(self):
        years=self.ctx.available_years
        with QSignalBlocker(self.year):
            if [self.year.itemData(index) for index in range(self.year.count())] != years:
                self.year.clear()
                for year in years:
                    self.year.addItem(f"{year}–{year+1}",year)
            self.year.setCurrentIndex(self.year.findData(self.ctx.year))
        self.add_year_button.setEnabled(years[-1] < MAX_SCHOOL_YEAR)
        next_year=years[-1]+1
        self.add_year_button.setToolTip(tr("Ajouter l’année {start}–{end}", start=next_year, end=next_year+1))

    def select_school_year(self, *_):
        year=self.year.currentData()
        if year is not None:
            self.ctx.set_year(year)

    def add_school_year(self):
        year=self.ctx.add_school_year()
        self.notify(tr("Année {start}–{end} ajoutée.", start=year, end=year+1))

    def show_saved_grade(self,dialog):
        self.navigate("notes")
        self.pages["notes"]._show_saved_note(dialog)

    def toggle_theme(self):
        self.ctx.set_theme("light" if self.ctx.theme=="dark" else "dark")

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.exit_fullscreen()
        else:
            self.enter_fullscreen()

    def enter_fullscreen(self):
        if self.isFullScreen() or self._closing:
            return
        self._windowed_geometry=self.normalGeometry() if self.isMaximized() else self.geometry()
        self.showFullScreen()
        self.sync_fullscreen_control()

    def exit_fullscreen(self):
        if not self.isFullScreen():
            return
        self.showNormal()
        if self._windowed_geometry is not None and self._windowed_geometry.isValid():
            self.setGeometry(self._windowed_geometry)
        self.sync_fullscreen_control()

    def convert_maximized(self):
        # The Windows maximize button should enter the same borderless mode as F11.
        if self.isMaximized() and not self.isFullScreen() and not self._closing:
            self.enter_fullscreen()

    def sync_fullscreen_control(self):
        if not hasattr(self,"fullscreen_button"):
            return
        full=self.isFullScreen()
        text=tr("Quitter le plein écran · F11 ou Échap") if full else tr("Plein écran · F11")
        self.fullscreen_button.setToolTip(text)
        self.fullscreen_button.setAccessibleName(text)
        self.fullscreen_button.setChecked(full)
        color=palette_for(self.ctx.theme)['muted']
        self.fullscreen_button.setIcon(icon("collapse" if full else "expand",color))
        if hasattr(self,"exit_fullscreen_shortcut"):
            self.exit_fullscreen_shortcut.setEnabled(full)

    def restore_window(self):
        if self.isFullScreen():
            self.showFullScreen()
        elif self.isMinimized():
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.WindowStateChange and hasattr(self,"maximize_timer"):
            if self.isMaximized() and not self.isFullScreen() and not self._closing:
                self.maximize_timer.start(0)
            else:
                self.maximize_timer.stop()
            self.sync_fullscreen_control()

    def theme_updated(self,theme):
        self.transition.finish()
        apply_theme(QApplication.instance(),theme)
        c=palette_for(theme)
        self.theme_button.setToolTip(tr("Passer au thème clair") if theme=="dark" else tr("Passer au thème sombre"))
        self.theme_button.setAccessibleName(self.theme_button.toolTip())
        self.theme_button.setIcon(icon("sun" if theme=="dark" else "moon",c['muted']))
        self.search_button.setIcon(icon('search',c['muted']))
        self.help_button.setIcon(icon('help',c['muted']))
        self.nav["settings"][0].setIcon(icon("settings",c['muted']))
        self.refresh_navigation_material(theme)
        self.mode_label.setStyleSheet(f"font-size:11px;color:{c['green']};")
        self.brand_icon.setPixmap(icon("pilot",c['text'],30).pixmap(QSize(30,30)))
        self.sync_fullscreen_control()
        self.toast.apply_theme(theme)
        self.settle_page_layouts()
        self.navigation_accent.sync()

    def refresh_navigation_material(self, theme):
        """Each selected page has its own tinted tab, with unchanged bounds."""
        neutral = palette_for(theme)

        def blend(base, accent, amount):
            left, right = QColor(base), QColor(accent)
            return QColor.fromRgbF(*(a + (b - a) * amount
                                    for a, b in zip(left.getRgbF()[:3], right.getRgbF()[:3]))).name()

        for key, (control, _) in self.nav.items():
            accent = page_palette(key, theme)['accent']
            control.setProperty('materialAccent', accent)
            top = blend(neutral['surface'], accent, .17 if theme == 'dark' else .12)
            bottom = blend(neutral['surface'], accent, .25 if theme == 'dark' else .21)
            hover = blend(neutral['surface'], accent, .13 if theme == 'dark' else .08)
            border = blend(neutral['border'], accent, .52)
            control.setStyleSheet(f"""
                QPushButton[role='nav']:checked {{
                    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {top},stop:1 {bottom});
                    border-color:{border}; color:{accent}; font-weight:600;
                }}
                QPushButton[role='nav']:hover {{ background:{hover}; color:{accent}; }}
                QPushButton[role='nav']:focus {{ border-color:{accent}; }}
            """)

    def notify(self,text,*,kind='info',title=None):
        if not str(text).strip():
            return
        self.toast_exit.stop()
        self.toast_fade.setOpacity(1)
        self.toast.setText(str(text),kind=kind,title=title)
        self.toast.setAccessibleName(str(text))
        width=min(620,self.central.width()-80)
        self.toast.fit_width(width,max_height=min(320,self.central.height()-100))
        end=self.notice_position()
        self.toast.raise_()
        self.toast.show()
        duration = notice_duration(text)
        self._notice_remaining_ms = duration
        self.toast.set_duration(duration)
        self.toast.restart()
        self.toast_animation.stop()
        if self.ctx.db.get_setting("desktop_reduced_motion",False): self.toast.move(end)
        else:
            self.toast_animation.setStartValue(end+QPoint(0,16))
            self.toast_animation.setEndValue(end)
            self.toast_animation.start()
        self.toast_timer.start(duration)
        if self._notice_hold_active:
            self.hold_notice(True)

    def hold_notice(self, held):
        """Keep a message available while the user reads, selects or copies it."""
        self._notice_hold_active = bool(held)
        if not self.toast.isVisible():
            self.toast_timer.stop()
            return
        if held:
            remaining = self.toast_timer.remainingTime()
            if remaining >= 0:
                self._notice_remaining_ms = max(1, remaining)
            elif self._notice_remaining_ms <= 0:
                self._notice_remaining_ms = 2000
            self.toast_timer.stop()
            self.toast_exit.stop()
            self.toast_fade.setOpacity(1)
            if self.toast.lifetime_animation.state() == QAbstractAnimation.Running:
                self.toast.lifetime_animation.pause()
        else:
            if self._notice_remaining_ms <= 0 or self.toast_exit.state() == QAbstractAnimation.Running:
                return
            self.toast_timer.start(max(1, self._notice_remaining_ms))
            if (self.toast.lifetime_animation.state() == QAbstractAnimation.Paused
                    and not QApplication.instance().property('reducedMotion')):
                self.toast.lifetime_animation.resume()

    def notice_position(self):
        return QPoint((self.central.width()-self.toast.width())//2,self.central.height()-self.toast.height()-28)

    def position_notice(self):
        self.toast.move(self.notice_position())

    def dismiss_notice(self):
        self._notice_remaining_ms = 0
        self.toast_timer.stop()
        self.toast_animation.stop()
        self.toast.stop_effects()
        if self.ctx.db.get_setting("desktop_reduced_motion",False):
            self.toast.hide()
        else:
            self.toast_exit.setStartValue(1.0)
            self.toast_exit.setEndValue(0.0)
            self.toast_exit.start()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'transition'):
            self.transition.finish()
        if hasattr(self,"toast") and self.toast.isVisible():
            self.toast_animation.stop()
            self.toast.fit_width(min(620,self.central.width()-80),
                                max_height=min(320,self.central.height()-100))
            self.position_notice()

    def closeEvent(self,event):
        if self.ctx.busy:
            self.notify(tr("Un fichier est en cours de traitement. Attends la fin du traitement avant de fermer."),kind='warning')
            event.ignore()
            return
        try:
            if not getattr(self, '_language_rebuild', False):
                self.pages['home'].shutdown_focus()
        except (ValueError, OSError, sqlite3.Error):
            self.notify(tr("La séance en cours n’a pas pu être sauvegardée. Vérifie le dossier de données, puis réessaie de fermer."),kind='error')
            event.ignore()
            return
        self.transition.shutdown()
        self.navigation_accent.shutdown()
        if hasattr(self,'navigation_preview'):
            self.navigation_preview.shutdown()
        self.pages['progression'].shutdown()
        # A closed window can remain alive until Qt processes deferred deletion.
        # No presentation callback should outlive the database connection.
        for timer in self.findChildren(QTimer):
            timer.stop()
        for animation in self.findChildren(QAbstractAnimation):
            animation.stop()
        if self.tray:self.tray.hide()
        self._closing=True
        event.accept()
