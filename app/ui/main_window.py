from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QAction, QActionGroup, QIcon, QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QWidget,
)

from app.actions import ActionEngine
from app.midi import (
    ControlProfileStore,
    MidiDevice,
    MidiDeviceManager,
    MidiEvent,
    MidiInputController,
)
from app.nodes import Node, NodeGraph
from app.storage import WorkspacePreset, WorkspaceStore, get_presets

from .device_panel import DevicePanel
from .node_editor import NodeEditorView
from .node_inspector import NodeInspector


logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Top-level window for the Midas application.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Midas")
        self.setMinimumSize(1024, 720)

        icon_path = Path(__file__).resolve().parents[2] / "Icon.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        app = QApplication.instance()
        self._default_palette: Optional[QPalette] = QPalette(app.palette()) if app else None
        self._default_style: Optional[str] = app.style().objectName() if app else None

        self._graph = NodeGraph()
        self._midi_manager = MidiDeviceManager()
        self._profile_store = ControlProfileStore()
        self._device_panel = DevicePanel()
        self._node_editor = NodeEditorView(self._graph)
        self._midi_controller = MidiInputController(self)
        self._action_engine = ActionEngine(self._graph, profile_store=self._profile_store)
        self._node_inspector = NodeInspector(self._profile_store, self._midi_manager)
        self._node_inspector.setMinimumWidth(260)
        self._workspace_store = WorkspaceStore()
        self._workspace_path: Optional[Path] = None
        self._last_workspace_dir: Path = Path.home()
        self._default_workspace_path: Path = Path.home() / ".config" / "midas" / "workspace.json"
        self._default_workspace_path.parent.mkdir(parents=True, exist_ok=True)
        self._status_bar = self.statusBar()
        self._status_bar.showMessage("Ready")

        self._theme: str = "light"
        self._theme_actions: Dict[str, QAction] = {}

        self._active_device_ids: Set[str] = set()
        self._suppress_selection_updates = False
        self._pending_learn: Optional[str] = None
        self._workspace_dirty = False

        self._setup_ui()
        self._setup_menus()
        self._setup_midi()

    def _setup_ui(self) -> None:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Horizontal, container)
        splitter.addWidget(self._device_panel)
        splitter.addWidget(self._node_editor)
        splitter.addWidget(self._node_inspector)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 2)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([280, 900, 340])

        layout.addWidget(splitter)
        self.setCentralWidget(container)

        self._node_editor.selectionChanged.connect(self._on_node_selection_changed)
        self._node_editor.connectionCreated.connect(lambda _c: self._mark_workspace_dirty())
        self._node_editor.connectionDeleted.connect(lambda _c: self._mark_workspace_dirty())
        self._node_inspector.learnRequested.connect(self._on_learn_requested)
        self._node_inspector.profileAssigned.connect(self._on_profile_assigned)
        self._node_inspector.deviceFilterChanged.connect(self._on_device_filter_changed)
        self._node_inspector.configChanged.connect(self._on_node_config_changed)

    def _setup_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File")

        open_action = QAction("&Open Workspace\u2026", self)
        open_action.triggered.connect(self._open_workspace)  # type: ignore[arg-type]
        file_menu.addAction(open_action)

        save_action = QAction("&Save Workspace", self)
        save_action.triggered.connect(self._save_workspace)  # type: ignore[arg-type]
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Workspace &As\u2026", self)
        save_as_action.triggered.connect(self._save_workspace_as)  # type: ignore[arg-type]
        file_menu.addAction(save_as_action)

        presets_menu = file_menu.addMenu("Load &Preset")
        for preset in get_presets():
            action = presets_menu.addAction(preset.name)
            action.setToolTip(preset.description)
            action.triggered.connect(
                lambda _checked=False, preset=preset: self._load_preset(preset)
            )

        file_menu.addSeparator()

        quit_action = QAction("&Quit", self)
        quit_action.triggered.connect(self.close)  # type: ignore[arg-type]
        file_menu.addAction(quit_action)

        nodes_menu = self.menuBar().addMenu("&Nodes")
        for template in self._node_editor.templates:
            action = nodes_menu.addAction(template.title)
            action.triggered.connect(
                lambda _checked=False, node_type=template.type: self._add_node(node_type)
            )
            action.setStatusTip(template.description)
        nodes_menu.addSeparator()
        delete_action = nodes_menu.addAction("Delete Selected Nodes")
        delete_action.triggered.connect(self._delete_selected_nodes)  # type: ignore[arg-type]

        view_menu = self.menuBar().addMenu("&View")
        theme_menu = view_menu.addMenu("&Theme")
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for theme_key, label in (("light", "Light"), ("dark", "Dark")):
            action = theme_menu.addAction(label)
            action.setCheckable(True)
            theme_group.addAction(action)
            action.triggered.connect(
                lambda checked, theme=theme_key: self._on_theme_action(theme, checked)
            )
            self._theme_actions[theme_key] = action
        self._update_theme_actions()

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about_dialog)  # type: ignore[arg-type]
        help_menu.addAction(about_action)

        quickstart_action = QAction("Quick &Start", self)
        quickstart_action.triggered.connect(self._show_quick_start)  # type: ignore[arg-type]
        help_menu.addAction(quickstart_action)

    def _setup_midi(self) -> None:
        self._device_panel.refreshRequested.connect(self._refresh_devices)
        self._device_panel.selectionChanged.connect(self._on_device_selection_changed)
        self._device_panel.createVirtualRequested.connect(self._create_virtual_source)
        self._device_panel.removeVirtualRequested.connect(self._remove_virtual_source)

        self._midi_controller.message_received.connect(self._handle_midi_event)
        self._midi_controller.devices_changed.connect(self._on_midi_devices_changed)
        self._midi_controller.error.connect(self._on_midi_error)
        self._midi_controller.stopped.connect(self._on_midi_stopped)

        self._load_initial_workspace()
        self._refresh_devices()

    def _open_workspace(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "Open Workspace",
            str(self._last_workspace_dir),
            "Workspace Files (*.json)",
        )
        if not file_name:
            return

        path = Path(file_name)
        try:
            payload = self._workspace_store.load(path)
        except Exception as exc:  # pragma: no cover - disk I/O
            QMessageBox.critical(self, "Failed to Open Workspace", str(exc))
            return

        info = self._workspace_store.import_workspace(
            self._graph,
            payload,
            profile_store=self._profile_store,
            midi_manager=self._midi_manager,
        )

        self._workspace_path = path
        self._last_workspace_dir = path.parent
        self._active_device_ids = {str(port) for port in info.get("active_devices", [])}
        self._workspace_dirty = False
        self._reload_graph()
        self._refresh_devices()
        self._status_bar.showMessage(f"Workspace loaded: {path.name}", 5000)

    def _save_workspace(self) -> None:
        target = self._workspace_path or self._default_workspace_path
        update_path = self._workspace_path is None
        if self._save_to_path(target, update_workspace_path=update_path):
            self._workspace_dirty = False

    def _save_workspace_as(self) -> None:
        file_name, _ = QFileDialog.getSaveFileName(
            self,
            "Save Workspace As",
            str(self._last_workspace_dir / "workspace.json"),
            "Workspace Files (*.json)",
        )
        if not file_name:
            return

        path = Path(file_name)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")

        if self._save_to_path(path, update_workspace_path=True):
            self._workspace_dirty = False

    def _show_about_dialog(self) -> None:
        QMessageBox.information(
            self,
            "About Midas",
            (
                "Midas\n\n"
                "Map your MIDI controller to powerful desktop automations "
                "through an intuitive node-based workflow."
            ),
        )

    def _on_theme_action(self, theme: str, checked: bool) -> None:
        if not checked:
            return
        self._set_theme(theme)

    def _set_theme(self, theme: str) -> None:
        if theme == self._theme:
            return
        self._theme = theme
        self._apply_theme(theme)
        self._update_theme_actions()
        self._status_bar.showMessage(f"{theme.capitalize()} theme applied.", 4000)

    def _update_theme_actions(self) -> None:
        for theme_key, action in self._theme_actions.items():
            action.setChecked(theme_key == self._theme)

    def _apply_theme(self, theme: str) -> None:
        app = QApplication.instance()
        if app is None:
            return

        if theme == "dark":
            app.setStyle("Fusion")
            app.setPalette(self._build_dark_palette())
        else:
            if self._default_style:
                app.setStyle(self._default_style)
            if self._default_palette is not None:
                app.setPalette(self._default_palette)
            else:
                app.setPalette(app.style().standardPalette())

    def _build_dark_palette(self) -> QPalette:
        palette = QPalette()
        base_color = QColor(37, 37, 38)
        alt_base_color = QColor(45, 45, 48)
        text_color = QColor(220, 220, 220)
        disabled_text = QColor(128, 128, 128)
        highlight_color = QColor(103, 153, 255)

        palette.setColor(QPalette.Window, alt_base_color)
        palette.setColor(QPalette.WindowText, text_color)
        palette.setColor(QPalette.Base, base_color)
        palette.setColor(QPalette.AlternateBase, alt_base_color)
        palette.setColor(QPalette.ToolTipBase, alt_base_color)
        palette.setColor(QPalette.ToolTipText, text_color)
        palette.setColor(QPalette.Text, text_color)
        palette.setColor(QPalette.Button, alt_base_color)
        palette.setColor(QPalette.ButtonText, text_color)
        palette.setColor(QPalette.BrightText, QColor(Qt.red))
        palette.setColor(QPalette.Link, QColor(140, 180, 255))
        palette.setColor(QPalette.Highlight, highlight_color)
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.PlaceholderText, QColor(180, 180, 180))

        palette.setColor(QPalette.Disabled, QPalette.Text, disabled_text)
        palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text)
        palette.setColor(QPalette.Disabled, QPalette.WindowText, disabled_text)
        palette.setColor(QPalette.Disabled, QPalette.HighlightedText, disabled_text)

        return palette

    def _show_quick_start(self) -> None:
        QMessageBox.information(
            self,
            "Midas Quick Start",
            (
                "1. Select your MIDI controller from the Devices panel.\n"
                "2. Right-click in the node canvas or use the Nodes menu to add nodes.\n"
                "3. Load the Mixer Controller preset from File → Load Preset for an example setup.\n"
                "4. Save your workspace once you configure your macros."
            ),
        )

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._auto_save_workspace()
        self._midi_controller.stop()
        super().closeEvent(event)

    @Slot()
    def _refresh_devices(self) -> None:
        devices = self._midi_manager.list_input_devices()
        self._suppress_selection_updates = True
        self._device_panel.set_devices(devices)

        selected_devices = [device for device in devices if device.port in self._active_device_ids]
        if not selected_devices and devices:
            default_device = next((device for device in devices if not device.is_virtual), devices[0])
            selected_devices = [default_device]

        self._device_panel.set_active_devices(selected_devices)
        self._suppress_selection_updates = False
        self._apply_device_selection(selected_devices, update_panel=False)
        self._node_inspector.refresh()

    @Slot(object)
    def _on_node_selection_changed(self, nodes: List[Node]) -> None:
        self._node_inspector.set_nodes(nodes)

    @Slot(str)
    def _on_learn_requested(self, node_id: str) -> None:
        self._pending_learn = node_id
        self._status_bar.showMessage("Learning control: move the desired knob, fader, or button…")
        self._device_panel.set_status("Learning… move the desired control.")

    @Slot(str, object)
    def _on_profile_assigned(self, node_id: str, profile_id: Optional[str]) -> None:
        node = self._graph.get_node(node_id)
        if node is None:
            return
        if profile_id:
            node.config["profile_id"] = str(profile_id)
            profile = self._profile_store.get(str(profile_id))
            if profile:
                node.config["control_type"] = profile.control_type
        else:
            node.config.pop("profile_id", None)
            node.config.pop("control_type", None)
        self._node_inspector.refresh()
        self._workspace_dirty = True

    @Slot(str, object)
    def _on_device_filter_changed(self, node_id: str, ports: List[str]) -> None:
        node = self._graph.get_node(node_id)
        if node is None:
            return
        if ports:
            node.config["device_ports"] = list(ports)
        else:
            node.config.pop("device_ports", None)
        self._node_inspector.refresh()
        self._workspace_dirty = True

    @Slot(str)
    def _on_node_config_changed(self, node_id: str) -> None:
        node = self._graph.get_node(node_id)
        if node is not None:
            self._node_editor.update_node(node)
        self._workspace_dirty = True

    def _apply_device_selection(self, devices: List[MidiDevice], update_panel: bool = True) -> None:
        self._active_device_ids = {device.port for device in devices}
        if update_panel:
            self._suppress_selection_updates = True
            self._device_panel.set_active_devices(devices)
            self._suppress_selection_updates = False

        if devices:
            self._device_panel.set_status(
                "Connecting to " + ", ".join(device.name for device in devices) + "…"
            )
        else:
            self._device_panel.set_status("No devices active.")

        self._midi_controller.set_active_devices(devices)

    @Slot(object)
    def _on_device_selection_changed(self, devices: List[MidiDevice]) -> None:
        if self._suppress_selection_updates:
            return
        self._apply_device_selection(devices, update_panel=False)
        self._workspace_dirty = True

    @Slot(str, object)
    def _create_virtual_source(self, name: str, ports: List[str]) -> None:
        device = self._midi_manager.add_virtual_device(name, ports)
        if device is None:
            QMessageBox.warning(self, "Virtual Source", "Unable to create virtual source.")
            return
        self._active_device_ids = {device.port}
        self._status_bar.showMessage(f"Virtual source '{device.name}' created.", 4000)
        self._refresh_devices()
        self._workspace_dirty = True

    def _remove_virtual_source(self, device_id: str) -> None:
        device = self._midi_manager.find_device(device_id)
        if device is None or not device.is_virtual:
            return
        self._midi_manager.remove_virtual_device(device_id)
        removed_name = device.name
        if device_id in self._active_device_ids:
            self._active_device_ids.discard(device_id)
        self._status_bar.showMessage(f"Virtual source '{removed_name}' removed.", 4000)
        self._refresh_devices()
        self._workspace_dirty = True

    @Slot(object)
    def _on_midi_devices_changed(self, devices: List[MidiDevice]) -> None:
        self._active_device_ids = {device.port for device in devices}
        self._suppress_selection_updates = True
        self._device_panel.set_active_devices(devices)
        self._suppress_selection_updates = False
        if devices:
            names = ", ".join(device.name for device in devices)
            self._device_panel.set_status(f"Listening on {names}")
        else:
            self._device_panel.set_status("No devices active.")

    @Slot()
    def _on_midi_stopped(self) -> None:
        self._device_panel.set_status("MIDI input stopped.")

    def _complete_learn(self, event: MidiEvent) -> None:
        node_id = self._pending_learn
        self._pending_learn = None
        if not node_id:
            return
        if event.source is None:
            QMessageBox.warning(self, "Learn Control", "Unable to learn control: event has no source device.")
            return
        node = self._graph.get_node(node_id)
        if node is None:
            return
        profile = self._profile_store.add_from_event(event)
        node.config["profile_id"] = profile.id
        node.config["device_ports"] = [event.source]
        node.config["control_type"] = profile.control_type
        self._status_bar.showMessage(f"Learned control: {profile.name}", 6000)
        self._device_panel.set_status(f"Learned control: {profile.name}")
        self._node_inspector.refresh()
        self._workspace_dirty = True

    @Slot(str)
    def _on_midi_error(self, message: str) -> None:
        QMessageBox.warning(self, "MIDI Error", message)

    @Slot(object)
    def _handle_midi_event(self, event: MidiEvent) -> None:
        if self._pending_learn:
            self._complete_learn(event)

        source_device = self._midi_manager.find_device(event.source) if event.source else None
        source_label = source_device.name if source_device else (event.source or "Unknown device")
        alias_names = [
            alias_device.name
            for alias in event.aliases
            if (alias_device := self._midi_manager.find_device(alias)) is not None
        ]
        if alias_names:
            source_label += f" ({', '.join(alias_names)})"
        self._device_panel.set_status(
            f"{source_label}: {event.message_type} value={event.value} note={event.note}"
        )
        self._status_bar.showMessage(
            f"Event: {event.message_type} value={event.value} note={event.note}", 2000
        )
        triggered_inputs = self._action_engine.handle_event(event)
        if triggered_inputs:
            self._update_midi_input_visuals(triggered_inputs, event)

    def _update_midi_input_visuals(self, nodes: Iterable[Node], event: MidiEvent) -> None:
        display_info = self._extract_event_display(event)
        if display_info is None:
            return

        value, active, raw = display_info
        for node in nodes:
            changed = False
            prev_value = node.config.get("_display_last_value")
            if prev_value is None or abs(float(prev_value) - value) > 1e-3:
                node.config["_display_last_value"] = value
                changed = True

            prev_active = bool(node.config.get("_display_last_active", False))
            if prev_active != active:
                node.config["_display_last_active"] = active
                changed = True

            if raw is not None:
                if node.config.get("_display_last_raw") != raw:
                    node.config["_display_last_raw"] = raw
                    changed = True
            elif "_display_last_raw" in node.config:
                node.config.pop("_display_last_raw", None)
                changed = True

            if changed:
                self._node_editor.update_node(node)

    def _extract_event_display(self, event: MidiEvent) -> Optional[tuple[float, bool, Optional[int]]]:
        message = event.message_type
        if message in {"note_on", "note_off"}:
            velocity = event.velocity if event.velocity is not None else event.value
            if velocity is None:
                velocity = 127 if message == "note_on" else 0
            try:
                raw_value = int(velocity)
            except (TypeError, ValueError):
                raw_value = 0
            raw_value = max(0, min(127, raw_value))
            active = message != "note_off" and raw_value > 0
            normalized = raw_value / 127.0 if raw_value else 0.0
            return normalized, active, raw_value

        if event.value is None:
            return None

        raw_value = event.value
        try:
            numeric = float(raw_value)
        except (TypeError, ValueError):
            return None

        if message == "pitchwheel":
            normalized = (numeric + 8192.0) / 16383.0
            raw_int: Optional[int] = int(round(numeric))
        else:
            normalized = numeric / 127.0
            raw_int = int(round(numeric))

        normalized = max(0.0, min(1.0, normalized))
        active = normalized > 0.001
        return normalized, active, raw_int

    def _add_node(self, node_type: str) -> None:
        node = self._node_editor.add_node(node_type)
        if node is not None:
            self._workspace_dirty = True

    def _delete_selected_nodes(self) -> None:
        self._node_editor.delete_selected_nodes()
        self._workspace_dirty = True

    def _reload_graph(self) -> None:
        self._node_editor.reload()
        self._action_engine = ActionEngine(self._graph, profile_store=self._profile_store)

    def _load_preset(self, preset: WorkspacePreset) -> None:
        info = self._workspace_store.import_workspace(
            self._graph,
            preset.payload,
            profile_store=self._profile_store,
            midi_manager=self._midi_manager,
        )
        self._workspace_path = None
        self._active_device_ids = {str(port) for port in info.get("active_devices", [])}
        self._workspace_dirty = True
        self._reload_graph()
        self._refresh_devices()
        self._status_bar.showMessage(f"Preset loaded: {preset.name}", 4000)

    def _load_initial_workspace(self) -> None:
        path = self._workspace_path or self._default_workspace_path
        if not path.exists():
            self._graph.clear()
            self._profile_store.clear()
            self._workspace_path = None
            self._workspace_dirty = False
            self._reload_graph()
            return

        try:
            payload = self._workspace_store.load(path)
        except Exception as exc:
            logger.warning("Failed to load workspace '%s': %s", path, exc)
            self._graph.clear()
            self._profile_store.clear()
            self._workspace_path = None
            self._workspace_dirty = False
            self._reload_graph()
            return

        info = self._workspace_store.import_workspace(
            self._graph,
            payload,
            profile_store=self._profile_store,
            midi_manager=self._midi_manager,
        )
        self._workspace_path = path
        self._last_workspace_dir = path.parent
        self._active_device_ids = {str(port) for port in info.get("active_devices", [])}
        self._workspace_dirty = False
        self._reload_graph()

    def _workspace_payload(self) -> Dict[str, object]:
        return self._workspace_store.export_workspace(
            self._graph,
            profiles=self._profile_store.serialize(),
            virtual_devices=self._midi_manager.export_virtual_devices(),
            active_devices=self._active_device_ids,
        )

    def _save_to_path(
        self,
        path: Path,
        *,
        update_workspace_path: bool,
        show_message: bool = True,
    ) -> bool:
        try:
            payload = self._workspace_payload()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._workspace_store.save(path, payload)
        except Exception as exc:  # pragma: no cover - disk I/O
            if show_message:
                QMessageBox.critical(self, "Failed to Save Workspace", str(exc))
            else:
                logger.exception("Auto-save failed: %s", exc)
            return False

        if update_workspace_path:
            self._workspace_path = path
            self._last_workspace_dir = path.parent

        if show_message:
            self._status_bar.showMessage(f"Workspace saved: {path.name}", 4000)

        return True

    def _auto_save_workspace(self) -> None:
        target = self._workspace_path or self._default_workspace_path
        update_path = self._workspace_path is None
        if self._save_to_path(target, update_workspace_path=update_path, show_message=False):
            self._workspace_dirty = False

    def _mark_workspace_dirty(self) -> None:
        self._workspace_dirty = True

