from .i18n import tr, qt_locale
from datetime import date, datetime, timedelta
import sqlite3
import math
from PySide6.QtCore import Qt, QTimer, QDate, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QDialog, QFrame, QSizePolicy, QLayout

from .widgets import Card, button, page_header, stat_card, clear_layout, empty_state, confirm, show_error
from .theme import palette_for
from .catalog import duration_text
from .notes import GradeDialog
from .study_profile import schedule_labels
from .page_chrome import AccentCard, AccentTitle, PageHero, accent_stat_card
from .focus_session import FocusSession
from .focus_dialogs import FocusSetupDialog, FocusReviewDialog
from .focus_visuals import FocusDial
from .getting_started import GettingStartedCard
from .engagement import MomentumCard


class DashboardPage(QWidget):
    focus_updated = Signal()

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(parent)
        self.ctx, self.navigate = ctx, navigate
        self.focus_session = getattr(ctx, '_live_focus_session', None) or FocusSession(ctx.db)
        ctx._live_focus_session = self.focus_session
        self._focus_metadata = None
        self.outer = QVBoxLayout(self)
        self.outer.setSizeConstraint(QLayout.SetMinimumSize)
        self.outer.setContentsMargins(0,0,0,0)
        self.outer.setSpacing(20)
        self.header = QWidget()
        self.header_layout = QVBoxLayout(self.header)
        self.header_layout.setContentsMargins(0,0,0,10)
        self.outer.addWidget(self.header)
        hero_row = QHBoxLayout()
        hero_row.setSpacing(18)
        hero_row.setAlignment(Qt.AlignTop)
        hero_left = QVBoxLayout()
        hero_left.setSpacing(18)
        self.next_step_button = button(tr('Commencer une séance  →'), self.open_next_step, primary=True)
        intro = self.hero = PageHero(ctx, 'home', tr('TON PROCHAIN PAS'),
            tr('Préparer une séance'),
            tr('Choisis la matière, la durée et ce que tu veux travailler.'),
            actions=[self.next_step_button])
        intro.title_label.setStyleSheet('font-size:27px;font-weight:600;letter-spacing:-.4px;')
        intro.figure.setFixedSize(144, 138)
        self.sculpture = intro.figure
        hero_left.addWidget(intro)
        focus = self.focus_card = AccentCard(ctx, 'memory')
        focus.setMinimumWidth(320)
        focus.setMinimumHeight(256)
        focus.body.addWidget(QLabel(tr('Minuteur de travail'), objectName="sectionTitle"))
        self.focus_caption = QLabel()
        self.focus_caption.setObjectName("muted")
        self.focus_caption.setTextFormat(Qt.PlainText)
        self.focus_caption.setWordWrap(True)
        focus.body.addWidget(self.focus_caption)
        horizontal = QHBoxLayout()
        self.dial = FocusDial(ctx)
        horizontal.addWidget(self.dial)
        focus_actions = QVBoxLayout()
        focus_actions.addStretch()
        self.focus_button = button(tr('Démarrer'), self.toggle_focus, primary=True)
        focus_actions.addWidget(self.focus_button)
        self.focus_finish_button = button(tr('Terminer'), self.finish_focus)
        focus_actions.addWidget(self.focus_finish_button)
        self.focus_reset_button = button(tr('Abandonner'), self.reset_focus)
        focus_actions.addWidget(self.focus_reset_button)
        focus_actions.addStretch()
        horizontal.addLayout(focus_actions)
        focus.body.addLayout(horizontal)
        self.focus_status = QLabel()
        self.focus_status.setObjectName("muted")
        self.focus_status.setWordWrap(True)
        focus.body.addWidget(self.focus_status)
        hero_left.addWidget(focus)
        hero_row.addLayout(hero_left,3)
        self.tomorrow_card = AccentCard(ctx, 'documents')
        self.tomorrow_card.setMinimumWidth(300)
        hero_row.addWidget(self.tomorrow_card,2)
        self.outer.addLayout(hero_row)
        self.momentum_card = MomentumCard(ctx, navigate, self.open_next_step)
        self.outer.addWidget(self.momentum_card)
        row = QHBoxLayout()
        row.setSpacing(18)
        self.work_stat = accent_stat_card(ctx, 'home', tr('Travail réalisé aujourd’hui'), "0 min", tr('Séances validées uniquement'))
        self.doc_stat = accent_stat_card(ctx, 'documents', tr('Documents'), "0", tr('Tes fichiers, classés par matière'))
        self.grade_stat = accent_stat_card(ctx, 'notes', tr('Notes enregistrées'), "0", tr('Cette année scolaire'))
        for card in (self.work_stat,self.doc_stat,self.grade_stat):
            row.addWidget(card)
        self.outer.addLayout(row)
        lower = QHBoxLayout()
        lower.setSpacing(18)
        self.day_card = AccentCard(ctx, 'home')
        lower.addWidget(self.day_card,3)
        self.getting_started = GettingStartedCard(ctx, navigate, self.add_document,
                                                self.add_grade, self.open_next_step)
        lower.addWidget(self.getting_started,2)
        self.outer.addLayout(lower)
        self.outer.addStretch()
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.day_timer = QTimer(self)
        self.day_timer.setInterval(60000)
        self.day_timer.timeout.connect(self.refresh_if_new_day)
        self.day_timer.start()
        ctx.watch_data(self.refresh, 'profile', 'activities', 'timetable', 'subjects', 'grades', 'documents', 'year', 'progression')
        ctx.theme_changed.connect(self.refresh)
        self.refresh()
        self._sync_focus()

    def _today(self):
        return date.today()

    @property
    def preview_revision(self):
        # The countdown and midnight rollover also change without a DB signal.
        return (self._displayed_day, self.dial.seconds, self.focus_button.text(), self.focus_status.text())

    def refresh_if_new_day(self):
        if self._today() != self._displayed_day:
            self.ctx.sync_school_years()
            self.refresh()

    def refresh(self, *_):
        self._focus_metadata = None
        self._sync_focus()
        name = (self.ctx.db.get_setting("desktop_name", "") or "").strip()
        today = self._today()
        self._displayed_day = today
        clear_layout(self.header_layout)
        self.header_layout.addWidget(QLabel(qt_locale().toString(QDate(today.year, today.month, today.day), "dddd d MMMM").upper(),objectName="eyebrow"))
        greeting = AccentTitle(self.ctx, 'home', tr('Bonjour {value0}.', value0=name) if name else tr('Tes études. Plus claires.'))
        greeting.setObjectName('heroTitle')
        greeting.setTextFormat(Qt.PlainText)
        greeting.setWordWrap(True)
        self.header_layout.addWidget(greeting)
        program = self.ctx.db.get_setting("desktop_program", "")
        subtitle = QLabel(program or tr('Un peu de recul. Une chose à la fois.'), objectName="pageSubtitle")
        subtitle.setTextFormat(Qt.PlainText)
        subtitle.setWordWrap(True)
        self.header_layout.addWidget(subtitle)
        self.ctx.db.ensure_day(today.isoformat())
        rows = self.ctx.db.list_time_entries(today.isoformat(), today.isoformat())
        self.momentum_card.refresh(today=today)
        minutes = next((day['work_minutes'] for day in self.momentum_card.summary['days']
                        if day['day'] == today), 0)
        self.work_stat.value.setText(duration_text(minutes))
        self.doc_stat.value.setText(str(self.ctx.db._rows('SELECT COUNT(*) AS total FROM documents')[0]['total']))
        year = self.ctx.year
        self.grade_stat.value.setText(str(self.ctx.db._rows(
            'SELECT COUNT(*) AS total FROM grades WHERE graded_on>=? AND graded_on<?',
            (f'{year}-08-01', f'{year+1}-08-01'))[0]['total']))
        self.getting_started.refresh(documents=int(self.doc_stat.value.text()),
                                     grades=bool(self.ctx.db._rows('SELECT 1 FROM grades LIMIT 1')))
        clear_layout(self.day_card.body)
        top = QHBoxLayout()
        top.addWidget(QLabel(tr('Le fil de ta journée'),objectName="sectionTitle"))
        top.addStretch()
        view = button(tr('Tout voir  →'),lambda:self.navigate("time"))
        view.setProperty("role","link")
        top.addWidget(view)
        self.day_card.body.addLayout(top)
        if not rows:
            self.day_card.body.addWidget(empty_state(tr('Une journée à écrire.'),tr('Ajoute une activité pour garder une trace de ton temps.')))
            self.day_card.body.addWidget(button(tr('Ajouter ma première activité  →'), self.add_activity))
        labels = self.ctx.db.category_labels(include_archived=True)
        for entry in rows[:4]:
            line = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color:{self.ctx.db.category_color(entry['category'])};font-size:14px;")
            line.addWidget(dot)
            stamp = entry['start_at'][11:16]
            title = QLabel(f"{stamp}   {entry['title'] or labels.get(entry['category'], entry['category'])}")
            title.setTextFormat(Qt.PlainText)
            title.setWordWrap(True)
            line.addWidget(title,1)
            state = QLabel(tr('Réalisé') if entry['status']=='completed' else tr('Prévu'),objectName="badge")
            line.addWidget(state)
            self.day_card.body.addLayout(line)
        self.day_card.body.addStretch()
        self.refresh_tomorrow(today + timedelta(days=1))

    def refresh_tomorrow(self, tomorrow):
        """Render the dated timetable, including absences and manual corrections."""
        day = tomorrow.isoformat()
        result = self.ctx.db.ensure_day(day)
        holiday = self.ctx.db.holiday_for_day(day)
        self.tomorrow_entries = [entry for entry in self.ctx.db.list_time_entries(day, day)
                                 if entry['source'] == 'timetable']
        clear_layout(self.tomorrow_card.body)
        self.tomorrow_card.body.addWidget(QLabel(tr('DEMAIN'), objectName="eyebrow"))
        locale = qt_locale()
        stamp = locale.toString(QDate(tomorrow.year, tomorrow.month, tomorrow.day), "dddd d MMMM")
        self.tomorrow_title = QLabel(stamp[0].upper() + stamp[1:], objectName="sectionTitle")
        self.tomorrow_title.setWordWrap(True)
        self.tomorrow_card.body.addWidget(self.tomorrow_title)
        self.holiday_status = QLabel(objectName="muted")
        self.holiday_status.setTextFormat(Qt.PlainText)
        self.holiday_status.setWordWrap(True)
        if holiday:
            end = date.fromisoformat(holiday['end'])
            end_label = locale.toString(QDate(end.year,end.month,end.day), "d MMMM yyyy")
            self.holiday_status.setText(tr('{value0} · jusqu’au {value1}\nLes cours habituels sont en pause.', value0=holiday['label'], value1=end_label))
        else:
            semester = schedule_labels(self.ctx.db)[self.ctx.db.semester_for_day(day)]
            week = self.ctx.db.week_for_day(day)
            self.holiday_status.setText(tr('{value0} · semaine {value1}', value0=semester, value1=week))
        self.tomorrow_card.body.addWidget(self.holiday_status)
        colors = palette_for(self.ctx.theme)
        for index, entry in enumerate(self.tomorrow_entries):
            item = QWidget()
            row = QHBoxLayout(item)
            row.setContentsMargins(0,8,0,8)
            row.setSpacing(12)
            times = QVBoxLayout()
            times.setSpacing(4)
            start = QLabel(entry['start_at'][11:16])
            start.setStyleSheet("font-weight:600;font-size:13px;")
            end = QLabel(entry['end_at'][11:16], objectName="muted")
            end.setStyleSheet("font-size:11px;")
            times.addWidget(start)
            times.addWidget(end)
            times.addStretch()
            row.addLayout(times)
            axis = QVBoxLayout()
            axis.setSpacing(4)
            dot = QFrame()
            dot.setFixedSize(8,8)
            dot.setStyleSheet(f"background:{self.ctx.db.category_color(entry['category'])};border-radius:4px;")
            axis.addWidget(dot,0,Qt.AlignHCenter)
            if index < len(self.tomorrow_entries)-1:
                line = QFrame()
                line.setFixedWidth(2)
                line.setMinimumHeight(28)
                line.setStyleSheet(f"background:{colors['border']};")
                axis.addWidget(line,1,Qt.AlignHCenter)
            else:
                axis.addStretch()
            row.addLayout(axis)
            details = QVBoxLayout()
            details.setSpacing(5)
            subject_name = self.ctx.db.category_labels(include_archived=True).get(entry['category'], entry['category'])
            title = QLabel(entry['title'] or subject_name)
            title.setTextFormat(Qt.PlainText)
            title.setWordWrap(True)
            title.setStyleSheet("font-weight:500;")
            details.addWidget(title)
            caption = duration_text(entry['minutes'])
            if entry['title'] and entry['title'] != subject_name:
                caption = subject_name + " · " + caption
            if entry['manual_override']:
                caption += tr(' · horaire personnalisé')
            duration = QLabel(caption, objectName="muted")
            duration.setWordWrap(True)
            details.addWidget(duration)
            details.addStretch()
            row.addLayout(details,1)
            self.tomorrow_card.body.addWidget(item)
        if not self.tomorrow_entries:
            self.tomorrow_card.body.addWidget(empty_state(
                tr('Une journée pour toi.') if holiday else tr('Aucun cours prévu.'),
                tr('Tu peux noter tes révisions, tes loisirs et tes moments de repos.') if holiday else
                tr('Retrouve tes activités personnelles dans le journal de cette journée.')))
        if result['conflicts']:
            skipped = QLabel(tr('Certains créneaux ont été remplacés par tes activités. Consulte le journal pour le détail.'), objectName="muted")
            skipped.setWordWrap(True)
            self.tomorrow_card.body.addWidget(skipped)
        self.tomorrow_card.body.addStretch()
        view = button(tr('Voir la journée  →'),lambda:self.open_day(tomorrow))
        view.setProperty("role","link")
        self.tomorrow_card.body.addWidget(view,0,Qt.AlignLeft)
        holidays = button(tr('Vacances et pauses'),self.open_holidays)
        self.tomorrow_card.body.addWidget(holidays,0,Qt.AlignLeft)

    def open_day(self, chosen):
        self.navigate("time")
        page = self.window().pages["time"]
        page.day.setDate(QDate(chosen.year,chosen.month,chosen.day))

    def open_holidays(self):
        self.navigate("time")
        self.window().pages["time"].edit_holidays()

    def add_activity(self):
        self.navigate("time")
        self.window().pages["time"].add_activity()

    def add_document(self):
        self.navigate("documents")
        self.window().pages["documents"].add_documents()

    def add_grade(self):
        dialog = GradeDialog(self.ctx,parent=self)
        if dialog.exec() == QDialog.Accepted and hasattr(self.window(), "show_saved_grade"):
            self.window().show_saved_grade(dialog)

    def toggle_focus(self):
        try:
            status = self.focus_session.status
            if status == 'running':
                self.focus_session.pause()
            elif status == 'paused':
                self.focus_session.resume()
            elif status == 'review':
                self.review_focus()
            else:
                dialog = FocusSetupDialog(self.ctx, parent=self)
                if dialog.exec() == QDialog.Accepted:
                    self.focus_session.start(**dialog.values)
            self._sync_focus()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._sync_focus()
            show_error(self, str(exc))

    def open_next_step(self):
        """A running session stays running when reached from a home shortcut."""
        if self.focus_session.status == 'running':
            self.navigate('home')
            window = self.window()
            if hasattr(window, 'wrappers'):
                window.wrappers['home'].ensureWidgetVisible(self.focus_card, 0, 24)
        else:
            self.toggle_focus()

    def _sync_next_step(self, status):
        content = {
            'running': ('TA SÉANCE EN COURS', 'Séance en cours',
                        'Ton minuteur est en route. Retrouve ta séance juste en dessous.', 'Retrouver ma séance  →'),
            'paused': ('TON PROCHAIN PAS', 'Séance en pause',
                       'Ton temps de travail est conservé. Reprends ta séance à ton rythme.', 'Reprendre ma séance  →'),
            'review': ('TON PROCHAIN PAS', 'Vérifier le bilan',
                       'Ta séance est terminée. Vérifie son bilan pour retrouver ton travail dans ta progression.', 'Voir mon bilan  →'),
            'saved': ('TON PROCHAIN PAS', 'Séance enregistrée',
                      'Ton travail est enregistré. Tu peux faire une pause ou choisir ton prochain objectif.', 'Commencer une séance  →'),
        }.get(status, ('TON PROCHAIN PAS', 'Préparer une séance',
                      'Choisis la matière, la durée et ce que tu veux travailler.', 'Commencer une séance  →'))
        for control, text in zip((self.hero.eyebrow_label, self.hero.title_label,
                                  self.hero.subtitle_label, self.next_step_button), content):
            translated = tr(text)
            if control.text() != translated:
                control.setText(translated)

    def finish_focus(self):
        try:
            self.focus_session.finish()
            self._sync_focus()
            self.review_focus()
        except (ValueError, OSError, sqlite3.Error) as exc:
            self._sync_focus()
            show_error(self, str(exc))

    def review_focus(self):
        dialog = FocusReviewDialog(self.ctx, self.focus_session, parent=self)
        dialog.exec()
        self._sync_focus()

    def reset_focus(self):
        if self.focus_session.active and not confirm(
                self, tr('Ignorer cette séance ?'),
                tr('Le temps de cette séance ne sera pas ajouté au journal. Les activités déjà enregistrées sont conservées.')):
            return
        try:
            self.focus_session.discard()
            self._sync_focus()
        except (ValueError, OSError, sqlite3.Error) as exc:
            show_error(self, str(exc))

    def reload_focus(self):
        # A restored database replaces the draft too. Never checkpoint the old
        # in-memory session into the new database.
        self.timer.stop()
        self.focus_session = FocusSession(self.ctx.db)
        self.ctx._live_focus_session = self.focus_session
        self._focus_metadata = None
        self._sync_focus()

    def shutdown_focus(self):
        self.timer.stop()
        try:
            self.focus_session.shutdown()
        finally:
            self._sync_focus()

    def _sync_focus(self):
        session = self.focus_session
        state, status = session.state, session.status
        self._sync_next_step(status)
        if hasattr(self, 'momentum_card'):
            self.momentum_card.sync_focus_state()
        active = session.active
        minutes = state.get('target_minutes', 25)
        self.dial.total_seconds = minutes * 60
        seconds = int(math.ceil(session.remaining_seconds)) if active else minutes * 60
        if self.dial.seconds != seconds:
            self.dial.set_seconds(seconds)
        self.focus_button.setText({'running': tr('Pause'), 'paused': tr('Reprendre'), 'review': tr('Voir le bilan')}.get(status, tr('Démarrer')))
        self.focus_finish_button.setVisible(status in ('running', 'paused'))
        self.focus_reset_button.setVisible(active)
        self.focus_reset_button.setText(tr('Ignorer') if status == 'review' else tr('Abandonner'))
        metadata = (status, state.get('category'), state.get('title'), minutes)
        if metadata != self._focus_metadata:
            self._focus_metadata = metadata
            labels = self.ctx.db.category_labels(include_archived=True)
            caption = labels.get(state.get('category'), tr('Minuteur libre'))
            if active:
                caption += tr(' · {value0} min prévues', value0=minutes)
                if state.get('title'):
                    caption += '\n' + state['title']
            else:
                caption = tr('Une matière, un objectif, une durée. À toi de choisir.')
            self.focus_caption.setText(caption)
        elapsed = int(session.elapsed_seconds)
        duration = f"{elapsed // 60} min {elapsed % 60:02} s"
        if status == 'running':
            text = tr('{value0} de travail · les pauses ne comptent pas.', value0=duration)
        elif status == 'paused':
            text = (tr('Séance interrompue : le temps d’absence n’a pas été compté. ')
                    if state.get('interrupted') else tr('En pause. ')) + tr('{value0} conservées.', value0=duration)
        elif status == 'review':
            text = tr('{value0} réalisées. Vérifie le bilan avant de l’ajouter au journal.', value0=duration)
        elif status == 'saved':
            text = tr('Séance enregistrée. Retrouve-la dans Gestion du temps et Progression.')
        else:
            text = tr('En fin de séance, tu choisis de conserver ou non ton temps de travail.')
        self.focus_status.setText(text)
        if status == 'running':
            if not self.timer.isActive():
                self.timer.start()
        else:
            self.timer.stop()
        self.focus_updated.emit()

    def tick(self):
        previous = self.focus_session.status
        try:
            self.focus_session.tick()
        except (ValueError, OSError, sqlite3.Error):
            self._sync_focus()
            self.timer.stop()
            # Avoid repeated dialogs from a timer. Keep the draft accessible.
            self.ctx.notice.emit(tr('La séance n’a pas pu être sauvegardée. Vérifie le dossier de données avant de reprendre.'))
            return
        self._sync_focus()
        if previous == 'running' and self.focus_session.status == 'review':
            self.ctx.notice.emit(tr('Séance terminée. Le bilan t’attend sur l’accueil avant l’enregistrement dans le journal.'))
        elif previous == 'running' and self.focus_session.status == 'paused':
            self.ctx.notice.emit(tr('Séance mise en pause après une interruption. Reprends-la depuis l’accueil.'))
