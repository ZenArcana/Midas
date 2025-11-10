# Midas

Prototype desktop application that maps MIDI controller inputs to automation
macros on Linux. Built with Python, PySide6, and `mido`.

## Getting Started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .
```

Run the application:

```bash
midas
```

## Project Structure

- `app/main.py` – executable entry point
- `app/ui/` – Qt widgets (main window, node editor, device panel)
- `app/midi/` – device discovery and MIDI helpers
- `app/nodes/` – node graph data structures and built-in templates
- `app/actions/` – volume, command, and script action handlers
- `app/storage/` – workspace serialization and starter presets

## Features

- Discover and select MIDI input devices, with live event telemetry.
- Node-based editor with drag-to-move nodes, context menu creation, and keyboard delete.
- Built-in nodes for MIDI input, value mapping, system volume control, shell commands, and embedded Python scripts.
- Cable-style connections with selectable/erasable links between nodes.
- Action engine that maps incoming events to configured runtime actions.
- Workspace persistence (`.json`) with presets accessible from the File menu.
- Auto-saves your current workspace on exit and supports import/export via JSON files.
- Multiple simultaneous MIDI inputs, virtual device groups, and per-control learning with reusable profiles.

## Tips

- Right-click the canvas or use the `Nodes` menu to add new nodes.
- Load the **Mixer Controller** preset from `File → Load Preset` for a ready-made example.
- Save your layout with `File → Save Workspace` (or `Save As` for a new file).
- Script actions run inside a sandboxed environment exposing `event`, `node`, and `context`.

