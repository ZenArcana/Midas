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

    _BACKENDS = ("ffplay", "paplay", "cvlc", "play", "aplay")

    def __init__(self) -> None:
        self._available_backends = self._detect_backends()
        self._backend = self._available_backends[0] if self._available_backends else None
        self._warned_missing_backend = False
        self._unsupported_volume_backends: set[str] = set()

    def _detect_backends(self) -> list[str]:
        return [candidate for candidate in self._BACKENDS if shutil.which(candidate)]

    def play(self, file_path: Path, volume: Optional[float] = None) -> None:
        if self._backend is None:
            if not self._warned_missing_backend:
                logger.warning(
                    "Sound playback requested but no supported audio backend was detected. "
                    "Install paplay, aplay, ffplay, cvlc, or play."
                )
                self._warned_missing_backend = True
            return

        command_spec = self._build_command(file_path, volume)
        if not command_spec:
            return

        try:
            if isinstance(command_spec, tuple) and command_spec and command_spec[0] == "pipeline":
                _, producer_cmd, consumer_cmd = command_spec
                producer = subprocess.Popen(
                    producer_cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
                consumer = subprocess.Popen(
                    consumer_cmd,
                    stdin=producer.stdout,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                if producer.stdout is not None:
                    producer.stdout.close()
            else:
                subprocess.Popen(
                    command_spec,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception as exc:  # pragma: no cover - runtime safeguard
            logger.exception("Failed to play sound %s: %s", file_path, exc)

    def _build_command(self, file_path: Path, volume: Optional[float]):
        resolved = str(file_path)
        backend = self._backend
        normalized_volume = None
        if volume is not None:
            normalized_volume = max(0.0, min(1.0, float(volume)))

        if normalized_volume is not None and backend is not None and not self._supports_volume(backend):
            fallback = self._find_volume_capable_backend()
            if fallback:
                logger.debug("Switching sound backend from %s to %s to support volume control.", backend, fallback)
                backend = fallback
                self._backend = fallback
            else:
                self._warn_volume_unsupported(backend)

        if backend == "paplay":
            command = ["paplay"]
            if normalized_volume is not None:
                pulse_volume = max(0, min(0x10000, int(round(normalized_volume * 0x10000))))
                command.append(f"--volume={pulse_volume}")
            command.append(resolved)
            return command
        if backend == "ffplay":
            command = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error"]
            if normalized_volume is not None:
                command.extend(["-af", f"volume={normalized_volume:.4f}"])
            command.append(resolved)
            return command
        if backend == "aplay":
            if normalized_volume is not None and abs(normalized_volume - 1.0) > 1e-6:
                pipeline = self._build_volume_pipeline(resolved, normalized_volume)
                if pipeline:
                    return pipeline
                self._warn_volume_unsupported(backend)
            return ["aplay", resolved]
        if backend == "cvlc":
            command = ["cvlc", "--play-and-exit", "--intf", "dummy"]
            if normalized_volume is not None:
                vlc_gain = max(0.0, min(8.0, normalized_volume))
                command.extend(["--gain", f"{vlc_gain:.3f}"])
            command.append(resolved)
            return command
        if backend == "play":  # sox
            command = ["play", "-q"]
            if normalized_volume is not None:
                command.extend(["-v", f"{normalized_volume:.3f}"])
            command.append(resolved)
            return command
        logger.debug("Unsupported sound backend %s", backend)
        return None

    def _supports_volume(self, backend: Optional[str]) -> bool:
        return backend in {"paplay", "ffplay", "cvlc", "play"}

    def _find_volume_capable_backend(self) -> Optional[str]:
        for candidate in self._available_backends:
            if self._supports_volume(candidate):
                return candidate
        return None

    def _build_volume_pipeline(self, resolved: str, normalized_volume: float):
        producer: Optional[list[str]] = None
        if shutil.which("ffmpeg"):
            producer = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                resolved,
                "-filter:a",
                f"volume={normalized_volume:.4f}",
                "-f",
                "wav",
                "pipe:1",
            ]
        elif shutil.which("sox"):
            producer = [
                "sox",
                "-q",
                resolved,
                "-t",
                "wav",
                "-",
                "vol",
                f"{normalized_volume:.3f}",
            ]

        if producer is None:
            return None

        consumer = ["aplay", "-q", "-"]
        return ("pipeline", producer, consumer)

    def _warn_volume_unsupported(self, backend: str) -> None:
        if backend in self._unsupported_volume_backends:
            return
        logger.warning("Volume control is not supported for backend '%s'; ignoring configured volume.", backend)
        self._unsupported_volume_backends.add(backend)


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

        volume = self._safe_float(node.config.get("volume"))
        if volume is not None:
            volume = max(0.0, min(1.0, volume))
            if abs(volume - 1.0) <= 1e-6:
                volume = None

        self._player.play(file_path, volume)

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

    @staticmethod
    def _safe_float(value: object) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

