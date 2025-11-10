from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence

from .base import Node, NodePort, NodePortDirection


@dataclass(frozen=True)
class NodeTemplate:
    """
    Describes how to instantiate a node for the editor.
    """

    type: str
    title: str
    category: str
    description: str
    input_ports: Sequence[tuple[str, str]] = field(default_factory=list)
    output_ports: Sequence[tuple[str, str]] = field(default_factory=list)
    default_config: Dict[str, object] = field(default_factory=dict)

    def instantiate(self, node_id: str) -> Node:
        return Node(
            id=node_id,
            type=self.type,
            title=self.title,
            inputs=[
                NodePort(name=name, direction=NodePortDirection.INPUT, data_type=data_type)
                for name, data_type in self.input_ports
            ],
            outputs=[
                NodePort(name=name, direction=NodePortDirection.OUTPUT, data_type=data_type)
                for name, data_type in self.output_ports
            ],
            config=dict(self.default_config),
        )


_TEMPLATES: List[NodeTemplate] = [
    NodeTemplate(
        type="midi.input",
        title="MIDI Input",
        category="Input",
        description="Starts a macro flow when MIDI messages arrive from a selected device.",
        input_ports=[],
        output_ports=[("message", "midi")],
    ),
    NodeTemplate(
        type="logic.mapper",
        title="Value Mapper",
        category="Processing",
        description="Transforms MIDI values (e.g. map CC ranges, scale velocities).",
        input_ports=[("in", "midi")],
        output_ports=[("out", "midi")],
        default_config={
            "input_min": 0,
            "input_max": 127,
            "output_min": 0,
            "output_max": 127,
            "curve": "linear",
        },
    ),
    NodeTemplate(
        type="action.volume",
        title="Volume Control",
        category="Action",
        description="Adjusts the system (PulseAudio/PipeWire) volume based on MIDI values.",
        input_ports=[("in", "midi")],
        output_ports=[],
        default_config={
            "input_min": 0,
            "input_max": 127,
            "output_min": 0.0,
            "output_max": 1.0,
            "sink": "",
        },
    ),
    NodeTemplate(
        type="action.script",
        title="Script Action",
        category="Action",
        description="Runs a custom Python snippet when triggered.",
        input_ports=[("trigger", "midi")],
        output_ports=[],
        default_config={"script": "# write Python code here\n"},
    ),
    NodeTemplate(
        type="action.command",
        title="Command Runner",
        category="Action",
        description="Executes shell commands or external applications.",
        input_ports=[("trigger", "midi")],
        output_ports=[],
        default_config={"command": "", "shell": False, "cwd": ""},
    ),
]

_TEMPLATE_MAP: Dict[str, NodeTemplate] = {template.type: template for template in _TEMPLATES}


def get_node_templates() -> Iterable[NodeTemplate]:
    """
    Return an iterable of all registered node templates.
    """

    return tuple(_TEMPLATES)


def get_node_template(node_type: str) -> NodeTemplate:
    """
    Look up a node template by its unique type identifier.
    """

    return _TEMPLATE_MAP[node_type]

