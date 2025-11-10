from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from .base import Node, NodePort, NodePortDirection


@dataclass
class NodeConnection:
    source_node: str
    source_port: str
    target_node: str
    target_port: str


@dataclass
class NodeGroup:
    id: str
    title: str = "Group"
    node_ids: List[str] = field(default_factory=list)
    position: Tuple[float, float] = (0.0, 0.0)
    size: Tuple[float, float] = (240.0, 180.0)
    collapsed: bool = False


class NodeGraph:
    """
    In-memory representation of the node graph to be used by the UI and
    runtime systems.
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, Node] = {}
        self._connections: List[NodeConnection] = []
        self._groups: Dict[str, NodeGroup] = {}

    def add_node(self, node: Node) -> None:
        node.config.setdefault("position", (0.0, 0.0))
        self._nodes[node.id] = node

    def remove_node(self, node_id: str) -> None:
        self._nodes.pop(node_id, None)
        self._connections = [
            connection
            for connection in self._connections
            if connection.source_node != node_id
            and connection.target_node != node_id
        ]
        groups_to_remove: List[str] = []
        for group in self._groups.values():
            if node_id in group.node_ids:
                group.node_ids = [nid for nid in group.node_ids if nid != node_id]
                if not group.node_ids:
                    groups_to_remove.append(group.id)
        for group_id in groups_to_remove:
            self.remove_group(group_id)

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def get_port(self, node_id: str, port_name: str) -> Optional[NodePort]:
        node = self._nodes.get(node_id)
        if node is None:
            return None
        for port in node.inputs + node.outputs:
            if port.name == port_name:
                return port
        return None

    def can_connect(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> Tuple[bool, Optional[str]]:
        if source_node == target_node:
            return False, "Cannot connect a node to itself."

        source = self.get_port(source_node, source_port)
        target = self.get_port(target_node, target_port)

        if source is None or target is None:
            return False, "One of the ports does not exist."

        if source.direction != NodePortDirection.OUTPUT:
            return False, "Source port must be an output."
        if target.direction != NodePortDirection.INPUT:
            return False, "Target port must be an input."

        if not self._is_compatible(source, target):
            return False, "Incompatible port data types."

        existing = self._find_connection(
            source_node, source_port, target_node, target_port
        )
        if existing is not None:
            return False, "Connection already exists."

        for connection in self._connections:
            if (
                connection.target_node == target_node
                and connection.target_port == target_port
            ):
                return False, "Target port already has an incoming connection."

        return True, None

    def connect(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> bool:
        ok, _reason = self.can_connect(source_node, source_port, target_node, target_port)
        if not ok:
            return False

        connection = NodeConnection(source_node, source_port, target_node, target_port)
        self._connections.append(connection)
        return True

    def disconnect(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> None:
        self._connections = [
            connection
            for connection in self._connections
            if not (
                connection.source_node == source_node
                and connection.source_port == source_port
                and connection.target_node == target_node
                and connection.target_port == target_port
            )
        ]

    def disconnect_connection(self, connection: NodeConnection) -> None:
        self.disconnect(
            connection.source_node,
            connection.source_port,
            connection.target_node,
            connection.target_port,
        )

    def _find_connection(
        self,
        source_node: str,
        source_port: str,
        target_node: str,
        target_port: str,
    ) -> Optional[NodeConnection]:
        for connection in self._connections:
            if (
                connection.source_node == source_node
                and connection.source_port == source_port
                and connection.target_node == target_node
                and connection.target_port == target_port
            ):
                return connection
        return None

    def nodes(self) -> Dict[str, Node]:
        return dict(self._nodes)

    def groups(self) -> Tuple[NodeGroup, ...]:
        return tuple(self._groups.values())

    def add_group(self, group: NodeGroup) -> None:
        self._groups[group.id] = group
        self._normalize_group_members(group.id)

    def remove_group(self, group_id: str) -> None:
        self._groups.pop(group_id, None)

    def get_group(self, group_id: str) -> Optional[NodeGroup]:
        return self._groups.get(group_id)

    def set_group_title(self, group_id: str, title: str) -> None:
        group = self._groups.get(group_id)
        if group is not None:
            group.title = title

    def set_group_nodes(self, group_id: str, node_ids: Iterable[str]) -> None:
        group = self._groups.get(group_id)
        if group is not None:
            group.node_ids = list(dict.fromkeys(str(node_id) for node_id in node_ids))
            self._normalize_group_members(group_id)

    def set_group_rect(self, group_id: str, x: float, y: float, width: float, height: float) -> None:
        group = self._groups.get(group_id)
        if group is not None:
            group.position = (float(x), float(y))
            group.size = (max(40.0, float(width)), max(40.0, float(height)))

    def set_group_collapsed(self, group_id: str, collapsed: bool) -> None:
        group = self._groups.get(group_id)
        if group is not None:
            group.collapsed = bool(collapsed)

    def groups_containing(self, node_id: str) -> Tuple[NodeGroup, ...]:
        return tuple(group for group in self._groups.values() if node_id in group.node_ids)

    def is_node_collapsed(self, node_id: str) -> bool:
        return any(group.collapsed for group in self.groups_containing(node_id))

    def connections(self) -> Tuple[NodeConnection, ...]:
        return tuple(self._connections)

    def outgoing(self, node_id: str) -> Tuple[NodeConnection, ...]:
        return tuple(
            connection
            for connection in self._connections
            if connection.source_node == node_id
        )

    def connections_from(
        self,
        node_id: str,
        port_name: Optional[str] = None,
    ) -> Tuple[NodeConnection, ...]:
        connections = [
            connection
            for connection in self._connections
            if connection.source_node == node_id
        ]
        if port_name is not None:
            connections = [
                connection
                for connection in connections
                if connection.source_port == port_name
            ]
        return tuple(connections)

    def incoming(self, node_id: str) -> Tuple[NodeConnection, ...]:
        return tuple(
            connection
            for connection in self._connections
            if connection.target_node == node_id
        )

    def connections_from(
        self, node_id: str, port_name: Optional[str] = None
    ) -> Tuple[NodeConnection, ...]:
        connections = [
            connection
            for connection in self._connections
            if connection.source_node == node_id
            and (port_name is None or connection.source_port == port_name)
        ]
        return tuple(connections)

    def connections_to(
        self, node_id: str, port_name: Optional[str] = None
    ) -> Tuple[NodeConnection, ...]:
        connections = [
            connection
            for connection in self._connections
            if connection.target_node == node_id
            and (port_name is None or connection.target_port == port_name)
        ]
        return tuple(connections)

    def set_node_position(self, node_id: str, x: float, y: float) -> None:
        node = self._nodes.get(node_id)
        if node is not None:
            node.config["position"] = (float(x), float(y))

    def node_position(self, node_id: str) -> Optional[Tuple[float, float]]:
        node = self._nodes.get(node_id)
        if node is not None:
            position = node.config.get("position")
            if isinstance(position, Iterable):
                items = list(position)
                if len(items) == 2:
                    return float(items[0]), float(items[1])
        return None

    def is_empty(self) -> bool:
        return not self._nodes

    def clear(self) -> None:
        self._nodes.clear()
        self._connections.clear()
        self._groups.clear()

    def _is_compatible(self, source: NodePort, target: NodePort) -> bool:
        if source.data_type == "any" or target.data_type == "any":
            return True
        return source.data_type == target.data_type

    def _normalize_group_members(self, group_id: str) -> None:
        group = self._groups.get(group_id)
        if group is None:
            return

        unique_members: list[str] = []
        seen: set[str] = set()
        for node_id in list(group.node_ids):
            node_id = str(node_id)
            if node_id not in self._nodes:
                continue
            if node_id in seen:
                continue
            seen.add(node_id)
            unique_members.append(node_id)
            for other_id, other in self._groups.items():
                if other_id == group_id:
                    continue
                if node_id in other.node_ids:
                    other.node_ids = [nid for nid in other.node_ids if nid != node_id]
        group.node_ids = unique_members

