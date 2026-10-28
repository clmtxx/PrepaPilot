from PySide6.QtGui import QColor, QPalette
from pathlib import Path
import sys

PALETTES = {
    "dark": dict(bg="#12191F", surface="#1C252C", surface2="#26323B", border="#3C4B53", text="#EDF1F0", muted="#AEBBBE", accent="#90BCE7", accent_soft="#294359", blue="#92C0E4", orange="#DDA66C", green="#85C4A6", danger="#F09687"),
    "light": dict(bg="#F3F0E9", surface="#FFFDFA", surface2="#EAE6DD", border="#D4CEC2", text="#26323A", muted="#626B6D", accent="#315F98", accent_soft="#E3EDF9", blue="#3474AD", orange="#A56A34", green="#2C7A5A", danger="#B34239"),
}


def palette_for(theme):
    return PALETTES.get(theme, PALETTES["light"])


def apply_theme(app, theme):
    c = palette_for(theme)
    dark = theme == 'dark'
    primary_start, primary_end = '#326EA5', '#2A5C8D'
    primary_hover_start, primary_hover_end = '#3A7BB5', '#326A9E'
    nav_start, nav_end = ('#304653', '#263B48') if dark else ('#E6EAE8', '#DDE5E7')
    focus_color = QColor(c['surface'])
    pigment = QColor(c['accent'])
    amount = .09 if dark else .045
    focus_color = QColor.fromRgbF(*(a + (b - a) * amount
                                   for a, b in zip(focus_color.getRgbF()[:3], pigment.getRgbF()[:3]))).name()
    app.setProperty('visualTheme', theme)
    assets = (Path(getattr(sys,"_MEIPASS",Path(__file__).resolve().parent.parent))/"assets").as_posix()
    pal = QPalette()
    for role, color in [(QPalette.Window,c['bg']), (QPalette.WindowText,c['text']),
                         (QPalette.Base,c['surface']), (QPalette.AlternateBase,c['surface2']),
                         (QPalette.Text,c['text']), (QPalette.Button,c['surface2']),
                         (QPalette.ButtonText,c['text']), (QPalette.Highlight,c['accent_soft']),
                         (QPalette.HighlightedText,c['text']), (QPalette.ToolTipBase,c['surface']),
                         (QPalette.ToolTipText,c['text']), (QPalette.PlaceholderText,c['muted'])]:
        pal.setColor(role, QColor(color))
    app.setPalette(pal)
    app.setStyleSheet(f"""
        QWidget {{ color: {c['text']}; font-family: 'Segoe UI'; font-size: 13px; }}
        QMainWindow, QDialog {{ background: {c['bg']}; }}
        QLabel {{ background: transparent; }}
        QLabel#pageTitle {{ font-size: 32px; font-weight: 600; letter-spacing: -0.6px; }}
        QLabel#heroTitle {{ font-size: 38px; font-weight: 600; letter-spacing: -0.8px; }}
        QLabel#pageSubtitle {{ color: {c['muted']}; font-size: 15px; }}
        QLabel#sectionTitle, QLabel#cardTitle {{ font-size: 19px; font-weight: 600; letter-spacing: -0.2px; }}
        QLabel#muted, QLabel[muted='true'] {{ color: {c['muted']}; }}
        QLabel#eyebrow {{ color: {c['muted']}; font-size: 11px; font-weight: 600; letter-spacing: 1.2px; }}
        QLabel#dialogTitle {{ font-size: 26px; font-weight: 600; letter-spacing: -0.4px; }}
        QLabel#timeBlock {{ font-size: 18px; color: {c["accent"]}; font-weight: 600; }}
        QLabel#warning {{ color: {c["orange"]}; }}
        QLabel#statValue {{ font-size: 32px; font-weight: 600; letter-spacing: -0.8px; }}
        QLabel#badge {{ background: {c['accent_soft']}; color: {c['accent']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 600; }}
        QLabel#error {{ color: {c['danger']}; }}
        QFrame#Card {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 16px; }}
        QFrame#HeroCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 18px; }}
        QFrame#Navigation {{ background: {c['surface']}; border: none; border-bottom: 1px solid {c['border']}; }}
        QFrame#UtilityBar {{ background: {c['bg']}; border: none; }}
        QFrame#Sidebar {{ background: {c['surface']}; border: none; border-right: 1px solid {c['border']}; }}
        QFrame#Topbar {{ background: {c['bg']}; border: none; }}
        QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {c['surface']},stop:1 {c['surface2']}); border: 1px solid {c['border']}; border-radius: 10px; padding: 8px 18px; min-height: 22px; font-weight: 600; }}
        QPushButton:hover {{ background: {c['accent_soft']}; color: {c['accent']}; border-color: {c['accent']}; }}
        QPushButton:focus {{ border-color: {c['accent']}; }}
        QPushButton:pressed {{ background: {c['accent_soft']}; }}
        QPushButton:disabled {{ color: {c['muted']}; border-color: {c['border']}; }}
        QPushButton[role='primary'] {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {primary_start},stop:1 {primary_end}); border: 1px solid {'#67889C' if dark else '#244A66'}; color: #FFFFFF; font-weight: 600; }}
        QPushButton[role='primary']:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {primary_hover_start},stop:1 {primary_hover_end}); color: #FFFFFF; border-color: #7BA3BB; }}
        QPushButton[role='primary']:pressed {{ background: #214561; color: #FFFFFF; }}
        QPushButton[role='primary']:focus {{ border-color: #C79560; }}
        QPushButton[role='primary']:disabled {{ background: {c['surface2']}; color: {c['muted']}; border-color: transparent; }}
        QPushButton[role='link'] {{ background: transparent; color: {c['accent']}; padding-left: 0; padding-right: 0; border: 1px solid transparent; border-radius: 6px; }}
        QPushButton[role='danger'] {{ color: {c['danger']}; background: transparent; border: 1px solid transparent; }}
        QPushButton[role='danger']:disabled {{ color: {c['muted']}; border-color: transparent; }}
        QPushButton[role='nav'] {{ background: transparent; border: 1px solid transparent; padding: 8px 12px; border-radius: 8px; font-size: 13px; font-weight: 500; color: {c['muted']}; }}
        QPushButton[role='nav']:checked {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {nav_start},stop:1 {nav_end}); color: {c['text'] if dark else c['accent']}; border-color: {c['border']}; font-weight: 600; }}
        QPushButton[role='nav']:hover {{ background: {c['surface2']}; }}
        QPushButton[role='nav']:focus {{ border-color: {c['accent']}; }}
        QPushButton[role='tab']:checked {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {primary_start},stop:1 {primary_end}); color: #FFFFFF; border-color: {c['accent']}; font-weight: 700; }}
        QLineEdit, QTextEdit, QPlainTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 8px; padding: 10px 12px; selection-background-color: {c['accent_soft']}; selection-color: {c['text']}; }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {{
            border: 2px solid {c['accent']}; background:{focus_color}; padding:9px 11px;
        }}
        QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; selection-background-color: {c['accent_soft']}; color: {c['text']}; padding: 6px; }}
        QComboBox::drop-down, QDateEdit::drop-down {{ width: 25px; border: none; }}
        QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url("{assets}/down.svg"); width: 14px; height: 14px; }}
        QSpinBox::up-button, QDoubleSpinBox::up-button, QTimeEdit::up-button, QDateEdit::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 22px; height: 18px; background: {c['surface2']}; border: none; border-top-right-radius: 7px; }}
        QSpinBox::down-button, QDoubleSpinBox::down-button, QTimeEdit::down-button, QDateEdit::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; height: 18px; background: {c['surface2']}; border: none; border-bottom-right-radius: 7px; }}
        QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QTimeEdit::up-arrow, QDateEdit::up-arrow {{ image: url("{assets}/up.svg"); width: 11px; height: 11px; }}
        QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QTimeEdit::down-arrow, QDateEdit::down-arrow {{ image: url("{assets}/down.svg"); width: 11px; height: 11px; }}
        QTableWidget, QTableView, QListWidget {{ background: {c['surface']}; border: none; border-radius: 10px; gridline-color: {c['border']}; alternate-background-color: {c['surface2']}; outline: none; }}
        QTableWidget::item, QListWidget::item {{ padding: 9px; border: none; }}
        QListWidget::item {{ border-radius: 8px; margin: 2px 0; }}
        QTableWidget::item:selected, QListWidget::item:selected {{ background: {c['accent_soft']}; color: {c['text']}; }}
        QHeaderView::section {{ background: {c['surface2']}; color: {c['text']}; border: none; border-bottom: 2px solid {c['border']}; padding: 13px 9px; font-weight: 600; font-size: 11px; }}
        QTableCornerButton::section {{ background: {c['surface2']}; border: none; }}
        QScrollArea {{ background: transparent; border: none; }}
        QScrollArea > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:vertical {{ width: 9px; background: transparent; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 28px; border-radius: 4px; }}
        QScrollBar:horizontal {{ height: 9px; background: transparent; }}
        QScrollBar::handle:horizontal {{ background: {c['border']}; min-width: 28px; border-radius: 4px; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
        QTabWidget::pane {{ border: none; }}
        QTabBar::tab {{ padding: 11px 20px; color: {c['muted']}; background: {c['surface2']}; border-radius: 8px; margin-right: 6px; }}
        QTabBar::tab:selected {{ color: #FFFFFF; background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {primary_start},stop:1 {primary_end}); }}
        QCheckBox {{ spacing: 9px; }}
        QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {c['border']}; border-radius: 4px; background: {c['surface']}; }}
        QCheckBox::indicator:checked {{ background: {primary_start}; border-color: {primary_start}; image: url("{assets}/check.svg"); }}
        QProgressBar {{ background: {c['surface2']}; border: none; border-radius: 5px; height: 8px; text-align: center; }}
        QProgressBar::chunk {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {c['accent']},stop:1 {c['blue']}); border-radius: 5px; }}
        QToolTip {{ border: 1px solid {c['border']}; padding: 8px; border-radius: 5px; background: {c['surface']}; color: {c['text']}; }}
        QSplitter::handle {{ background: transparent; width: 12px; height: 12px; }}
        QGroupBox {{ border: 1px solid {c['border']}; border-radius: 12px; margin-top: 18px; padding: 18px; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}
        QCalendarWidget QAbstractItemView {{ background: {c['surface']}; selection-background-color: {c['accent_soft']}; }}
    """)
