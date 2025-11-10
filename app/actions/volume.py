from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional

from app.midi import MidiEvent
from app.nodes import Node

from .base import ActionContext, BaseAction

logger = logging.getLogger(__name__)


class SystemVolumeController:
    """
    Wrapper over system utilities (wpctl / pactl) to adjust master or app volume.
    """

    def __init__(self) -> None:
        self._backend = self._detect_backend()
        self._warned = False

    def _detect_backend(self) -> Optional[str]:
        if shutil.which("wpctl"):
            return "wpctl"
        if shutil.which("pactl"):
            return "pactl"
        return None

    def set_level(self, level: float, target_id: Optional[str], target_kind: str) -> None:
        level = max(0.0, min(1.0, level))

        if self._backend is None:
            if not self._warned:
                logger.warning(
                    "No supported volume backend found. Install PipeWire (wpctl) or PulseAudio (pactl)."
                )
                self._warned = True
            return

        target_id = target_id or ("@DEFAULT_AUDIO_SINK@" if self._backend == "wpctl" else "@DEFAULT_SINK@")

        if self._backend == "wpctl":
            command = ["wpctl", "set-volume", target_id, f"{level:.3f}"]
        else:  # pactl
            percent = int(round(level * 100))
            if target_kind == "sink_input":
                command = ["pactl", "set-sink-input-volume", target_id, f"{percent}%"]
            else:
                command = ["pactl", "set-sink-volume", target_id, f"{percent}%"]

        try:
            subprocess.run(command, check=True)
        except Exception as exc:  # pragma: no cover - system-specific
            logger.exception("Failed to adjust system volume: %s", exc)


class VolumeAction(BaseAction):
    """
    Adjust PulseAudio/PipeWire volume using MIDI values.
    """

    def __init__(self) -> None:
        self._controller = SystemVolumeController()
        self._last_value: Optional[int] = None

    def handle_event(self, event: MidiEvent, node: Node, context: ActionContext) -> None:
        if event.value is None:
            return

        if self._last_value == event.value:
            return
        self._last_value = event.value

        input_min = int(node.config.get("input_min", 0))
        input_max = int(node.config.get("input_max", 127))
        output_min = float(node.config.get("output_min", 0.0))
        output_max = float(node.config.get("output_max", 1.0))

        target_id = node.config.get("target_id")
        target_kind = str(node.config.get("target_kind") or "default")

        normalized = (event.value - input_min) / max(1, (input_max - input_min))
        normalized = max(0.0, min(1.0, normalized))
        level = output_min + normalized * (output_max - output_min)
        self._controller.set_level(level, target_id=str(target_id) if target_id else None, target_kind=target_kind)

