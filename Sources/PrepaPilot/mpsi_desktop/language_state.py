"""Preserve editable page drafts while rebuilding translated UI widgets."""
from PySide6.QtWidgets import (QAbstractSpinBox, QComboBox, QLineEdit, QPlainTextEdit,
                              QTextEdit, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QCheckBox)


def _inputs(page):
    for kind in (QComboBox, QDateTimeEdit, QSpinBox, QDoubleSpinBox, QCheckBox,
                 QLineEdit, QPlainTextEdit, QTextEdit):
        for control in page.findChildren(kind):
            if kind is QLineEdit and isinstance(control.parent(), (QAbstractSpinBox, QComboBox)):
                continue
            if kind in (QPlainTextEdit, QTextEdit) and control.isReadOnly():
                continue
            yield kind.__name__, control


def capture_inputs(page):
    result = []
    for kind, control in _inputs(page):
        if isinstance(control, QComboBox):
            value = (control.currentData(), control.currentText() if control.isEditable() else None)
        elif isinstance(control, QDateTimeEdit):
            value = control.dateTime()
        elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
            value = control.value()
        elif isinstance(control, QCheckBox):
            value = control.isChecked()
        elif isinstance(control, QLineEdit):
            value = (control.text(), control.isModified(), control.cursorPosition(), control.isReadOnly())
        else:
            value = control.toPlainText()
        result.append((kind, value))
    return result


def restore_inputs(page, values):
    for (kind, control), (previous_kind, value) in zip(_inputs(page), values):
        if kind != previous_kind:
            continue
        if isinstance(control, QComboBox):
            data, text = value
            index = control.findData(data)
            if index >= 0:
                control.setCurrentIndex(index)
            if text is not None:
                control.setEditText(text)
        elif isinstance(control, QDateTimeEdit):
            control.setDateTime(value)
        elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
            control.setValue(value)
        elif isinstance(control, QCheckBox):
            control.setChecked(value)
        elif isinstance(control, QLineEdit):
            text, modified, position, read_only = value
            control.setText(text)
            control.setModified(modified)
            control.setCursorPosition(position)
            control.setReadOnly(read_only)
        else:
            control.setPlainText(value)
