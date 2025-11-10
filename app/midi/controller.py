from __future__ import annotations

import logging
from typing import Dict, Iterable, Optional, Sequence

from PySide6.QtCore import QObject, Signal

from .events import MidiEvent
from .manager import MidiDevice

try:
    import mido
except ImportError:  # pragma: no cover - optional dependency.
    mido = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class MidiInputController(QObject):
    """
    Manage a single open MIDI input port and emit normalized events.
    """

    message_received = Signal(object)
    devices_changed = Signal(object)
    stopped = Signal()
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._input_ports: Dict[str, "mido.ports.BaseInput"] = {}
        self._active_devices: Dict[str, MidiDevice] = {}
        self._virtual_sources: Dict[str, Sequence[str]] = {}

    def set_active_devices(self, devices: Iterable[MidiDevice]) -> None:
        """
        Activate listening on the provided MIDI devices. Supports physical and
        virtual (aggregated) devices.
        """

        if mido is None:
            self.error.emit(
                "mido is not available. Install optional dependencies to enable MIDI."
            )
            return

        device_map = {device.port: device for device in devices}
        desired_ports = self._expand_physical_ports(device_map.values())

        self._virtual_sources = {
            device.port: device.sources
            for device in device_map.values()
            if device.is_virtual and device.sources
        }

        self._refresh_ports(desired_ports)
        self._active_devices = device_map
        self.devices_changed.emit(list(device_map.values()))

        if not desired_ports:
            self.stopped.emit()

    def stop(self) -> None:
        """
        Stop listening to the current MIDI port.
        """

        for port_name, input_port in list(self._input_ports.items()):
            try:
                input_port.close()
            finally:
                self._input_ports.pop(port_name, None)

        self._active_devices.clear()
        self._virtual_sources.clear()
        self.stopped.emit()
        self.devices_changed.emit([])

    def _refresh_ports(self, desired_ports: Sequence[str]) -> None:
        current_ports = set(self._input_ports.keys())
        desired_set = set(desired_ports)

        for port_name in current_ports - desired_set:
            try:
                self._input_ports[port_name].close()
            finally:
                self._input_ports.pop(port_name, None)

        for port_name in desired_set - current_ports:
            try:
                self._input_ports[port_name] = mido.open_input(
                    port_name, callback=lambda message, port=port_name: self._on_message(port, message)
                )
            except Exception as exc:  # pragma: no cover - runtime safeguard.
                logger.exception("Failed to open MIDI port %s", port_name)
                self.error.emit(f"Failed to open MIDI port '{port_name}': {exc}")
                self._input_ports.pop(port_name, None)

    def _expand_physical_ports(self, devices: Iterable[MidiDevice]) -> Sequence[str]:
        ports: set[str] = set()
        for device in devices:
            if device.is_virtual and device.sources:
                ports.update(device.sources)
            else:
                ports.add(device.port)
        return sorted(ports)

    def _on_message(self, port_name: str, message: "mido.Message") -> None:
        aliases = tuple(
            alias
            for alias, members in self._virtual_sources.items()
            if port_name in members
        )
        event = MidiEvent.from_message(message, source=port_name, aliases=aliases)
        self.message_received.emit(event)

