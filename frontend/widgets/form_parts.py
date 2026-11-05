"""Building blocks for the parameter form, styled like the sign-in pages:
white cards with serif headings, labels above fields, errors underneath."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLayout,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionComboBox,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)


def section_card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    """White card with a serif title (and muted subtitle). Returns (card, body layout)."""
    card = QFrame()
    card.setObjectName("SectionCard")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 16, 22, 20)
    layout.setSpacing(12)

    heading = QVBoxLayout()
    heading.setSpacing(2)
    title_label = QLabel(title)
    title_label.setObjectName("SectionTitle")
    heading.addWidget(title_label)
    if subtitle:
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("SectionSubtitle")
        subtitle_label.setWordWrap(True)
        heading.addWidget(subtitle_label)
    layout.addLayout(heading)
    layout.addWidget(divider())

    body = QVBoxLayout()
    body.setSpacing(12)
    layout.addLayout(body)
    return card, body


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def field_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    return label


def hint_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("FieldHint")
    label.setWordWrap(True)
    return label


def labelled(label: str, content: QWidget | QLayout, *extra: QWidget) -> QWidget:
    """Label above ``content``, followed by optional hint / error labels."""
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    layout.addWidget(field_label(label))
    if isinstance(content, QLayout):
        layout.addLayout(content)
    else:
        layout.addWidget(content)
    for widget in extra:
        layout.addWidget(widget)
    layout.addStretch(1)
    return box


def field_row(*fields: QWidget, stretches: tuple[int, ...] | None = None) -> QGridLayout:
    """Several labelled fields side by side, sharing the row's width."""
    grid = QGridLayout()
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(0)
    for column, widget in enumerate(fields):
        grid.addWidget(widget, 0, column, Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(column, stretches[column] if stretches else 1)
    return grid


class CheckGrid(QWidget):
    """Checkboxes laid out in columns. Replaces a scrolling check list, so
    the mouse wheel never changes what is shown."""

    def __init__(self, columns: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("CheckGrid")
        self._columns = columns
        self._boxes: list[QCheckBox] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(12, 10, 12, 10)
        self._grid.setHorizontalSpacing(18)
        self._grid.setVerticalSpacing(8)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def set_items(self, items: list[tuple[str, bool, bool, str]]) -> None:
        """``items``: (text, checked, enabled, tooltip). Disabled items are shown greyed out."""
        for box in self._boxes:
            self._grid.removeWidget(box)
            box.deleteLater()
        self._boxes = []

        for index, (text, checked, enabled, tooltip) in enumerate(items):
            box = QCheckBox(text)
            box.setCursor(Qt.CursorShape.PointingHandCursor if enabled else Qt.CursorShape.ForbiddenCursor)
            box.setChecked(checked and enabled)
            box.setEnabled(enabled)
            box.setToolTip(tooltip)
            self._grid.addWidget(box, index // self._columns, index % self._columns)
            self._boxes.append(box)
        for column in range(self._columns):
            self._grid.setColumnStretch(column, 1)

    def checked(self) -> list[str]:
        return [box.text() for box in self._boxes if box.isEnabled() and box.isChecked()]

    def boxes(self) -> list[QCheckBox]:
        return list(self._boxes)


class CheckComboBox(QComboBox):
    """Drop-down with a checkbox per item, for picking several values compactly.

    * clicking an item (or pressing Space / Enter on it) toggles it and keeps the popup open;
    * the closed box shows the checked items, e.g. "B2, B3, B4, B8, B11";
    * the mouse wheel never changes the selection (it scrolls the page instead).
    """

    selection_changed = pyqtSignal(list)  # checked item texts

    def __init__(self, placeholder: str = "Nothing selected", parent: QWidget | None = None):
        super().__init__(parent)
        self._placeholder = placeholder
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        # The default combo delegate does not draw item checkboxes.
        self.setItemDelegate(QStyledItemDelegate(self))
        self.view().viewport().installEventFilter(self)
        self.view().installEventFilter(self)
        self._model.itemChanged.connect(self._on_item_changed)

    # ------------------------------------------------------------------ API
    def set_items(self, items: list[tuple[str, bool]]) -> None:
        """``items``: (text, checked)."""
        self._model.blockSignals(True)
        self._model.clear()
        for text, checked in items:
            item = QStandardItem(text)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self._model.appendRow(item)
        self._model.blockSignals(False)
        self._on_item_changed()

    def checked(self) -> list[str]:
        return [
            self._model.item(row).text()
            for row in range(self._model.rowCount())
            if self._model.item(row).checkState() == Qt.CheckState.Checked
        ]

    def set_checked(self, texts) -> None:
        wanted = set(texts)
        self._model.blockSignals(True)
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            item.setCheckState(Qt.CheckState.Checked if item.text() in wanted else Qt.CheckState.Unchecked)
        self._model.blockSignals(False)
        self._on_item_changed()

    def summary(self) -> str:
        checked = self.checked()
        return ", ".join(checked) if checked else self._placeholder

    # ------------------------------------------------------------- behaviour
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        view = self.view()
        if obj is view.viewport() and event.type() == QEvent.Type.MouseButtonRelease:
            self._toggle(view.indexAt(event.position().toPoint()).row())
            return True  # keep the popup open
        if obj is view and event.type() == QEvent.Type.KeyPress and event.key() in (
            Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter,
        ):
            self._toggle(view.currentIndex().row())
            return True
        return super().eventFilter(obj, event)

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        event.ignore()  # stepping through items makes no sense for a multi-select

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QStylePainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        text_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option, QStyle.SubControl.SC_ComboBoxEditField, self
        )
        option.currentText = self.fontMetrics().elidedText(
            self.summary(), Qt.TextElideMode.ElideRight, max(text_rect.width() - 4, 20)
        )
        option.currentIcon = QIcon()
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)

    def _toggle(self, row: int) -> None:
        item = self._model.item(row) if row >= 0 else None
        if item is None or not item.isEnabled():
            return
        item.setCheckState(
            Qt.CheckState.Unchecked if item.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        )

    def _on_item_changed(self, *_args) -> None:
        checked = self.checked()
        self.setToolTip(", ".join(checked) if checked else self._placeholder)
        self.update()
        self.selection_changed.emit(checked)


class StatusBanner(QLabel):
    """Coloured message (success / error / info) in the action bar; hidden when empty."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setContentsMargins(10, 0, 10, 0)  # stylesheet padding is not applied to wrapped labels
        self.hide()

    def show_success(self, text: str) -> None:
        self._show("SuccessBanner", text)

    def show_error(self, text: str) -> None:
        self._show("ErrorBanner", text)

    def show_info(self, text: str) -> None:
        self._show("InfoBanner", text)

    def clear(self) -> None:  # noqa: D401 - QLabel API
        super().clear()
        self.hide()

    def _show(self, kind: str, text: str) -> None:
        if not text:
            self.clear()
            return
        self.setObjectName(kind)
        self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)
        self.show()


def pad_spin_text(*spins: QAbstractSpinBox) -> None:
    """Fusion ignores the stylesheet's left padding for spin boxes' inner text."""
    for spin in spins:
        spin.lineEdit().setTextMargins(6, 0, 0, 0)


def set_invalid(widget: QWidget, invalid: bool) -> None:
    """Toggle the red ``[invalid="true"]`` border from the stylesheet."""
    if bool(widget.property("invalid")) == invalid:
        return
    widget.setProperty("invalid", invalid)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
