from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable, List

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioTarget:
    """
    Represents an adjustable audio endpoint (device or application stream).
    """

    id: str
    name: str
    kind: str  # "default", "sink", "sink_input"


def _run_command(command: Iterable[str]) -> str:
    try:
        result = subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except Exception as exc:  # pragma: no cover - system-specific
        logger.debug("Command %s failed: %s", command, exc)
        return ""


def _list_wpctl_targets() -> List[AudioTarget]:
    output = _run_command(["wpctl", "status"])
    if not output:
        return []

    targets: List[AudioTarget] = [
        AudioTarget(id="@DEFAULT_AUDIO_SINK@", name="System Default Output", kind="default"),
        AudioTarget(id="@DEFAULT_AUDIO_SOURCE@", name="System Default Input", kind="default"),
    ]

    current_section = None
    sink_pattern = re.compile(r"\s*(\d+)\.\s+([^\[]+)")
    for line in output.splitlines():
        line = line.rstrip()
        if "Sinks:" in line:
            current_section = "sink"
            continue
        if "Sink inputs:" in line:
            current_section = "sink_input"
            continue
        if not line.startswith("│"):
            continue
        match = sink_pattern.search(line)
        if not match or current_section is None:
            continue
        identifier, name = match.groups()
        name = name.strip()
        target_id = identifier
        if current_section == "sink_input":
            target_id = identifier
        targets.append(AudioTarget(id=target_id, name=name, kind=current_section))
    return targets


def _list_pactl_targets() -> List[AudioTarget]:
    targets: List[AudioTarget] = [
        AudioTarget(id="@DEFAULT_SINK@", name="System Default Output", kind="default"),
        AudioTarget(id="@DEFAULT_SOURCE@", name="System Default Input", kind="default"),
    ]

    sinks_output = _run_command(["pactl", "list", "short", "sinks"])
    for line in sinks_output.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        identifier, name = parts[0], parts[1]
        targets.append(AudioTarget(id=identifier, name=name, kind="sink"))

    inputs_output = _run_command(["pactl", "list", "short", "sink-inputs"])
    for line in inputs_output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        identifier, name, owner = parts[0], parts[1], parts[2]
        display = f"{owner} ({name})"
        targets.append(AudioTarget(id=identifier, name=display, kind="sink_input"))

    return targets


def list_audio_targets() -> List[AudioTarget]:
    """
    Return available audio targets depending on the installed backend.
    """

    if shutil.which("wpctl"):
        targets = _list_wpctl_targets()
    elif shutil.which("pactl"):
        targets = _list_pactl_targets()
    else:
        targets = []

    # Ensure unique ids
    seen = set()
    deduped: List[AudioTarget] = []
    for target in targets:
        if target.id in seen:
            continue
        seen.add(target.id)
        deduped.append(target)
    return deduped


