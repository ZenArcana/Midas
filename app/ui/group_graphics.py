from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsObject


@dataclass
class GroupGeometry:
    width: float
    height: float


class GroupGraphicsItem(QGraphicsObject):
    """
    Visual container representing a group of nodes.
    """

    HEADER_HEIGHT = 28.0
    MIN_WIDTH = 160.0
    MIN_HEIGHT = 80.0

    BACKGROUND = QColor(30, 34, 47, 150)
    BORDER_COLOR = QColor("#4a5063")
    TITLE_BACKGROUND = QColor(42, 49, 66, 220)
    TITLE_COLOR = QColor("#f0f3ff")
    COLLAPSE_INDICATOR = QColor("#8aa8ff")

    geometryChanged = Signal(str, object)  # group_id, GroupGeometry
    collapseToggled = Signal(str, bool)
    positionChanged = Signal(str, QPointF)

    def __init__(self, group_id: str, title: str, *, collapsed: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._group_id = group_id
        self._title = title
        self._collapsed = collapsed
        self._expanded_size = GroupGeometry(self.MIN_WIDTH, self.MIN_HEIGHT)
        self._current_size = GroupGeometry(self.MIN_WIDTH, self.MIN_HEIGHT if not collapsed else self.HEADER_HEIGHT + 10)

        self.setFlag(QGraphicsObject.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.LeftButton | Qt.RightButton)
        self.setOpacity(0.6)
        self.setZValue(-0.5)
        self._last_indicator_rect = QRectF()

    @property
    def group_id(self) -> str:
        return self._group_id

    def title(self) -> str:
        return self._title

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_title(self, title: str) -> None:
        if self._title == title:
            return
        self._title = title
        self.update()

    def set_geometry(self, width: float, height: float) -> None:
        width = max(self.MIN_WIDTH, float(width))
        height = max(self.MIN_HEIGHT, float(height))
        self._expanded_size = GroupGeometry(width, height)
        if not self._collapsed:
            self._update_current_size(width, height)

    def set_collapsed(self, collapsed: bool) -> None:
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        if collapsed:
            self._update_current_size(self._expanded_size.width, self.HEADER_HEIGHT + 10)
        else:
            self._update_current_size(self._expanded_size.width, self._expanded_size.height)
        self.update()

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        return QRectF(0.0, 0.0, self._current_size.width, self._current_size.height)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override]
        _ = option, widget
        rect = self.boundingRect()

        painter.setRenderHint(QPainter.Antialiasing, True)

        # Body
        painter.setPen(QPen(self.BORDER_COLOR, 1.6, Qt.SolidLine))
        painter.setBrush(self.BACKGROUND)
        radius = 10.0
        painter.drawRoundedRect(rect, radius, radius)

        # Header
        header_rect = QRectF(rect.left(), rect.top(), rect.width(), self.HEADER_HEIGHT)
        painter.setBrush(self.TITLE_BACKGROUND)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(header_rect, radius, radius)
        painter.drawRect(
            QRectF(
                header_rect.left(),
                header_rect.top() + self.HEADER_HEIGHT / 2,
                header_rect.width(),
                self.HEADER_HEIGHT / 2,
            )
        )

        painter.setPen(self.TITLE_COLOR)
        font = QFont()
        font.setPointSizeF(9.5)
        font.setBold(True)
        painter.setFont(font)
        title_rect = header_rect.adjusted(14, 0, -48, 0)
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, self._title)

        # Collapse indicator
        indicator_rect = QRectF(
            header_rect.right() - 20,
            header_rect.top() + (self.HEADER_HEIGHT - 14) / 2,
            14,
            14,
        )
        self._last_indicator_rect = indicator_rect
        painter.setBrush(self.COLLAPSE_INDICATOR)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(indicator_rect)

        painter.setPen(QColor("#131722"))
        painter.setBrush(Qt.NoBrush)
        symbol = "−" if not self._collapsed else "+"
        painter.drawText(indicator_rect, Qt.AlignCenter, symbol)

        if self._collapsed:
            return

        # Draw subtle stripes in the body for visual grouping
        painter.setPen(QPen(QColor(255, 255, 255, 18), 1, Qt.DashLine))
        spacing = 16
        y = header_rect.bottom() + spacing
        while y < rect.bottom() - spacing:
            painter.drawLine(rect.left() + 12, y, rect.right() - 12, y)
            y += spacing

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton and self._last_indicator_rect.contains(event.pos()):
            self.set_collapsed(not self._collapsed)
            self.collapseToggled.emit(self._group_id, self._collapsed)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.set_collapsed(not self._collapsed)
            self.collapseToggled.emit(self._group_id, self._collapsed)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def itemChange(self, change: QGraphicsObject.GraphicsItemChange, value):  # type: ignore[override]
        if change == QGraphicsObject.ItemPositionChange:
            new_pos: QPointF = value
            delta = new_pos - self.pos()
            if not delta.isNull():
                self.positionChanged.emit(self._group_id, delta)
        elif change == QGraphicsObject.ItemPositionHasChanged:
            geometry = GroupGeometry(self._expanded_size.width, self._expanded_size.height)
            self.geometryChanged.emit(self._group_id, geometry)
        return super().itemChange(change, value)

    def _update_current_size(self, width: float, height: float) -> None:
        self.prepareGeometryChange()
        self._current_size = GroupGeometry(width, height)

