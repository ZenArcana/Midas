from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import mido
except ImportError:  # pragma: no cover - Optional dependency at runtime.
    mido = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MidiDevice:
    """
    Simple data class representing a MIDI input device.
    """

    name: str
    port: str
    is_virtual: bool = False
    sources: Tuple[str, ...] = field(default_factory=tuple)


class MidiDeviceManager:
    """
    Enumerate MIDI devices and provide helper utilities for discovery.
    """

    def __init__(self) -> None:
        self._virtual_devices: Dict[str, MidiDevice] = {}

    def list_input_devices(self, include_virtual: bool = True) -> List[MidiDevice]:
        devices: List[MidiDevice] = []

        if mido is not None:
            for name in mido.get_input_names():
                devices.append(MidiDevice(name=name, port=name, is_virtual=False))

        if include_virtual:
            devices.extend(self._virtual_devices.values())

        return devices

    def add_virtual_device(
        self,
        name: str,
        ports: Iterable[str],
        *,
        device_id: Optional[str] = None,
    ) -> Optional[MidiDevice]:
        sources = tuple(sorted(set(ports)))
        if not sources:
            return None
        device_id = device_id or f"virtual::{uuid.uuid4().hex}"
        device = MidiDevice(name=name, port=device_id, is_virtual=True, sources=sources)
        self._virtual_devices[device_id] = device
        return device

    def remove_virtual_device(self, device_id: str) -> None:
        self._virtual_devices.pop(device_id, None)

    def find_device(self, device_id: str) -> Optional[MidiDevice]:
        for device in self.list_input_devices(include_virtual=True):
            if device.port == device_id:
                return device
        return None

    def virtual_devices(self) -> List[MidiDevice]:
        return list(self._virtual_devices.values())

    def export_virtual_devices(self) -> List[Dict[str, object]]:
        return [
            {
                "id": device.port,
                "name": device.name,
                "sources": list(device.sources),
            }
            for device in self._virtual_devices.values()
        ]

    def import_virtual_devices(self, definitions: Iterable[Dict[str, object]]) -> None:
        self._virtual_devices.clear()
        for entry in definitions:
            name = entry.get("name")
            sources = entry.get("sources", [])
            device_id = entry.get("id")
            if not name or not sources:
                continue
            self.add_virtual_device(
                str(name),
                [str(port) for port in sources],
                device_id=str(device_id) if device_id else None,
            )


__all__ = ["MidiDevice", "MidiDeviceManager"]

