from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPainter, QPen
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QInputDialog, QMenu, QWidget

from app.nodes import (
    Node,
    NodeConnection,
    NodeGraph,
    NodeGroup,
    NodeTemplate,
    get_node_template,
    get_node_templates,
)

from .connection_graphics import ConnectionGraphicsItem
from .group_graphics import GroupGraphicsItem, GroupGeometry
from .node_graphics import NodeGraphicsItem


class NodeEditorScene(QGraphicsScene):
    """
    Scene responsible for rendering the node graph and managing graphics items.
    """

    GRID_SIZE = 32
    GRID_PEN = QPen(QColor(70, 76, 92, 110), 1)
    GROUP_MARGIN = 0.0

    portPressed = Signal(str, str, str)  # node_id, direction, port_name
    portReleased = Signal(str, str, str)

    def __init__(self, graph: NodeGraph, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._graph = graph
        self._node_items: Dict[str, NodeGraphicsItem] = {}
        self._connection_items: Dict[Tuple[str, str, str, str], ConnectionGraphicsItem] = {}
        self._temporary_connection: Optional[ConnectionGraphicsItem] = None
        self._group_items: Dict[str, GroupGraphicsItem] = {}
        self._suppress_group_geometry = False
        self._suppress_group_movement = False

    @property
    def graph(self) -> NodeGraph:
        return self._graph

    def drawBackground(self, painter, rect):  # type: ignore[override]
        super().drawBackground(painter, rect)

        start_x = int(rect.left()) - (int(rect.left()) % self.GRID_SIZE)
        start_y = int(rect.top()) - (int(rect.top()) % self.GRID_SIZE)

        painter.setPen(self.GRID_PEN)

        for x in range(start_x, int(rect.right()) + self.GRID_SIZE, self.GRID_SIZE):
            painter.drawLine(x, rect.top(), x, rect.bottom())

        for y in range(start_y, int(rect.bottom()) + self.GRID_SIZE, self.GRID_SIZE):
            painter.drawLine(rect.left(), y, rect.right(), y)

    def add_node_item(self, node: Node, position: Optional[QPointF] = None) -> NodeGraphicsItem:
        item = NodeGraphicsItem(node)
        self._node_items[node.id] = item
        self.addItem(item)

        if position is None:
            stored = self._graph.node_position(node.id)
            if stored is not None:
                position = QPointF(*stored)
            else:
                position = QPointF(0.0, 0.0)

        item.setPos(position)
        self._graph.set_node_position(node.id, position.x(), position.y())
        item.positionChanged.connect(self._handle_node_position_changed)
        item.portPressed.connect(self.portPressed.emit)
        item.portReleased.connect(self.portReleased.emit)
        return item

    def remove_node_item(self, node_id: str) -> None:
        item = self._node_items.pop(node_id, None)
        if item is not None:
            self.removeItem(item)

        for key in [
            key
            for key in self._connection_items.keys()
            if node_id in (key[0], key[2])
        ]:
            self.remove_connection_item(*key)

    def clear_node_items(self) -> None:
        for item in list(self._node_items.values()):
            self.removeItem(item)
        self._node_items.clear()

        for item in list(self._group_items.values()):
            self.removeItem(item)
        self._group_items.clear()

        for item in list(self._connection_items.values()):
            self.removeItem(item)
        self._connection_items.clear()

        self.clear_temporary_connection()

    def refresh_node(self, node: Node) -> None:
        item = self._node_items.get(node.id)
        if item is not None:
            item.update_node(node)

    def selected_node_items(self) -> list[NodeGraphicsItem]:
        return [item for item in self.selectedItems() if isinstance(item, NodeGraphicsItem)]

    def selected_group_items(self) -> list[GroupGraphicsItem]:
        return [item for item in self.selectedItems() if isinstance(item, GroupGraphicsItem)]

    def selected_connection_items(self) -> list[ConnectionGraphicsItem]:
        return [item for item in self.selectedItems() if isinstance(item, ConnectionGraphicsItem)]

    def node_item(self, node_id: str) -> Optional[NodeGraphicsItem]:
        return self._node_items.get(node_id)

    def add_connection_item(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> ConnectionGraphicsItem:
        key = (source_node, source_port, target_node, target_port)
        item = self._connection_items.get(key)
        if item is None:
            item = ConnectionGraphicsItem((source_node, source_port), (target_node, target_port))
            self._connection_items[key] = item
            self.addItem(item)
        self.update_connection_path(item)
        return item

    def remove_connection_item(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> None:
        key = (source_node, source_port, target_node, target_port)
        item = self._connection_items.pop(key, None)
        if item is not None:
            self.removeItem(item)

    def update_connection_path(self, item: ConnectionGraphicsItem) -> None:
        source_node, source_port = item.source
        target = item.target
        start = self.port_scene_position(source_node, "output", source_port)
        end = (
            self.port_scene_position(target[0], "input", target[1])
            if target is not None
            else None
        )
        if start is None:
            return
        item.update_path(start, end or start)

    def update_connections_for_node(self, node_id: str) -> None:
        for key, item in self._connection_items.items():
            if node_id in (key[0], key[2]):
                self.update_connection_path(item)

    def sync_connections(self) -> None:
        graph_keys = {
            (connection.source_node, connection.source_port, connection.target_node, connection.target_port)
            for connection in self._graph.connections()
        }
        existing_keys = set(self._connection_items.keys())

        for key in existing_keys - graph_keys:
            self.remove_connection_item(*key)

        for key in graph_keys - existing_keys:
            self.add_connection_item(*key)

    def start_temporary_connection(self, source_node: str, source_port: str) -> None:
        self.clear_temporary_connection()
        self._temporary_connection = ConnectionGraphicsItem((source_node, source_port))
        self._temporary_connection.setPen(ConnectionGraphicsItem.HOVER_PEN)
        self.addItem(self._temporary_connection)
        start = self.port_scene_position(source_node, "output", source_port)
        if start is not None:
            self._temporary_connection.update_path(start, start)

    def update_temporary_connection(self, scene_pos: QPointF) -> None:
        if self._temporary_connection is None:
            return
        source_node, source_port = self._temporary_connection.source
        start = self.port_scene_position(source_node, "output", source_port)
        if start is None:
            return
        target = self.port_at(scene_pos, "input")
        if target is not None:
            node_id, port_name = target
            self._temporary_connection.set_target(target)
            target_pos = self.port_scene_position(node_id, "input", port_name) or scene_pos
        else:
            self._temporary_connection.set_target(None)
            target_pos = scene_pos
        self._temporary_connection.update_path(start, target_pos)

    def clear_temporary_connection(self) -> None:
        if self._temporary_connection is not None:
            self.removeItem(self._temporary_connection)
            self._temporary_connection = None

    def port_scene_position(self, node_id: str, direction: str, port_name: str) -> Optional[QPointF]:
        node_item = self._node_items.get(node_id)
        if node_item is None:
            return None
        return node_item.scene_port_position(direction, port_name)

    def port_at(self, scene_pos: QPointF, direction: str) -> Optional[Tuple[str, str]]:
        for node_id, node_item in reversed(list(self._node_items.items())):
            port_name = node_item.port_at_scene_position(scene_pos, direction)
            if port_name:
                return node_id, port_name
        return None

    def _handle_node_position_changed(self, node_id: str, x: float, y: float) -> None:
        self._graph.set_node_position(node_id, x, y)
        self.update_connections_for_node(node_id)
        self._update_groups_for_node(node_id)

    def sync_groups(self) -> None:
        graph_groups = {group.id: group for group in self._graph.groups()}
        current_ids = set(self._group_items.keys())

        for group_id in current_ids - graph_groups.keys():
            item = self._group_items.pop(group_id, None)
            if item is not None:
                self.removeItem(item)

        for group_id, group in graph_groups.items():
            item = self._group_items.get(group_id)
            if item is None:
                item = GroupGraphicsItem(group_id, group.title, collapsed=group.collapsed)
                item.geometryChanged.connect(self._handle_group_geometry_changed)
                item.collapseToggled.connect(self._handle_group_collapse_toggled)
                item.positionChanged.connect(self._handle_group_position_changed)
                self._group_items[group_id] = item
                self.addItem(item)

            item.set_title(group.title)
            item.set_collapsed(group.collapsed)

            if not group.collapsed:
                rect = self._calculate_group_rect(group)
                if rect is not None:
                    self._graph.set_group_rect(group.id, rect.x(), rect.y(), rect.width(), rect.height())
                    item.set_geometry(rect.width(), rect.height())
                    self._suppress_group_movement = True
                    item.setPos(rect.topLeft())
                    self._suppress_group_movement = False
                else:
                    item.set_geometry(group.size[0], group.size[1])
                    self._suppress_group_movement = True
                    item.setPos(QPointF(*group.position))
                    self._suppress_group_movement = False
            else:
                item.set_geometry(group.size[0], group.size[1])
                self._suppress_group_movement = True
                item.setPos(QPointF(*group.position))
                self._suppress_group_movement = False

        self._apply_group_visibility()

    def bounding_rect_for_nodes(self, node_ids: Iterable[str]) -> Optional[QRectF]:
        bounding: Optional[QRectF] = None
        for node_id in node_ids:
            item = self._node_items.get(node_id)
            if item is None:
                continue
            rect = item.sceneBoundingRect()
            if bounding is None:
                bounding = QRectF(rect)
            else:
                bounding = bounding.united(rect)
        if bounding is None:
            return None
        header_offset = 40.0
        horiz_padding = 24.0
        top_padding = header_offset
        bottom_padding = 72.0

        bounded = bounding.adjusted(-horiz_padding, -top_padding, horiz_padding, bottom_padding)

        min_width = 200.0
        if bounded.width() < min_width:
            bounded.setWidth(min_width)
        min_height = header_offset + 80.0
        if bounded.height() < min_height:
            bounded.setHeight(min_height)
        return bounded

    def _update_groups_for_node(self, node_id: str) -> None:
        if self._suppress_group_geometry:
            return
        for group in self._graph.groups_containing(node_id):
            self._update_group_geometry(group)

    def _update_group_geometry(self, group: NodeGroup) -> None:
        if self._suppress_group_geometry:
            return
        if group.collapsed:
            return
        rect = self._calculate_group_rect(group)
        if rect is None:
            return
        self._graph.set_group_rect(group.id, rect.x(), rect.y(), rect.width(), rect.height())
        item = self._group_items.get(group.id)
        if item is not None:
            item.set_geometry(rect.width(), rect.height())
            item.setPos(rect.topLeft())

    def _calculate_group_rect(self, group: NodeGroup) -> Optional[QRectF]:
        return self.bounding_rect_for_nodes(group.node_ids)

    def _apply_group_visibility(self) -> None:
        collapsed_nodes = {
            node_id for group in self._graph.groups() if group.collapsed for node_id in group.node_ids
        }
        for node_id, item in self._node_items.items():
            visible = node_id not in collapsed_nodes
            if item.isVisible() != visible:
                item.setVisible(visible)
            if not visible:
                item.setSelected(False)
        for key, item in self._connection_items.items():
            visible = key[0] not in collapsed_nodes and key[2] not in collapsed_nodes
            item.setVisible(visible)

    def _handle_group_geometry_changed(self, group_id: str, geometry: GroupGeometry) -> None:
        item = self._group_items.get(group_id)
        if item is None:
            return
        pos = item.pos()
        self._graph.set_group_rect(group_id, pos.x(), pos.y(), geometry.width, geometry.height)

    def _handle_group_collapse_toggled(self, group_id: str, collapsed: bool) -> None:
        self._graph.set_group_collapsed(group_id, collapsed)
        group = self._graph.get_group(group_id)
        if group is None:
            return
        if not collapsed:
            self._update_group_geometry(group)
        else:
            item = self._group_items.get(group_id)
            if item is not None:
                self._graph.set_group_rect(group_id, item.pos().x(), item.pos().y(), group.size[0], group.size[1])
        self._apply_group_visibility()

    def _handle_group_position_changed(self, group_id: str, delta: QPointF) -> None:
        if self._suppress_group_movement:
            return
        if delta.isNull():
            return
        group = self._graph.get_group(group_id)
        if group is None:
            return

        self._suppress_group_geometry = True
        try:
            for node_id in group.node_ids:
                node_item = self._node_items.get(node_id)
                if node_item is None:
                    continue
                new_pos = node_item.pos() + delta
                node_item.setPos(new_pos)
                self._graph.set_node_position(node_id, new_pos.x(), new_pos.y())
                self.update_connections_for_node(node_id)
        finally:
            self._suppress_group_geometry = False

        group.position = (group.position[0] + delta.x(), group.position[1] + delta.y())
        self._graph.set_group_rect(group_id, group.position[0], group.position[1], group.size[0], group.size[1])
        self._apply_group_visibility()

@dataclass
class PendingConnection:
    node_id: str
    port_name: str


class NodeEditorView(QGraphicsView):
    """
    Graphics view wrapper around the node editor scene.
    """

    selectionChanged = Signal(object)  # list[Node]
    connectionCreated = Signal(object)  # NodeConnection
    connectionDeleted = Signal(object)  # NodeConnection

    def __init__(self, graph: Optional[NodeGraph] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._graph = graph or NodeGraph()
        self._templates: tuple[NodeTemplate, ...] = tuple(
            sorted(get_node_templates(), key=lambda template: (template.category, template.title))
        )
        self._scene = NodeEditorScene(self._graph, self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)

        self._scene.portPressed.connect(self._on_port_pressed)
        self._scene.portReleased.connect(self._on_port_released)
        self._scene.selectionChanged.connect(self._emit_selection_changed)

        self._pending_connection: Optional[PendingConnection] = None

        self._populate_from_graph()
        self._scene.sync_connections()
        self._scene.sync_groups()
        self._center_on_graph()

    @property
    def templates(self) -> Iterable[NodeTemplate]:
        return self._templates

    @property
    def graph(self) -> NodeGraph:
        return self._graph

    def add_node(self, node_type: str, position: Optional[QPointF] = None) -> Optional[Node]:
        try:
            template = get_node_template(node_type)
        except KeyError:
            return None

        node_id = uuid.uuid4().hex
        node = template.instantiate(node_id)
        self._graph.add_node(node)
        if position is None:
            position = self.mapToScene(self.viewport().rect().center())
        self._scene.add_node_item(node, position)
        self._scene.sync_connections()
        self._scene.sync_groups()
        return node

    def contextMenuEvent(self, event) -> None:  # type: ignore[override]
        scene_pos = self.mapToScene(event.pos())
        menu = QMenu(self)

        selected_node_items = self._scene.selected_node_items()
        selected_group_items = self._scene.selected_group_items()
        group_item = selected_group_items[0] if len(selected_group_items) == 1 else None

        group_action = None
        rename_group_action = None
        toggle_group_action = None
        delete_group_action = None

        if selected_node_items:
            if group_item is not None:
                group_action = menu.addAction("Add Selected Nodes to Group")
            else:
                group_action = menu.addAction("Group Selected Nodes")

        if selected_group_items:
            if group_item is not None:
                rename_group_action = menu.addAction("Rename Group…")
                toggle_text = "Collapse Group" if not group_item.is_collapsed() else "Expand Group"
                toggle_group_action = menu.addAction(toggle_text)
            delete_group_action = menu.addAction("Delete Group")

        if selected_node_items or selected_group_items:
            menu.addSeparator()

        last_category = None
        for template in self._templates:
            if template.category != last_category:
                menu.addSection(template.category)
                last_category = template.category
            action = menu.addAction(template.title)
            action.setData(template.type)
            action.setToolTip(template.description)
            action.setStatusTip(template.description)

        menu.addSeparator()
        reset_action = menu.addAction("Reset View")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return

        if chosen == group_action and selected_node_items:
            if group_item is not None:
                self._add_nodes_to_group(group_item.group_id, selected_node_items)
            else:
                self._create_group_from_selection(selected_node_items)
            return
        if chosen == rename_group_action and group_item is not None:
            self._rename_group(group_item.group_id)
            return
        if chosen == toggle_group_action and group_item is not None:
            self._toggle_group_collapse(group_item.group_id)
            return
        if chosen == delete_group_action and selected_group_items:
            self._delete_groups(selected_group_items)
            return

        if chosen == reset_action:
            self.resetTransform()
            self.centerOn(0, 0)
            return

        node_type = chosen.data()
        if node_type:
            self.add_node(str(node_type), scene_pos)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        if event.key() in {Qt.Key_Delete, Qt.Key_Backspace}:
            self._delete_selected_items()
            event.accept()
            return
        if event.key() == Qt.Key_Escape and self._pending_connection is not None:
            self._cancel_pending_connection()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        if event.modifiers() & Qt.ControlModifier:
            zoom_factor = 1.2 if event.angleDelta().y() > 0 else 1 / 1.2
            self.scale(zoom_factor, zoom_factor)
        else:
            super().wheelEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._pending_connection is not None:
            self._scene.update_temporary_connection(self.mapToScene(event.pos()))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        if self._pending_connection is not None:
            scene_pos = self.mapToScene(event.pos())
            target = self._scene.port_at(scene_pos, "input")
            if target is not None:
                node_id, port_name = target
                self._handle_port_release(node_id, "input", port_name)
                event.accept()
                return

        super().mouseReleaseEvent(event)
        if self._pending_connection is not None:
            # Released somewhere that is not a port; cancel
            self._cancel_pending_connection()

    def delete_selected_nodes(self) -> None:
        self._delete_selected_items()

    def reload(self) -> None:
        self._scene.clear_node_items()
        self._populate_from_graph()
        self._scene.sync_connections()
        self._scene.sync_groups()
        self._center_on_graph()
        self._emit_selection_changed()

    def update_node(self, node: Node) -> None:
        self._scene.refresh_node(node)
        self._scene.sync_groups()

    def _populate_from_graph(self) -> None:
        for node in self._graph.nodes().values():
            self._scene.add_node_item(node)

    def _delete_selected_items(self) -> None:
        for connection_item in list(self._scene.selected_connection_items()):
            source_node, source_port = connection_item.source
            target_node, target_port = connection_item.target or ("", "")
            if target_node:
                self._graph.disconnect(source_node, source_port, target_node, target_port)
                self._scene.remove_connection_item(source_node, source_port, target_node, target_port)
                self._emit_connection_deleted(
                    NodeConnection(source_node, source_port, target_node, target_port)
                )

        for item in list(self._scene.selected_node_items()):
            node_id = item.node.id
            self._graph.remove_node(node_id)
            self._scene.remove_node_item(node_id)

        self._scene.sync_connections()
        self._scene.sync_groups()

    def _center_on_graph(self) -> None:
        items = self._scene.items()
        if not items:
            self.centerOn(0, 0)
            return
        rect = self._scene.itemsBoundingRect()
        self.centerOn(rect.center())

    def _emit_selection_changed(self) -> None:
        nodes = [item.node for item in self._scene.selected_node_items()]
        self.selectionChanged.emit(nodes)

    def _on_port_pressed(self, node_id: str, direction: str, port_name: str) -> None:
        if direction != "output":
            return
        self._pending_connection = PendingConnection(node_id=node_id, port_name=port_name)
        self._scene.start_temporary_connection(node_id, port_name)

    def _on_port_released(self, node_id: str, direction: str, port_name: str) -> None:
        self._handle_port_release(node_id, direction, port_name)

    def _handle_port_release(self, node_id: str, direction: str, port_name: str) -> None:
        if self._pending_connection is None:
            return

        if direction == "input":
            source = self._pending_connection
            if self._graph.connect(source.node_id, source.port_name, node_id, port_name):
                connection = NodeConnection(source.node_id, source.port_name, node_id, port_name)
                self._scene.sync_connections()
                self._emit_connection_created(connection)
        self._cancel_pending_connection()

    def _cancel_pending_connection(self) -> None:
        self._pending_connection = None
        self._scene.clear_temporary_connection()

    def _emit_connection_created(self, connection: NodeConnection) -> None:
        self.connectionCreated.emit(connection)

    def _emit_connection_deleted(self, connection: NodeConnection) -> None:
        self.connectionDeleted.emit(connection)

    def _create_group_from_selection(self, items: list[NodeGraphicsItem]) -> None:
        node_ids = [item.node.id for item in items]
        rect = self._scene.bounding_rect_for_nodes(node_ids)

        group_id = uuid.uuid4().hex
        title = f"Group {len(self._graph.groups()) + 1}"
        group = NodeGroup(id=group_id, title=title, node_ids=node_ids)

        if rect is not None:
            group.position = (rect.x(), rect.y())
            group.size = (rect.width(), rect.height())
        else:
            center = self.mapToScene(self.viewport().rect().center())
            group.position = (center.x() - GroupGraphicsItem.MIN_WIDTH / 2, center.y() - GroupGraphicsItem.MIN_HEIGHT / 2)
            group.size = (GroupGraphicsItem.MIN_WIDTH, GroupGraphicsItem.MIN_HEIGHT)

        self._graph.add_group(group)
        self._scene.sync_groups()

    def _add_nodes_to_group(self, group_id: str, items: list[NodeGraphicsItem]) -> None:
        group = self._graph.get_group(group_id)
        if group is None:
            return

        node_ids = list(dict.fromkeys(group.node_ids + [item.node.id for item in items]))
        self._graph.set_group_nodes(group_id, node_ids)
        self._scene.sync_groups()

    def _rename_group(self, group_id: str) -> None:
        group = self._graph.get_group(group_id)
        if group is None:
            return
        text, ok = QInputDialog.getText(self, "Rename Group", "Group name:", text=group.title)
        if ok and text.strip():
            self._graph.set_group_title(group_id, text.strip())
            self._scene.sync_groups()

    def _toggle_group_collapse(self, group_id: str) -> None:
        group = self._graph.get_group(group_id)
        if group is None:
            return
        self._graph.set_group_collapsed(group_id, not group.collapsed)
        self._scene.sync_groups()

    def _delete_groups(self, items: list[GroupGraphicsItem]) -> None:
        for item in items:
            self._graph.remove_group(item.group_id)
        self._scene.sync_groups()

