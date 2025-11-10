from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List


class NodePortDirection(Enum):
    INPUT = auto()
    OUTPUT = auto()


@dataclass
class NodePort:
    """
    Represents a single input or output port on a node.
    """

    name: str
    direction: NodePortDirection
    data_type: str = "any"


@dataclass
class Node:
    """
    Base class for node graph elements.
    """

    id: str
    type: str
    title: str
    inputs: List[NodePort] = field(default_factory=list)
    outputs: List[NodePort] = field(default_factory=list)
    config: Dict[str, object] = field(default_factory=dict)

