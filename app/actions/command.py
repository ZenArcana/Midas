from __future__ import annotations

import logging
import os
import shlex
import subprocess
from typing import Dict, Iterable, List, Optional, Sequence

from app.midi import MidiEvent
from app.nodes import Node

from .base import ActionContext, BaseAction

logger = logging.getLogger(__name__)


def _ensure_sequence(command: object) -> Optional[Sequence[str]]:
    if command is None:
        return None
    if isinstance(command, (list, tuple)):
        return [str(part) for part in command]
    if isinstance(command, str):
        return shlex.split(command)
    return None


class CommandAction(BaseAction):
    """
    Execute external commands in response to MIDI events.
    """

    def __init__(self) -> None:
        self._last_values: Dict[int, int] = {}

    def handle_event(self, event: MidiEvent, node: Node, context: ActionContext) -> None:
        command_config = node.config.get("command")
        args_config = node.config.get("args")
        working_dir = node.config.get("cwd")
        shell = bool(node.config.get("shell", False))

        if command_config is None and args_config is None:
            return

        if event.message_type == "control_change":
            control = event.control if event.control is not None else -1
            last_value = self._last_values.get(control)
            if last_value == event.value:
                return
            if event.value is not None:
                self._last_values[control] = event.value
        elif event.message_type == "note_on":
            if (event.velocity or 0) == 0:
                return

        env = os.environ.copy()
        env.update(
            {
                "MIDI_VALUE": str(event.value if event.value is not None else ""),
                "MIDI_CONTROL": str(event.control if event.control is not None else ""),
                "MIDI_NOTE": str(event.note if event.note is not None else ""),
                "MIDI_CHANNEL": str(event.channel if event.channel is not None else ""),
                "MIDI_TYPE": event.message_type,
                "MIDAS_WORKSPACE_ID": context.workspace_id,
            }
        )

        cwd = str(working_dir) if isinstance(working_dir, str) and working_dir else None

        try:
            if shell:
                command_str = str(command_config or "")
                if not command_str:
                    return
                subprocess.Popen(command_str, shell=True, cwd=cwd, env=env)
            else:
                base_command = _ensure_sequence(args_config) or _ensure_sequence(command_config)
                if not base_command:
                    return
                subprocess.Popen(list(base_command), cwd=cwd, env=env)
        except Exception as exc:  # pragma: no cover - subprocess
            logger.exception("Failed to execute command for node %s: %s", node.id, exc)

