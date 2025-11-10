from __future__ import annotations

from typing import Optional, Tuple

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem


class ConnectionGraphicsItem(QGraphicsPathItem):
    """
    Visual cable between two node ports.
    """

    NORMAL_PEN = QPen(QColor("#7aa2f7"), 2.0)
    HOVER_PEN = QPen(QColor("#c0d7ff"), 2.6)
    SELECTED_PEN = QPen(QColor("#ffcc66"), 3.0)

    def __init__(
        self,
        source: Tuple[str, str],
        target: Optional[Tuple[str, str]] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._target = target

        self.setPen(self.NORMAL_PEN)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(1)
        self.setAcceptHoverEvents(True)

    @property
    def source(self) -> Tuple[str, str]:
        return self._source

    @property
    def target(self) -> Optional[Tuple[str, str]]:
        return self._target

    def set_target(self, target: Optional[Tuple[str, str]]) -> None:
        self._target = target

    def update_path(self, start: QPointF, end: QPointF) -> None:
        path = QPainterPath(start)
        dx = max(abs(end.x() - start.x()) * 0.5, 60.0)
        ctrl1 = QPointF(start.x() + dx, start.y())
        ctrl2 = QPointF(end.x() - dx, end.y())
        path.cubicTo(ctrl1, ctrl2, end)
        self.setPath(path)

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self.setPen(self.HOVER_PEN)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.setPen(self.SELECTED_PEN if self.isSelected() else self.NORMAL_PEN)
        super().hoverLeaveEvent(event)

    def setSelected(self, selected: bool) -> None:  # type: ignore[override]
        super().setSelected(selected)
        if selected:
            self.setPen(self.SELECTED_PEN)
        else:
            self.setPen(self.NORMAL_PEN)

