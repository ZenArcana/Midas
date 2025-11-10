from __future__ import annotations

import logging
import shutil
import subprocess

from app.midi import MidiEvent
from app.nodes import Node

from .base import ActionContext, BaseAction

logger = logging.getLogger(__name__)


class ShortcutAction(BaseAction):
    """
    Execute a keyboard shortcut using the `xdotool` utility.
    """

    def __init__(self) -> None:
        self._available = shutil.which("xdotool") is not None
        self._warned = False

    def handle_event(self, event: MidiEvent, node: Node, context: ActionContext) -> None:
        message_type = event.message_type
        if message_type == "note_off":
            return

        if message_type == "note_on":
            velocity = event.velocity if event.velocity is not None else event.value
            if velocity is not None and velocity <= 0:
                return

        if event.value is not None and event.value == 0:
            # ignore note_off or zero velocity events for buttons
            return

        sequence = str(node.config.get("sequence") or "").strip()
        if not sequence:
            if not self._warned:
                logger.warning("Shortcut node '%s' has no sequence configured.", node.title)
                self._warned = True
            return

        if not self._available:
            if not self._warned:
                logger.warning("xdotool is not installed; keyboard shortcut cannot be executed.")
                self._warned = True
            return

        command = ["xdotool", "key", sequence]
        try:
            subprocess.run(command, check=True)
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception("Failed to execute keyboard shortcut '%s': %s", sequence, exc)

