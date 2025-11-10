from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:  # pragma: no cover - type checking imports
    from app.midi import MidiEvent
    from app.nodes import Node, NodeGraph


@dataclass
class ActionContext:
    """
    Context object passed to actions at runtime.
    """

    workspace_id: str
    graph: "NodeGraph"


class BaseAction(Protocol):
    """
    Protocol that all action implementations must follow.
    """

    def handle_event(
        self,
        event: "MidiEvent",
        node: "Node",
        context: ActionContext,
    ) -> None:  # pragma: no cover - interface
        ...

