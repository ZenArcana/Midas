from __future__ import annotations

import logging
import math
from dataclasses import replace
from typing import Dict, Optional

from app.midi import ControlProfile, ControlProfileStore, MidiEvent
from app.nodes import Node, NodeGraph

from .base import ActionContext, BaseAction
from .command import CommandAction
from .script import ScriptAction
from .shortcut import ShortcutAction
from .sound import SoundAction
from .volume import VolumeAction

logger = logging.getLogger(__name__)


class ActionEngine:
    """
    Dispatch MIDI events through the node graph to associated actions.
    """

    def __init__(
        self,
        graph: NodeGraph,
        workspace_id: str = "default",
        profile_store: Optional[ControlProfileStore] = None,
    ) -> None:
        self._graph = graph
        self._workspace_id = workspace_id
        self._profile_store = profile_store or ControlProfileStore()
        self._actions: Dict[str, BaseAction] = {
            "action.volume": VolumeAction(),
            "action.script": ScriptAction(),
            "action.command": CommandAction(),
            "action.shortcut": ShortcutAction(),
            "action.sound": SoundAction(),
        }

    def set_profile_store(self, store: ControlProfileStore) -> None:
        self._profile_store = store

    def handle_event(self, event: MidiEvent) -> tuple[Node, ...]:
        if self._graph.is_empty():
            return tuple()

        matching_profiles = {
            profile.id: profile
            for profile in self._profile_store
            if profile.matches_event(event)
        }

        context = ActionContext(workspace_id=self._workspace_id, graph=self._graph)
        visited: set[tuple[str, Optional[int], Optional[int], Optional[int], Optional[int]]] = set()

        dispatched = False
        triggered_inputs: list[Node] = []
        for node in self._graph.nodes().values():
            if node.type != "midi.input":
                continue
            if not self._node_accepts_event(node, event, matching_profiles):
                continue
            dispatched = True
            triggered_inputs.append(node)
            self._traverse_node(
                node=node,
                event=event,
                context=context,
                matching_profiles=matching_profiles,
                visited=visited,
            )

        if not dispatched:
            # Fallback to any nodes without incoming connections that accept the event.
            for node in self._graph.nodes().values():
                if self._graph.incoming(node.id):
                    continue
                if not self._node_accepts_event(node, event, matching_profiles):
                    continue
                dispatched = True
                triggered_inputs.append(node)
                self._traverse_node(
                    node=node,
                    event=event,
                    context=context,
                    matching_profiles=matching_profiles,
                    visited=visited,
                )

        if not dispatched:
            logger.debug("No nodes accepted the incoming event.")
        return tuple(triggered_inputs)

    def _apply_mapper(self, node: Node, event: MidiEvent) -> MidiEvent:
        if event.value is None:
            return event

        input_min = float(node.config.get("input_min", 0))
        input_max = float(node.config.get("input_max", 127))
        output_min = float(node.config.get("output_min", 0))
        output_max = float(node.config.get("output_max", 127))
        curve = str(node.config.get("curve", "linear")).lower()

        value = float(event.value)
        normalized = (value - input_min) / max(1.0, (input_max - input_min))
        normalized = max(0.0, min(1.0, normalized))

        if curve == "log":
            normalized = math.log1p(normalized * (math.e - 1))
        elif curve == "exp":
            normalized = (math.e**normalized - 1) / (math.e - 1)
        elif curve == "step":
            steps = int(node.config.get("steps", 8))
            steps = max(1, steps)
            normalized = round(normalized * steps) / steps

        mapped_value = output_min + normalized * (output_max - output_min)
        clamped_value = int(round(max(output_min, min(output_max, mapped_value))))

        return replace(event, value=clamped_value)

    def _traverse_node(
        self,
        node: Node,
        event: MidiEvent,
        context: ActionContext,
        matching_profiles: Dict[str, ControlProfile],
        visited: set[tuple[str, Optional[int], Optional[int], Optional[int], Optional[int]]],
    ) -> None:
        signature = (
            node.id,
            event.channel,
            event.control,
            event.note,
            event.value,
        )
        if signature in visited:
            return
        visited.add(signature)

        if node.type == "midi.input":
            outputs = [("message", event)]
        elif node.type == "logic.mapper":
            mapped_event = self._apply_mapper(node, event)
            outputs = [("out", mapped_event)]
        elif node.type.startswith("action."):
            self._process_action_node(node, event, context)
            outputs = []
        else:
            logger.debug("No processor configured for node type %s", node.type)
            outputs = []

        for port_name, out_event in outputs:
            if out_event is None:
                continue
            self._propagate_from_port(
                node,
                port_name,
                out_event,
                context,
                matching_profiles,
                visited,
            )

    def _process_action_node(
        self,
        node: Node,
        event: MidiEvent,
        context: ActionContext,
    ) -> None:
        action = self._actions.get(node.type)
        if action is None:
            logger.debug("Unknown action for node type %s", node.type)
            return
        try:
            action.handle_event(event, node, context)
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception("Action execution failed for node %s: %s", node.id, exc)

    def _propagate_from_port(
        self,
        node: Node,
        port_name: str,
        event: MidiEvent,
        context: ActionContext,
        matching_profiles: Dict[str, ControlProfile],
        visited: set[tuple[str, Optional[int], Optional[int], Optional[int], Optional[int]]],
    ) -> None:
        for connection in self._graph.connections_from(node.id, port_name):
            target = self._graph.get_node(connection.target_node)
            if target is None:
                continue
            if not self._node_accepts_event(target, event, matching_profiles):
                continue
            self._traverse_node(
                target,
                event,
                context,
                matching_profiles,
                visited,
            )

    def _node_accepts_event(
        self,
        node: Node,
        event: MidiEvent,
        matching_profiles: Dict[str, ControlProfile],
    ) -> bool:
        device_ports = node.config.get("device_ports")
        if device_ports:
            ports = {str(port) for port in device_ports}
            aliases = set(event.aliases)
            if event.source not in ports and ports.isdisjoint(aliases):
                return False

        profile_id = node.config.get("profile_id")
        if profile_id:
            profile = matching_profiles.get(profile_id) or self._profile_store.get(profile_id)
            if profile is None or not profile.matches_event(event):
                return False

        return True

