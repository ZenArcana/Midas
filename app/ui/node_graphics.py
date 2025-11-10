from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject

from app.nodes import Node, NodePortDirection


class PortHandleItem(QGraphicsObject):
    """
    Invisible interactive hotspot for a node port.
    """

    pressed = Signal(str, str)  # direction, port name
    released = Signal(str, str)
    hovered = Signal(str, str, bool)

    def __init__(self, direction: str, port_name: str, radius: float, parent=None):
        super().__init__(parent)
        self._direction = direction
        self._port_name = port_name
        self._radius = radius
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        size = self._radius * 2 + 6
        return QRectF(-size / 2, -size / 2, size, size)

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        # Hotspot does not render visible content.
        _ = painter, option, widget

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.pressed.emit(self._direction, self._port_name)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if event.button() == Qt.LeftButton:
            self.released.emit(self._direction, self._port_name)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def hoverEnterEvent(self, event) -> None:  # type: ignore[override]
        self.hovered.emit(self._direction, self._port_name, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # type: ignore[override]
        self.hovered.emit(self._direction, self._port_name, False)
        super().hoverLeaveEvent(event)


BADGE_STYLES: dict[str, tuple[str, QColor]] = {
    "key": ("KEY", QColor("#f4b860")),
    "pad": ("PAD", QColor("#d087ff")),
    "knob": ("KNB", QColor("#65c3ba")),
    "fader": ("FDR", QColor("#5aa9e6")),
}
CUSTOM_BADGE_COLOR = QColor("#9aa5b1")
DEFAULT_INDICATOR_COLOR = QColor("#7aa2f7")
INDICATOR_TRACK_COLOR = QColor("#1f2230")


class NodeGraphicsItem(QGraphicsObject):
    """
    Visual representation of a node in the graphics scene.
    """

    positionChanged = Signal(str, float, float)
    portPressed = Signal(str, str, str)  # node_id, direction, port_name
    portReleased = Signal(str, str, str)

    WIDTH = 220
    HEADER_HEIGHT = 38
    PORT_HEIGHT = 24
    PADDING = 12

    TITLE_BRUSH = QColor("#23262f")
    BODY_BRUSH = QColor("#2f3340")
    BORDER_PEN = QPen(QColor("#3e4455"), 1.5)
    SELECTED_BORDER_PEN = QPen(QColor("#7aa2f7"), 2.4)
    TEXT_COLOR = QColor("#f0f3ff")
    PORT_COLOR = QColor("#86c1b9")
    PORT_HOVER_COLOR = QColor("#c0f0e5")
    PORT_RADIUS = 6

    def __init__(self, node: Node, parent: Optional[QGraphicsItem] = None) -> None:
        super().__init__(parent)
        self._node = node
        self._input_port_positions: Dict[str, QPointF] = {}
        self._output_port_positions: Dict[str, QPointF] = {}
        self._input_handles: Dict[str, PortHandleItem] = {}
        self._output_handles: Dict[str, PortHandleItem] = {}
        self._hover_port: Optional[Tuple[str, str]] = None  # direction, name

        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setZValue(5)
        self.setToolTip(node.config.get("_description", node.title))

        self._create_port_handles()

    @property
    def node(self) -> Node:
        return self._node

    def boundingRect(self) -> QRectF:  # type: ignore[override]
        port_rows = max(len(self._node.inputs), len(self._node.outputs))
        body_height = max(1, port_rows) * self.PORT_HEIGHT
        height = self.HEADER_HEIGHT + body_height + self.PADDING * 2
        return QRectF(0, 0, self.WIDTH, height)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # type: ignore[override, unused-argument]
        rect = self.boundingRect()

        # Body
        painter.setPen(Qt.NoPen)
        painter.setBrush(self.BODY_BRUSH)
        painter.drawRoundedRect(rect, 8, 8)

        # Header
        header_rect = QRectF(rect.left(), rect.top(), rect.width(), self.HEADER_HEIGHT)
        painter.setBrush(self.TITLE_BRUSH)
        painter.drawRoundedRect(header_rect, 8, 8)
        painter.drawRect(
            QRectF(
                header_rect.left(),
                header_rect.top() + self.HEADER_HEIGHT / 2,
                header_rect.width(),
                self.HEADER_HEIGHT / 2,
            )
        )

        # Border
        painter.setBrush(Qt.NoBrush)
        painter.setPen(self.SELECTED_BORDER_PEN if self.isSelected() else self.BORDER_PEN)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

        # Title
        painter.setPen(self.TEXT_COLOR)
        font = QFont()
        font.setPointSizeF(10.5)
        font.setBold(True)
        painter.setFont(font)
        canonical_type, badge_label, badge_color = self._control_display_info()

        available_right = header_rect.right() - self.PADDING

        indicator_rect = self._draw_value_indicator(
            painter, header_rect, available_right, canonical_type, badge_color
        )
        if indicator_rect is not None:
            available_right = indicator_rect.left() - self.PADDING

        if badge_label:
            badge_rect = self._draw_badge(
                painter,
                header_rect,
                available_right,
                badge_label,
                badge_color or CUSTOM_BADGE_COLOR,
            )
            if badge_rect is not None:
                available_right = badge_rect.left() - self.PADDING

        title_rect = QRectF(
            header_rect.left() + self.PADDING,
            header_rect.top(),
            max(0.0, available_right - (header_rect.left() + self.PADDING)),
            self.HEADER_HEIGHT,
        )
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, self._node.title)

        # Ports
        painter.setFont(QFont("Sans Serif", 9))
        self._draw_ports(painter, rect)

    def _draw_ports(self, painter: QPainter, rect: QRectF) -> None:
        self._input_port_positions.clear()
        self._output_port_positions.clear()

        hovered = self._hover_port

        port_rows = max(len(self._node.inputs), len(self._node.outputs))
        body_height = max(1, port_rows) * self.PORT_HEIGHT
        body_top = rect.top() + self.HEADER_HEIGHT
        body_rect = QRectF(
            rect.left() + self.PADDING,
            body_top + self.PADDING,
            rect.width() - self.PADDING * 2,
            body_height,
        )

        painter.setPen(self.TEXT_COLOR)

        for index, port in enumerate(self._node.inputs):
            y = body_rect.top() + index * self.PORT_HEIGHT + self.PORT_HEIGHT / 2
            position = QPointF(body_rect.left(), y)
            painter.setBrush(
                self.PORT_HOVER_COLOR
                if hovered == ("input", port.name)
                else self.PORT_COLOR
            )
            painter.drawEllipse(position, self.PORT_RADIUS, self.PORT_RADIUS)
            self._input_port_positions[port.name] = position
            painter.drawText(
                QRectF(
                    position.x() + self.PORT_RADIUS * 2 + 4,
                    y - self.PORT_HEIGHT / 2,
                    body_rect.width() / 2,
                    self.PORT_HEIGHT,
                ),
                Qt.AlignVCenter | Qt.AlignLeft,
                port.name,
            )

        for index, port in enumerate(self._node.outputs):
            y = body_rect.top() + index * self.PORT_HEIGHT + self.PORT_HEIGHT / 2
            position = QPointF(body_rect.right(), y)
            painter.setBrush(
                self.PORT_HOVER_COLOR
                if hovered == ("output", port.name)
                else self.PORT_COLOR
            )
            painter.drawEllipse(position, self.PORT_RADIUS, self.PORT_RADIUS)
            self._output_port_positions[port.name] = position
            painter.drawText(
                QRectF(
                    position.x() - self.PORT_RADIUS * 2 - (body_rect.width() / 2) - 4,
                    y - self.PORT_HEIGHT / 2,
                    body_rect.width() / 2,
                    self.PORT_HEIGHT,
                ),
                Qt.AlignVCenter | Qt.AlignRight,
                port.name,
            )

        self.update_port_handle_positions()

    def input_port_position(self, name: str) -> Optional[QPointF]:
        return self._input_port_positions.get(name)

    def output_port_position(self, name: str) -> Optional[QPointF]:
        return self._output_port_positions.get(name)

    def update_node(self, node: Node) -> None:
        self.prepareGeometryChange()
        self._node = node
        self._recreate_port_handles()
        self.setToolTip(node.config.get("_description", node.title))
        self.update()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value):  # type: ignore[override]
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.positionChanged.emit(self._node.id, value.x(), value.y())
        return super().itemChange(change, value)

    def scene_port_position(self, direction: str, port_name: str) -> Optional[QPointF]:
        if direction == "input":
            position = self._input_port_positions.get(port_name)
        else:
            position = self._output_port_positions.get(port_name)
        if position is None:
            return None
        return self.mapToScene(position)

    def _create_port_handles(self) -> None:
        radius = self.PORT_RADIUS
        for port in self._node.inputs:
            handle = PortHandleItem("input", port.name, radius, self)
            handle.pressed.connect(self._emit_port_pressed)
            handle.released.connect(self._emit_port_released)
            handle.hovered.connect(self._set_hover_port)
            self._input_handles[port.name] = handle
        for port in self._node.outputs:
            handle = PortHandleItem("output", port.name, radius, self)
            handle.pressed.connect(self._emit_port_pressed)
            handle.released.connect(self._emit_port_released)
            handle.hovered.connect(self._set_hover_port)
            self._output_handles[port.name] = handle

    def _recreate_port_handles(self) -> None:
        for handle in list(self._input_handles.values()) + list(self._output_handles.values()):
            handle.setParentItem(None)
        self._input_handles.clear()
        self._output_handles.clear()
        self._create_port_handles()

    def _emit_port_pressed(self, direction: str, port_name: str) -> None:
        self.portPressed.emit(self._node.id, direction, port_name)

    def _emit_port_released(self, direction: str, port_name: str) -> None:
        self.portReleased.emit(self._node.id, direction, port_name)

    def _set_hover_port(self, direction: str, port_name: str, hovered: bool) -> None:
        self._hover_port = (direction, port_name) if hovered else None
        self.update()

    def update_port_handle_positions(self) -> None:
        for name, position in self._input_port_positions.items():
            handle = self._input_handles.get(name)
            if handle:
                handle.setPos(position)
        for name, position in self._output_port_positions.items():
            handle = self._output_handles.get(name)
            if handle:
                handle.setPos(position)
        scene = self.scene()
        if scene is not None and hasattr(scene, "update_connections_for_node"):
            scene.update_connections_for_node(self._node.id)

    def port_at_scene_position(self, scene_pos: QPointF, direction: str, threshold: float = 12.0) -> Optional[str]:
        if direction == "input":
            ports = self._input_port_positions.items()
        else:
            ports = self._output_port_positions.items()

        threshold_sq = threshold * threshold
        for name, local_pos in ports:
            world_pos = self.mapToScene(local_pos)
            dx = world_pos.x() - scene_pos.x()
            dy = world_pos.y() - scene_pos.y()
            if dx * dx + dy * dy <= threshold_sq:
                return name
        return None

    def _control_display_info(self) -> tuple[Optional[str], Optional[str], Optional[QColor]]:
        if self._node.type != "midi.input":
            return None, None, None

        raw_mode = str(self._node.config.get("display_control_type") or "auto").lower()
        label_override = str(self._node.config.get("display_control_label") or "").strip()

        if raw_mode == "custom":
            if not label_override:
                return None, None, None
            return "custom", label_override[:8].upper(), CUSTOM_BADGE_COLOR

        if raw_mode == "auto":
            raw_type = str(self._node.config.get("control_type") or "").lower()
        else:
            raw_type = raw_mode

        canonical = self._canonical_control_type(raw_type)
        if canonical is None:
            if raw_type:
                return "custom", raw_type[:8].upper(), CUSTOM_BADGE_COLOR
            return None, None, None

        label, color = BADGE_STYLES[canonical]
        return canonical, label, color

    @staticmethod
    def _canonical_control_type(control_type: str) -> Optional[str]:
        value = control_type.lower()
        if not value:
            return None
        if value in {"key", "button", "note", "note_on", "note_off"}:
            return "key"
        if value in {"pad", "drum_pad", "pad_button"}:
            return "pad"
        if value in {"fader", "slider"}:
            return "fader"
        if value in {"knob", "dial", "continuous", "control_change"}:
            return "knob"
        return None

    def _draw_badge(
        self,
        painter: QPainter,
        header_rect: QRectF,
        right_edge: float,
        label: str,
        color: QColor,
    ) -> Optional[QRectF]:
        label = label.strip()
        if not label:
            return None

        painter.save()
        badge_font = QFont()
        badge_font.setPointSizeF(8.5)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(label)
        padding_x = 8
        padding_y = 4
        badge_width = text_width + padding_x * 2
        badge_height = metrics.height() + padding_y * 2
        max_width = header_rect.width() / 2
        if badge_width > max_width:
            badge_width = max_width
        badge_rect = QRectF(
            right_edge - badge_width,
            header_rect.top() + (self.HEADER_HEIGHT - badge_height) / 2,
            badge_width,
            badge_height,
        )

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawRoundedRect(badge_rect, badge_height / 2, badge_height / 2)
        painter.setPen(QColor("#111318"))
        painter.drawText(badge_rect, Qt.AlignCenter, label)
        painter.restore()
        return badge_rect

    def _draw_value_indicator(
        self,
        painter: QPainter,
        header_rect: QRectF,
        right_edge: float,
        canonical_type: Optional[str],
        accent_color: Optional[QColor],
    ) -> Optional[QRectF]:
        raw_value = self._node.config.get("_display_last_value")
        if raw_value is None:
            return None

        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return None

        value = max(0.0, min(1.0, value))
        active = bool(self._node.config.get("_display_last_active", value > 0.001))
        accent = accent_color or DEFAULT_INDICATOR_COLOR

        painter.save()

        if canonical_type == "fader":
            width = 12.0
            height = self.HEADER_HEIGHT - 12.0
            width = min(width, max(8.0, header_rect.width() * 0.1))
            rect = QRectF(
                right_edge - width,
                header_rect.top() + (self.HEADER_HEIGHT - height) / 2,
                width,
                height,
            )
            painter.setPen(QPen(QColor("#000000"), 0.8))
            painter.setBrush(INDICATOR_TRACK_COLOR)
            painter.drawRoundedRect(rect, width / 2, width / 2)

            fill_height = rect.height() * value
            fill_rect = QRectF(rect.left(), rect.bottom() - fill_height, rect.width(), fill_height)
            painter.setBrush(accent)
            painter.setPen(Qt.NoPen)
            if fill_height > 1.0:
                inner_rect = fill_rect.adjusted(1, 1, -1, -1)
                if inner_rect.height() <= 0:
                    inner_rect = fill_rect
                painter.drawRoundedRect(inner_rect, width / 2.2, width / 2.2)
            else:
                painter.drawRect(fill_rect)
            painter.restore()
            return rect

        if canonical_type == "knob":
            size = min(self.HEADER_HEIGHT - 8.0, 22.0)
            rect = QRectF(
                right_edge - size,
                header_rect.top() + (self.HEADER_HEIGHT - size) / 2,
                size,
                size,
            )
            center = rect.center()
            radius = size / 2 - 2

            painter.setPen(QPen(QColor("#000000"), 0.8))
            painter.setBrush(INDICATOR_TRACK_COLOR)
            painter.drawEllipse(rect)

            angle = -135 + value * 270
            radians = math.radians(angle)
            end_point = QPointF(
                center.x() + radius * math.cos(radians),
                center.y() - radius * math.sin(radians),
            )
            painter.setPen(QPen(accent, 2.4))
            painter.drawLine(center, end_point)
            painter.restore()
            return rect

        if canonical_type in {"key", "pad"}:
            width = 18.0
            height = self.HEADER_HEIGHT - 14.0
            rect = QRectF(
                right_edge - width,
                header_rect.top() + (self.HEADER_HEIGHT - height) / 2,
                width,
                height,
            )
            painter.setPen(QPen(QColor("#000000"), 0.8))
            painter.setBrush(accent if active else INDICATOR_TRACK_COLOR)
            painter.drawRoundedRect(rect, 4, 4)
            painter.restore()
            return rect

        # fallback simple meter
        width = 18.0
        height = 6.0
        rect = QRectF(
            right_edge - width,
            header_rect.top() + (self.HEADER_HEIGHT - height) / 2,
            width,
            height,
        )
        painter.setPen(QPen(QColor("#000000"), 0.8))
        painter.setBrush(INDICATOR_TRACK_COLOR)
        painter.drawRoundedRect(rect, height / 2, height / 2)

        fill_width = rect.width() * value
        fill_rect = QRectF(rect.left(), rect.top(), fill_width, rect.height())
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(fill_rect, height / 2, height / 2)

        painter.restore()
        return rect

