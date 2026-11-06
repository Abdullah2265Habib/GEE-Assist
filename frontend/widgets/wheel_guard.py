"""Stop the mouse wheel from changing fields the user has not selected.

By default Qt lets the wheel change any combo box, spin box or date edit the
mouse happens to pass over while scrolling the page, which silently edits
the form. With the guard installed:

* a value field only reacts to the wheel once it has keyboard focus
  (the user clicked or tabbed into it);
* otherwise the wheel event goes to the parent, so the page scrolls instead;
* the wheel no longer gives focus to a field by itself.
"""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtWidgets import QAbstractSpinBox, QApplication, QComboBox, QWidget

GUARDED_TYPES = (QAbstractSpinBox, QComboBox)  # QDateEdit is a QAbstractSpinBox


class WheelGuard(QObject):
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        if not isinstance(obj, GUARDED_TYPES):
            return False

        if event.type() == QEvent.Type.Polish:
            # Qt gives focus on wheel *before* filters run, so drop wheel focus up front.
            if obj.focusPolicy() == Qt.FocusPolicy.WheelFocus:
                obj.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            return False

        if event.type() == QEvent.Type.Wheel and not obj.hasFocus():
            # Ignored + filtered: Qt keeps propagating it to the parent (the scroll area).
            event.ignore()
            return True
        return False


def guard_widget(widget: QWidget) -> None:
    """Apply the focus policy immediately (for widgets that are already polished)."""
    if isinstance(widget, GUARDED_TYPES) and widget.focusPolicy() == Qt.FocusPolicy.WheelFocus:
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def install_wheel_guard(app: QApplication) -> WheelGuard:
    guard = WheelGuard(app)
    app.installEventFilter(guard)
    for widget in app.allWidgets():
        guard_widget(widget)
    return guard
