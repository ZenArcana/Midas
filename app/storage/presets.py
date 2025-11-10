from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Tuple


@dataclass(frozen=True)
class WorkspacePreset:
    id: str
    name: str
    description: str
    payload: Dict[str, object]


_DEFAULT_PRESET = WorkspacePreset(
    id="default-mixer",
    name="Mixer Controller",
    description="Map a MIDI fader to system volume and trigger a brush-size command.",
    payload={
        "version": 1,
        "nodes": [
            {
                "id": "input_1",
                "type": "midi.input",
                "title": "MIDI Input",
                "config": {},
                "position": (-300, -60),
            },
            {
                "id": "mapper_1",
                "type": "logic.mapper",
                "title": "Brush Mapper",
                "config": {
                    "input_min": 0,
                    "input_max": 127,
                    "output_min": 0,
                    "output_max": 100,
                    "curve": "linear",
                },
                "position": (-20, -60),
            },
            {
                "id": "volume_action",
                "type": "action.volume",
                "title": "System Volume",
                "config": {
                    "input_min": 0,
                    "input_max": 127,
                    "output_min": 0.0,
                    "output_max": 1.0,
                },
                "position": (280, -140),
            },
            {
                "id": "command_action",
                "type": "action.command",
                "title": "Brush Size Script",
                "config": {
                    "command": "xdotool key shift+bracketright",
                    "shell": False,
                },
                "position": (280, 40),
            },
        ],
        "connections": [
            {
                "source_node": "input_1",
                "source_port": "message",
                "target_node": "mapper_1",
                "target_port": "in",
            },
            {
                "source_node": "mapper_1",
                "source_port": "out",
                "target_node": "volume_action",
                "target_port": "in",
            },
            {
                "source_node": "mapper_1",
                "source_port": "out",
                "target_node": "command_action",
                "target_port": "trigger",
            },
        ],
    },
)


def get_presets() -> Tuple[WorkspacePreset, ...]:
    return (_DEFAULT_PRESET,)

