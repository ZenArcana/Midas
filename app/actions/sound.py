from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

from app.midi import MidiEvent
from app.nodes import Node

from .base import ActionContext, BaseAction

logger = logging.getLogger(__name__)


class _SoundPlayer:
    """
    Lightweight helper around common command-line audio players.
    """

    _BACKENDS = ("paplay", "aplay", "ffplay", "cvlc", "play")

    def __init__(self) -> None:
        self._backend = self._detect_backend()
        self._warned_missing_backend = False

    def _detect_backend(self) -> Optional[str]:
        for candidate in self._BACKENDS:
            if shutil.which(candidate):
                return candidate
        return None

    def play(self, file_path: Path) -> None:
        if self._backend is None:
            if not self._warned_missing_backend:
                logger.warning(
                    "Sound playback requested but no supported audio backend was detected. "
                    "Install paplay, aplay, ffplay, cvlc, or play."
                )
                self._warned_missing_backend = True
            return

        command = self._build_command(file_path)
        if not command:
            return

        try:
            subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception("Failed to play sound %s: %s", file_path, exc)

    def _build_command(self, file_path: Path) -> Optional[list[str]]:
        resolved = str(file_path)
        backend = self._backend
        if backend == "paplay":
            return ["paplay", resolved]
        if backend == "aplay":
            return ["aplay", resolved]
        if backend == "ffplay":
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", resolved]
        if backend == "cvlc":
            return ["cvlc", "--play-and-exit", "--intf", "dummy", resolved]
        if backend == "play":  # sox
            return ["play", "-q", resolved]
        logger.debug("Unsupported sound backend %s", backend)
        return None


class SoundAction(BaseAction):
    """
    Play an audio file when triggered by a MIDI event.
    """

    def __init__(self) -> None:
        self._player = _SoundPlayer()
        self._last_values: Dict[int, int] = {}

    def handle_event(self, event: MidiEvent, node: Node, context: ActionContext) -> None:
        path_config = node.config.get("file") or node.config.get("path")
        if not path_config:
            logger.debug("SoundAction for node %s has no file/path configured", node.id)
            return

        file_path = self._resolve_path(path_config)
        if file_path is None:
            logger.warning("SoundAction could not resolve path %s for node %s", path_config, node.id)
            return
        if not file_path.exists():
            logger.warning("SoundAction audio file %s does not exist", file_path)
            return

        if not self._should_trigger(event, node):
            return

        self._player.play(file_path)

    def _resolve_path(self, configured_path: object) -> Optional[Path]:
        try:
            path = Path(str(configured_path)).expanduser()
        except Exception:
            return None

        if path.is_absolute():
            return path

        try:
            return (Path.cwd() / path).resolve()
        except Exception:
            return None

    def _should_trigger(self, event: MidiEvent, node: Node) -> bool:
        trigger_value = self._safe_int(node.config.get("trigger_value"))
        min_value = self._safe_int(node.config.get("min_value"))

        if event.message_type == "control_change":
            control = event.control if event.control is not None else -1
            last_value = self._last_values.get(control)
            if last_value == event.value:
                return False
            if event.value is not None:
                self._last_values[control] = event.value
            value = event.value if event.value is not None else 0
            if trigger_value is not None and value != trigger_value:
                return False
            if min_value is not None and value < min_value:
                return False
            return True

        if event.message_type == "note_on":
            velocity = event.velocity if event.velocity is not None else 0
            if velocity <= 0:
                return False
            if trigger_value is not None and velocity != trigger_value:
                return False
            if min_value is not None and velocity < min_value:
                return False
            return True

        if event.message_type == "note_off":
            return bool(node.config.get("trigger_on_note_off", False))

        return False

    @staticmethod
    def _safe_int(value: object) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

