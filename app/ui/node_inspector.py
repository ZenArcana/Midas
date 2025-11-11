from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFileDialog,
    QPlainTextEdit,
    QPushButton,
    QFrame,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.midi import ControlProfileStore, MidiDeviceManager
from app.nodes import Node
from app.system import list_audio_targets


class NodeInspector(QGroupBox):
    """
    Simple inspector panel that exposes configuration for the selected node.
    """

    learnRequested = Signal(str)
    profileAssigned = Signal(str, object)  # node_id, profile_id | None
    deviceFilterChanged = Signal(str, object)  # node_id, list[str]
    configChanged = Signal(str)  # node_id

    def __init__(
        self,
        profile_store: ControlProfileStore,
        midi_manager: MidiDeviceManager,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__("Inspector", parent)
        self._profile_store = profile_store
        self._midi_manager = midi_manager
        self._current_nodes: List[Node] = []
        self._is_updating = False

        self._control_type_combo: Optional[QComboBox] = None
        self._control_type_custom_edit: Optional[QLineEdit] = None

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        self._content_widget = QWidget(self._scroll_area)
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_widget.setLayout(self._content_layout)
        self._scroll_area.setWidget(self._content_widget)

        root_layout = QVBoxLayout()
        root_layout.setContentsMargins(8, 8, 8, 8)
        root_layout.addWidget(self._scroll_area)
        self.setLayout(root_layout)

        self._learn_button: Optional[QPushButton] = None
        self._profile_combo: Optional[QComboBox] = None
        self._device_combo: Optional[QComboBox] = None
        self._profile_label: Optional[QLabel] = None
        self._volume_target_combo: Optional[QComboBox] = None
        self._volume_targets = []
        self._volume_refresh_button: Optional[QPushButton] = None
        self._command_command_edit: Optional[QLineEdit] = None
        self._command_args_edit: Optional[QLineEdit] = None
        self._command_cwd_edit: Optional[QLineEdit] = None
        self._command_shell_checkbox: Optional[QCheckBox] = None
        self._script_edit: Optional[QPlainTextEdit] = None
        self._mapper_inputs: Optional[tuple[QSpinBox, QSpinBox]] = None
        self._mapper_outputs: Optional[tuple[QDoubleSpinBox, QDoubleSpinBox]] = None
        self._mapper_curve_combo: Optional[QComboBox] = None
        self._mapper_steps_spin: Optional[QSpinBox] = None

        self.refresh()

    def set_nodes(self, nodes: List[Node]) -> None:
        self._current_nodes = nodes
        self.refresh()

    def set_profile_store(self, store: ControlProfileStore) -> None:
        self._profile_store = store
        self.refresh()

    def set_midi_manager(self, manager: MidiDeviceManager) -> None:
        self._midi_manager = manager
        self.refresh()

    def refresh(self) -> None:
        self._clear_content()

        if not self._current_nodes:
            self._content_layout.addWidget(QLabel("Select a node to edit its properties."))
            return

        if len(self._current_nodes) > 1:
            self._content_layout.addWidget(QLabel("Multiple nodes selected."))
            return

        node = self._current_nodes[0]
        header = QLabel(f"{node.title} ({node.type})")
        header.setWordWrap(True)
        header.setStyleSheet("font-weight: bold;")
        self._content_layout.addWidget(header)

        description = node.config.get("_description")
        if isinstance(description, str) and description.strip():
            desc_label = QLabel(description.strip())
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: palette(mid);")
            self._content_layout.addWidget(desc_label)

        if node.type == "midi.input":
            self._build_midi_input_editor(node)
        else:
            if node.type == "logic.mapper":
                self._build_mapper_editor(node)
            elif node.type == "action.volume":
                self._build_volume_editor(node)
            elif node.type == "action.command":
                self._build_command_editor(node)
            elif node.type == "action.script":
                self._build_script_editor(node)
            elif node.type == "action.shortcut":
                self._build_shortcut_editor(node)
            elif node.type == "action.sound":
                self._build_sound_editor(node)
            else:
                self._content_layout.addWidget(QLabel("No editable properties for this node."))

        self._content_layout.addStretch()

    def _build_midi_input_editor(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        self._device_combo = QComboBox()
        self._device_combo.addItem("Any device", "")

        for device in self._midi_manager.list_input_devices():
            label = device.name
            if device.is_virtual:
                label += " (virtual)"
            self._device_combo.addItem(label, device.port)

        device_ports = node.config.get("device_ports") or []
        selected_port = device_ports[0] if device_ports else ""
        index = self._device_combo.findData(selected_port)
        if index == -1:
            index = 0
        self._is_updating = True
        self._device_combo.setCurrentIndex(index)
        self._is_updating = False
        self._device_combo.currentIndexChanged.connect(self._handle_device_changed)
        form.addRow("Device filter", self._device_combo)

        profile_id = node.config.get("profile_id")
        profile = self._profile_store.get(profile_id) if profile_id else None
        profile_text = profile.name if profile else "No control learned."
        if profile and profile.control_type:
            profile_text += f" ({profile.control_type})"
        self._profile_label = QLabel(profile_text)
        self._profile_label.setWordWrap(True)
        form.addRow("Assigned control", self._profile_label)

        learn_row = QWidget()
        learn_layout = QVBoxLayout()
        learn_layout.setContentsMargins(0, 0, 0, 0)
        learn_row.setLayout(learn_layout)

        self._learn_button = QPushButton("Learn Control")
        self._learn_button.clicked.connect(self._on_learn_clicked)
        learn_layout.addWidget(self._learn_button)

        clear_button = QPushButton("Clear Profile")
        clear_button.clicked.connect(self._on_clear_profile)
        learn_layout.addWidget(clear_button)

        form.addRow("", learn_row)

        form.addRow(self._create_control_type_editor(node))

    def _build_trigger_filter_section(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        self._profile_combo = QComboBox()
        self._profile_combo.addItem("Any control", None)

        for profile in self._profile_store.profiles():
            device_suffix = f" - {profile.device_port}"
            text = f"{profile.name}{device_suffix}"
            self._profile_combo.addItem(text, profile.id)

        current_profile_id = node.config.get("profile_id")
        index = self._profile_combo.findData(current_profile_id)
        self._is_updating = True
        if index != -1:
            self._profile_combo.setCurrentIndex(index)
        else:
            self._profile_combo.setCurrentIndex(0)
        self._is_updating = False

        self._profile_combo.currentIndexChanged.connect(self._handle_profile_changed)
        form.addRow("Trigger profile", self._profile_combo)

    def _build_mapper_editor(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        input_min = int(node.config.get("input_min", 0))
        input_max = int(node.config.get("input_max", 127))
        output_min = float(node.config.get("output_min", 0.0))
        output_max = float(node.config.get("output_max", 1.0))
        curve = str(node.config.get("curve", "linear"))
        steps = int(node.config.get("steps", 8))

        in_min_spin = QSpinBox()
        in_min_spin.setRange(0, 127)
        in_min_spin.setValue(input_min)
        in_max_spin = QSpinBox()
        in_max_spin.setRange(0, 127)
        in_max_spin.setValue(input_max)
        out_min_spin = QDoubleSpinBox()
        out_min_spin.setRange(0.0, 1.0)
        out_min_spin.setSingleStep(0.01)
        out_min_spin.setValue(output_min)
        out_max_spin = QDoubleSpinBox()
        out_max_spin.setRange(0.0, 1.0)
        out_max_spin.setSingleStep(0.01)
        out_max_spin.setValue(output_max)

        curve_combo = QComboBox()
        curve_combo.addItems(["linear", "log", "exp", "step"])
        index = curve_combo.findText(curve)
        if index != -1:
            curve_combo.setCurrentIndex(index)

        steps_spin = QSpinBox()
        steps_spin.setRange(2, 128)
        steps_spin.setValue(max(2, steps))
        steps_spin.setEnabled(curve == "step")

        form.addRow("Input min", in_min_spin)
        form.addRow("Input max", in_max_spin)
        form.addRow("Output min", out_min_spin)
        form.addRow("Output max", out_max_spin)
        form.addRow("Curve", curve_combo)
        form.addRow("Steps", steps_spin)

        self._mapper_inputs = (in_min_spin, in_max_spin)
        self._mapper_outputs = (out_min_spin, out_max_spin)
        self._mapper_curve_combo = curve_combo
        self._mapper_steps_spin = steps_spin

        in_min_spin.valueChanged.connect(lambda value: self._set_config_value(node, "input_min", int(value)))
        in_max_spin.valueChanged.connect(lambda value: self._set_config_value(node, "input_max", int(value)))
        out_min_spin.valueChanged.connect(lambda value: self._set_config_value(node, "output_min", float(value)))
        out_max_spin.valueChanged.connect(lambda value: self._set_config_value(node, "output_max", float(value)))

        def on_curve_changed(index: int) -> None:
            if self._is_updating:
                return
            value = curve_combo.itemText(index)
            steps_spin.setEnabled(value == "step")
            self._set_config_value(node, "curve", value)

        curve_combo.currentIndexChanged.connect(on_curve_changed)
        steps_spin.valueChanged.connect(lambda value: self._set_config_value(node, "steps", int(value)))

    def _build_volume_editor(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        self._volume_target_combo = QComboBox()
        self._volume_refresh_button = QPushButton("Refresh Targets")
        target_row = QHBoxLayout()
        target_row.addWidget(self._volume_target_combo)
        target_row.addWidget(self._volume_refresh_button)
        form.addRow("Audio target", target_row)

        self._populate_volume_targets(node)
        self._volume_target_combo.currentIndexChanged.connect(lambda _: self._handle_volume_target_changed(node))
        self._volume_refresh_button.clicked.connect(lambda: self._populate_volume_targets(node))

        input_min = QSpinBox()
        input_min.setRange(0, 127)
        input_min.setValue(int(node.config.get("input_min", 0)))
        input_max = QSpinBox()
        input_max.setRange(0, 127)
        input_max.setValue(int(node.config.get("input_max", 127)))
        output_min = QDoubleSpinBox()
        output_min.setRange(0.0, 1.0)
        output_min.setSingleStep(0.01)
        output_min.setValue(float(node.config.get("output_min", 0.0)))
        output_max = QDoubleSpinBox()
        output_max.setRange(0.0, 1.0)
        output_max.setSingleStep(0.01)
        output_max.setValue(float(node.config.get("output_max", 1.0)))

        form.addRow("Input min", input_min)
        form.addRow("Input max", input_max)
        form.addRow("Output min", output_min)
        form.addRow("Output max", output_max)

        input_min.valueChanged.connect(lambda value: self._set_config_value(node, "input_min", int(value)))
        input_max.valueChanged.connect(lambda value: self._set_config_value(node, "input_max", int(value)))
        output_min.valueChanged.connect(lambda value: self._set_config_value(node, "output_min", float(value)))
        output_max.valueChanged.connect(lambda value: self._set_config_value(node, "output_max", float(value)))

        self._build_trigger_filter_section(node)

    def _populate_volume_targets(self, node: Node) -> None:
        if self._volume_target_combo is None:
            return
        self._is_updating = True
        self._volume_target_combo.clear()
        self._volume_targets = list_audio_targets()
        if not self._volume_targets:
            self._volume_target_combo.addItem("System Default Output", ("@DEFAULT", "default"))
            selected_id = str(node.config.get("target_id") or "@DEFAULT_AUDIO_SINK@")
            if selected_id.startswith("@DEFAULT"):
                self._volume_target_combo.setCurrentIndex(0)
            self._is_updating = False
            return

        selected_id = str(node.config.get("target_id") or "")
        selected_kind = str(node.config.get("target_kind") or "")
        best_index = 0
        for target in self._volume_targets:
            label = f"{target.name} ({target.kind})"
            self._volume_target_combo.addItem(label, (target.id, target.kind))
            if target.id == selected_id or (not selected_id and target.kind == "default"):
                best_index = self._volume_target_combo.count() - 1
        self._volume_target_combo.setCurrentIndex(best_index)
        self._is_updating = False

    def _handle_volume_target_changed(self, node: Node) -> None:
        if self._is_updating or self._volume_target_combo is None:
            return
        data = self._volume_target_combo.currentData()
        if isinstance(data, tuple) and len(data) == 2:
            target_id, target_kind = data
            self._set_config_value(node, "target_id", target_id)
            self._set_config_value(node, "target_kind", target_kind)

    def _build_command_editor(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        command_edit = QLineEdit()
        command_edit.setPlaceholderText("e.g. /usr/bin/xdotool")
        current_command = node.config.get("command", "")
        if isinstance(current_command, (list, tuple)):
            current_command = " ".join(str(part) for part in current_command)
        command_edit.setText(str(current_command or ""))

        args_edit = QLineEdit()
        args_edit.setPlaceholderText("Arguments (optional)")
        args = node.config.get("args")
        if isinstance(args, (list, tuple)):
            args_edit.setText(" ".join(str(part) for part in args))
        elif isinstance(args, str):
            args_edit.setText(args)

        cwd_edit = QLineEdit()
        cwd_edit.setPlaceholderText("Working directory (optional)")
        cwd_edit.setText(str(node.config.get("cwd") or ""))

        shell_checkbox = QCheckBox("Run in shell")
        shell_checkbox.setChecked(bool(node.config.get("shell")))

        form.addRow("Command", command_edit)
        form.addRow("Arguments", args_edit)
        form.addRow("Working dir", cwd_edit)
        form.addRow("", shell_checkbox)

        self._command_command_edit = command_edit
        self._command_args_edit = args_edit
        self._command_cwd_edit = cwd_edit
        self._command_shell_checkbox = shell_checkbox

        command_edit.editingFinished.connect(lambda: self._update_command_config(node))
        args_edit.editingFinished.connect(lambda: self._update_command_config(node))
        cwd_edit.editingFinished.connect(lambda: self._update_command_config(node))
        shell_checkbox.toggled.connect(lambda _: self._update_command_config(node))

        self._build_trigger_filter_section(node)

    def _update_command_config(self, node: Node) -> None:
        if self._is_updating:
            return
        command = ""
        args_value = []
        cwd_value = ""
        shell_value = False
        if self._command_command_edit is not None:
            command = self._command_command_edit.text().strip()
        if self._command_args_edit is not None:
            raw_args = self._command_args_edit.text().strip()
            if raw_args:
                import shlex

                try:
                    args_value = shlex.split(raw_args)
                except ValueError:
                    args_value = raw_args.split()
            else:
                args_value = []
        if self._command_cwd_edit is not None:
            cwd_value = self._command_cwd_edit.text().strip()
        if self._command_shell_checkbox is not None:
            shell_value = self._command_shell_checkbox.isChecked()

        self._set_config_value(node, "command", command)
        self._set_config_value(node, "args", args_value)
        self._set_config_value(node, "cwd", cwd_value)
        self._set_config_value(node, "shell", shell_value)

    def _build_script_editor(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        script_edit = QPlainTextEdit()
        script_edit.setPlaceholderText("# Write Python code here\n")
        script_edit.setPlainText(str(node.config.get("script") or ""))
        script_edit.textChanged.connect(lambda: self._handle_script_changed(node))
        form.addRow("Script", script_edit)

        self._script_edit = script_edit

        note = QLabel("The script executes with variables: event, node, context.")
        note.setWordWrap(True)
        note.setStyleSheet("color: palette(mid);")
        form.addRow("", note)

        self._build_trigger_filter_section(node)

    def _handle_script_changed(self, node: Node) -> None:
        if self._is_updating or self._script_edit is None:
            return
        self._set_config_value(node, "script", self._script_edit.toPlainText())

    def _build_shortcut_editor(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        sequence_edit = QLineEdit()
        sequence_edit.setPlaceholderText("ctrl+alt+k")
        sequence_edit.setText(str(node.config.get("sequence") or ""))
        sequence_edit.editingFinished.connect(
            lambda: self._set_config_value(node, "sequence", sequence_edit.text().strip())
        )
        form.addRow("Shortcut sequence", sequence_edit)

        hint = QLabel("Shortcut is passed to xdotool's `key` command (install xdotool).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid);")
        form.addRow("", hint)

        self._build_trigger_filter_section(node)

    def _build_sound_editor(self, node: Node) -> None:
        form = QFormLayout()
        container = QWidget(self)
        container.setLayout(form)
        self._content_layout.addWidget(container)

        path_row = QHBoxLayout()
        path_edit = QLineEdit()
        path_edit.setPlaceholderText("/path/to/sample.wav")
        current_path = str(node.config.get("file") or node.config.get("path") or "")
        path_edit.setText(current_path)

        browse_button = QPushButton("Browse…")
        browse_button.clicked.connect(lambda: self._handle_sound_browse(node, path_edit))

        path_edit.editingFinished.connect(lambda: self._handle_sound_path_changed(node, path_edit))

        path_row.addWidget(path_edit)
        path_row.addWidget(browse_button)
        form.addRow("Audio file", path_row)

        volume_spin = QDoubleSpinBox()
        volume_spin.setRange(0.0, 1.0)
        volume_spin.setSingleStep(0.05)
        volume_spin.setDecimals(2)
        try:
            current_volume = float(node.config.get("volume", 1.0))
        except (TypeError, ValueError):
            current_volume = 1.0
        volume_spin.setValue(max(0.0, min(1.0, current_volume)))
        volume_spin.valueChanged.connect(lambda value: self._set_config_value(node, "volume", float(value)))
        form.addRow("Volume", volume_spin)

        trigger_spin = QSpinBox()
        trigger_spin.setRange(-1, 127)
        trigger_spin.setSpecialValueText("Any value")
        trigger_value = node.config.get("trigger_value")
        trigger_spin.setValue(int(trigger_value) if trigger_value is not None else -1)
        trigger_spin.valueChanged.connect(
            lambda value: self._set_optional_int_config(node, "trigger_value", value)
        )
        form.addRow("Trigger value", trigger_spin)

        min_spin = QSpinBox()
        min_spin.setRange(-1, 127)
        min_spin.setSpecialValueText("Disabled")
        min_value = node.config.get("min_value")
        min_spin.setValue(int(min_value) if min_value is not None else -1)
        min_spin.valueChanged.connect(
            lambda value: self._set_optional_int_config(node, "min_value", value)
        )
        form.addRow("Minimum value", min_spin)

        note_off_checkbox = QCheckBox("Trigger on note-off messages")
        note_off_checkbox.setChecked(bool(node.config.get("trigger_on_note_off")))
        note_off_checkbox.toggled.connect(
            lambda checked: self._set_config_value(node, "trigger_on_note_off", bool(checked))
        )
        form.addRow("", note_off_checkbox)

        info_label = QLabel(
            "Leaves trigger/min filters optional. Control profile filters from the section below."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: palette(mid);")
        form.addRow("", info_label)

        self._build_trigger_filter_section(node)

    def _handle_sound_path_changed(self, node: Node, edit: QLineEdit) -> None:
        if self._is_updating:
            return
        value = edit.text().strip()
        if not value:
            if "file" in node.config:
                node.config["file"] = ""
                self._emit_config_changed(node.id)
            if "path" in node.config:
                node.config["path"] = ""
                self._emit_config_changed(node.id)
            return
        self._set_config_value(node, "file", value)
        if node.config.get("path") not in ("", value):
            self._set_config_value(node, "path", value)

    def _handle_sound_browse(self, node: Node, edit: QLineEdit) -> None:
        options = QFileDialog.Options()
        start_dir = Path(edit.text().strip() or str(Path.home()))
        directory = str(start_dir if start_dir.is_dir() else start_dir.parent)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select audio file",
            directory,
            "Audio Files (*.wav *.mp3 *.ogg *.flac *.aiff *.aif *.oga);;All Files (*)",
            options=options,
        )
        if file_path:
            edit.setText(file_path)
            self._handle_sound_path_changed(node, edit)

    def _set_optional_int_config(self, node: Node, key: str, value: int) -> None:
        if value < 0:
            removed = node.config.pop(key, None)
            if removed is not None:
                self._emit_config_changed(node.id)
            return
        self._set_config_value(node, key, int(value))

    def _handle_device_changed(self, index: int) -> None:
        if self._is_updating:
            return
        if not self._current_nodes:
            return
        data = self._device_combo.itemData(index) if self._device_combo else ""
        ports = [data] if data else []
        self.deviceFilterChanged.emit(self._current_nodes[0].id, ports)

    def _handle_profile_changed(self, index: int) -> None:
        if self._is_updating:
            return
        if not self._current_nodes:
            return
        profile_id = self._profile_combo.itemData(index) if self._profile_combo else None
        self.profileAssigned.emit(self._current_nodes[0].id, profile_id)

    def _set_config_value(self, node: Node, key: str, value) -> None:
        current = node.config.get(key)
        if current == value:
            return
        node.config[key] = value
        self._emit_config_changed(node.id)

    def _emit_config_changed(self, node_id: str) -> None:
        self.configChanged.emit(node_id)

    def _on_learn_clicked(self) -> None:
        if not self._current_nodes:
            return
        self.learnRequested.emit(self._current_nodes[0].id)

    def _on_clear_profile(self) -> None:
        if not self._current_nodes:
            return
        self.profileAssigned.emit(self._current_nodes[0].id, None)

    def _clear_content(self) -> None:
        self._control_type_combo = None
        self._control_type_custom_edit = None
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _create_control_type_editor(self, node: Node) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        container.setLayout(layout)

        combo = QComboBox()
        combo.addItem("Auto (from learned control)", "auto")
        combo.addItem("Key / Button", "key")
        combo.addItem("Pad", "pad")
        combo.addItem("Fader / Slider", "fader")
        combo.addItem("Knob / Dial", "knob")
        combo.addItem("Custom label…", "custom")

        stored_mode = str(node.config.get("display_control_type") or "auto")
        index = combo.findData(stored_mode)
        if index == -1:
            index = 0
        self._is_updating = True
        combo.setCurrentIndex(index)
        self._is_updating = False

        combo.currentIndexChanged.connect(lambda idx: self._handle_control_display_changed(node, idx))
        layout.addWidget(combo)
        self._control_type_combo = combo

        custom_edit = QLineEdit()
        custom_edit.setPlaceholderText("Custom label (e.g. Drum Pad)")
        custom_edit.setText(str(node.config.get("display_control_label") or ""))
        custom_edit.editingFinished.connect(lambda: self._handle_control_label_changed(node))
        layout.addWidget(custom_edit)
        self._control_type_custom_edit = custom_edit

        mode = combo.currentData()
        custom_edit.setVisible(mode == "custom")

        return container

    def _handle_control_display_changed(self, node: Node, index: int) -> None:
        if self._is_updating or self._control_type_combo is None:
            return

        mode = self._control_type_combo.itemData(index) or "auto"
        self._set_config_value(node, "display_control_type", mode)

        custom_visible = mode == "custom"
        if self._control_type_custom_edit is not None:
            self._control_type_custom_edit.setVisible(custom_visible)
        if not custom_visible:
            removed = node.config.pop("display_control_label", None)
            if removed is not None:
                self._emit_config_changed(node.id)

    def _handle_control_label_changed(self, node: Node) -> None:
        if self._is_updating or self._control_type_custom_edit is None:
            return
        text = self._control_type_custom_edit.text().strip()
        if not text:
            removed = node.config.pop("display_control_label", None)
            if removed is not None:
                self._emit_config_changed(node.id)
            return
        self._set_config_value(node, "display_control_label", text)

