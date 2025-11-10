from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from app.nodes import NodeGraph, NodeGroup, get_node_template


class WorkspaceStore:
    """
    Persistence helper for saving and loading workspace files.
    """

    VERSION = 1

    def save(self, path: Path, payload: Dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load(self, path: Path) -> Dict[str, Any]:
        contents = path.read_text(encoding="utf-8")
        return json.loads(contents)

    def export_graph(self, graph: NodeGraph) -> Dict[str, Any]:
        data = {
            "version": self.VERSION,
            "nodes": [],
            "connections": [],
        }

        for node in graph.nodes().values():
            position = graph.node_position(node.id) or (0.0, 0.0)
            data["nodes"].append(
                {
                    "id": node.id,
                    "type": node.type,
                    "title": node.title,
                    "config": node.config,
                    "position": position,
                }
            )

        if graph.groups():
            groups_payload = []
            for group in graph.groups():
                groups_payload.append(
                    {
                        "id": group.id,
                        "title": group.title,
                        "nodes": list(group.node_ids),
                        "position": list(group.position),
                        "size": list(group.size),
                        "collapsed": group.collapsed,
                    }
                )
            data["groups"] = groups_payload

        for connection in graph.connections():
            data["connections"].append(
                {
                    "source_node": connection.source_node,
                    "source_port": connection.source_port,
                    "target_node": connection.target_node,
                    "target_port": connection.target_port,
                }
            )

        return data

    def import_graph(self, graph: NodeGraph, payload: Dict[str, Any]) -> None:
        graph.clear()

        nodes_data: Iterable[Dict[str, Any]] = payload.get("nodes", [])
        for node_payload in nodes_data:
            node_type = node_payload.get("type")
            node_id = node_payload.get("id")
            if not node_type or not node_id:
                continue

            try:
                template = get_node_template(node_type)
            except KeyError:
                continue

            node = template.instantiate(node_id)
            node.title = str(node_payload.get("title", node.title))
            config = node_payload.get("config", {})
            if isinstance(config, dict):
                node.config.update(config)

            graph.add_node(node)

            position = node_payload.get("position")
            if isinstance(position, (list, tuple)) and len(position) == 2:
                graph.set_node_position(node.id, float(position[0]), float(position[1]))

        connections_data: Iterable[Dict[str, Any]] = payload.get("connections", [])
        for connection_payload in connections_data:
            source_node = connection_payload.get("source_node")
            source_port = connection_payload.get("source_port")
            target_node = connection_payload.get("target_node")
            target_port = connection_payload.get("target_port")

            if not all([source_node, source_port, target_node, target_port]):
                continue

            graph.connect(
                str(source_node),
                str(source_port),
                str(target_node),
                str(target_port),
            )

        groups_data: Iterable[Dict[str, Any]] = payload.get("groups", [])
        for group_payload in groups_data:
            group_id = group_payload.get("id")
            if not group_id:
                continue
            group = NodeGroup(
                id=str(group_id),
                title=str(group_payload.get("title", "Group")),
                node_ids=[str(node_id) for node_id in group_payload.get("nodes", [])],
                collapsed=bool(group_payload.get("collapsed", False)),
            )
            position = group_payload.get("position")
            if isinstance(position, (list, tuple)) and len(position) == 2:
                group.position = (float(position[0]), float(position[1]))
            size = group_payload.get("size")
            if isinstance(size, (list, tuple)) and len(size) == 2:
                group.size = (float(size[0]), float(size[1]))
            graph.add_group(group)

    def export_workspace(
        self,
        graph: NodeGraph,
        *,
        profiles: Iterable[Dict[str, object]] | None = None,
        virtual_devices: Iterable[Dict[str, object]] | None = None,
        active_devices: Iterable[str] | None = None,
    ) -> Dict[str, Any]:
        payload = self.export_graph(graph)
        if profiles is not None:
            payload["profiles"] = list(profiles)
        if virtual_devices is not None:
            payload["virtual_devices"] = list(virtual_devices)
        if active_devices is not None:
            payload["active_devices"] = list(active_devices)
        return payload

    def import_workspace(
        self,
        graph: NodeGraph,
        payload: Dict[str, Any],
        *,
        profile_store=None,
        midi_manager=None,
    ) -> Dict[str, Any]:
        self.import_graph(graph, payload)
        if profile_store is not None:
            profile_store.load(payload.get("profiles", []))
        if midi_manager is not None:
            midi_manager.import_virtual_devices(payload.get("virtual_devices", []))
        return {
            "active_devices": payload.get("active_devices", []),
        }

    def save_graph(self, path: Path, graph: NodeGraph) -> None:
        payload = self.export_graph(graph)
        self.save(path, payload)

    def load_graph(self, path: Path, graph: NodeGraph) -> None:
        payload = self.load(path)
        self.import_graph(graph, payload)

    def save_workspace(
        self,
        path: Path,
        graph: NodeGraph,
        *,
        profiles: Iterable[Dict[str, object]] | None = None,
        virtual_devices: Iterable[Dict[str, object]] | None = None,
        active_devices: Iterable[str] | None = None,
    ) -> None:
        payload = self.export_workspace(
            graph,
            profiles=profiles,
            virtual_devices=virtual_devices,
            active_devices=active_devices,
        )
        self.save(path, payload)

    def load_workspace(
        self,
        path: Path,
        graph: NodeGraph,
        *,
        profile_store=None,
        midi_manager=None,
    ) -> Dict[str, Any]:
        payload = self.load(path)
        info = self.import_workspace(
            graph,
            payload,
            profile_store=profile_store,
            midi_manager=midi_manager,
        )
        return {"payload": payload, **info}

