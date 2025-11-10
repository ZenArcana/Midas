from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.midi.manager import MidiDevice


class DevicePanel(QGroupBox):
    """
    Sidebar component that hosts MIDI device selection and status widgets.
    """

    refreshRequested = Signal()
    selectionChanged = Signal(object)  # list[MidiDevice]
    createVirtualRequested = Signal(str, object)  # name, list[str]
    removeVirtualRequested = Signal(str)  # device id

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("Devices", parent)
        self._devices: Dict[str, MidiDevice] = {}
        self._active_ports: set[str] = set()
        self._updating = False

        self._device_list = QListWidget()
        self._device_list.setSelectionMode(QListWidget.SingleSelection)
        self._device_list.itemChanged.connect(self._handle_item_change)
        self._device_list.currentItemChanged.connect(self._handle_current_change)

        self._refresh_button = QPushButton("Refresh")
        self._create_virtual_button = QPushButton("Create Virtual Source")
        self._remove_virtual_button = QPushButton("Remove Virtual Source")
        self._remove_virtual_button.setEnabled(False)

        self._status_label = QLabel("No devices active.")
        self._status_label.setWordWrap(True)
        self._status_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Available Inputs"))
        layout.addWidget(self._device_list, 3)
        layout.addWidget(self._refresh_button)
        layout.addWidget(self._create_virtual_button)
        layout.addWidget(self._remove_virtual_button)
        layout.addSpacing(12)
        layout.addWidget(self._status_label, 1)
        layout.addStretch()

        self._refresh_button.clicked.connect(self.refreshRequested.emit)
        self._create_virtual_button.clicked.connect(self._create_virtual_source)
        self._remove_virtual_button.clicked.connect(self._remove_virtual_source)

    def set_devices(self, devices: List[MidiDevice]) -> None:
        """
        Populate the list with available MIDI input devices.
        """

        active_before = set(self._active_ports)
        self._devices = {device.port: device for device in devices}

        self._updating = True
        self._device_list.clear()

        if not devices:
            placeholder = QListWidgetItem("No devices found")
            placeholder.setFlags(Qt.NoItemFlags)
            self._device_list.addItem(placeholder)
            self._device_list.setEnabled(False)
        else:
            self._device_list.setEnabled(True)
            for device in devices:
                item = QListWidgetItem(device.name)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                item.setData(Qt.UserRole, device.port)
                if device.is_virtual:
                    font = item.font()
                    font.setItalic(True)
                    item.setFont(font)
                    if device.sources:
                        item.setToolTip(f"Virtual source spanning: {', '.join(device.sources)}")
                item.setCheckState(Qt.Checked if device.port in active_before else Qt.Unchecked)
                self._device_list.addItem(item)

        self._updating = False
        self._active_ports = active_before & set(self._devices.keys())
        self._emit_selection_changed()
        self._update_status()
        self._update_buttons_state()

    def set_active_devices(self, devices: List[MidiDevice]) -> None:
        """
        Programmatically set the active devices and update the list check states.
        """

        ports = {device.port for device in devices}
        self._active_ports = ports

        self._updating = True
        for index in range(self._device_list.count()):
            item = self._device_list.item(index)
            port_id = item.data(Qt.UserRole)
            if not port_id:
                continue
            item.setCheckState(Qt.Checked if port_id in ports else Qt.Unchecked)
        self._updating = False

        self._update_status()
        self._update_buttons_state()

    def set_status(self, text: str) -> None:
        """
        Update the status label text.
        """

        self._status_label.setText(text)

    def selected_devices(self) -> List[MidiDevice]:
        """
        Return the list of currently checked devices.
        """

        devices: List[MidiDevice] = []
        for port_id in self._active_ports:
            device = self._devices.get(port_id)
            if device:
                devices.append(device)
        return devices

    def _handle_item_change(self, item: QListWidgetItem) -> None:
        if self._updating:
            return
        port_id = item.data(Qt.UserRole)
        if not port_id:
            return
        if item.checkState() == Qt.Checked:
            self._active_ports.add(port_id)
        else:
            self._active_ports.discard(port_id)
        self._emit_selection_changed()
        self._update_status()
        self._update_buttons_state()

    def _handle_current_change(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:  # type: ignore[override]
        _ = previous
        self._update_buttons_state()

    def _emit_selection_changed(self) -> None:
        self.selectionChanged.emit(self.selected_devices())

    def _create_virtual_source(self) -> None:
        physical_devices = [
            device for device in self.selected_devices() if not device.is_virtual
        ]
        if not physical_devices:
            self.set_status("Select at least one physical device to create a virtual source.")
            return

        default_name = " + ".join(device.name for device in physical_devices)
        name, ok = QInputDialog.getText(self, "Virtual Source", "Name:", text=default_name)
        if not ok or not name.strip():
            return

        ports = [device.port for device in physical_devices]
        self.createVirtualRequested.emit(name.strip(), ports)

    def _remove_virtual_source(self) -> None:
        current_item = self._device_list.currentItem()
        if current_item is None:
            return
        port_id = current_item.data(Qt.UserRole)
        if not port_id:
            return

        device = self._devices.get(port_id)
        if device and device.is_virtual:
            self.removeVirtualRequested.emit(port_id)

    def _update_status(self) -> None:
        if not self._active_ports:
            self._status_label.setText("No devices active.")
            return
        names = [self._devices[port].name for port in self._active_ports if port in self._devices]
        if names:
            self._status_label.setText(f"Active: {', '.join(names)}")
        else:
            self._status_label.setText("Active: (unknown devices)")

    def _update_buttons_state(self) -> None:
        current_item = self._device_list.currentItem()
        if current_item is None:
            self._remove_virtual_button.setEnabled(False)
            return
        port_id = current_item.data(Qt.UserRole)
        device = self._devices.get(port_id)
        self._remove_virtual_button.setEnabled(bool(device and device.is_virtual))

