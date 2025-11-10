from __future__ import annotations

import logging
from types import MappingProxyType
from typing import Dict

from app.midi import MidiEvent
from app.nodes import Node

from .base import ActionContext, BaseAction

logger = logging.getLogger(__name__)

SAFE_BUILTINS = MappingProxyType(
    {
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "int": int,
        "float": float,
        "str": str,
        "print": print,
        "bool": bool,
        "len": len,
        "list": list,
        "dict": dict,
        "set": set,
        "sorted": sorted,
        "getattr": getattr,
        "__import__": __import__,
    }
)


class ScriptAction(BaseAction):
    """
    Execute user-authored Python snippets on incoming MIDI events.
    """

    def handle_event(self, event: MidiEvent, node: Node, context: ActionContext) -> None:
        script = node.config.get("script")
        if not isinstance(script, str) or not script.strip():
            return

        globals_dict: Dict[str, object] = {
            "__builtins__": SAFE_BUILTINS,
            "event": event,
            "node": node,
            "context": context,
        }
        locals_dict: Dict[str, object] = {}

        try:
            exec(script, globals_dict, locals_dict)
        except Exception as exc:  # pragma: no cover - user supplied code
            logger.exception("Script action failed for node %s: %s", node.id, exc)

