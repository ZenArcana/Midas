from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Optional, Sequence

from .events import MidiEvent


@dataclass
class ControlProfile:
    """
    Represents a learned mapping between a MIDI control and a logical profile
    that can be reused across nodes.
    """

    id: str
    name: str
    device_port: str
    message_type: str
    control_type: str  # e.g. continuous, button
    channel: Optional[int]
    control: Optional[int]
    note: Optional[int]
    aliases: Sequence[str] = field(default_factory=tuple)

    def matches_event(self, event: MidiEvent) -> bool:
        if event.source != self.device_port and self.device_port not in event.aliases:
            return False
        if event.message_type != self.message_type:
            return False
        if self.channel is not None and event.channel != self.channel:
            return False
        if self.control is not None and event.control != self.control:
            return False
        if self.note is not None and event.note != self.note:
            return False
        return True


class ControlProfileStore:
    """
    In-memory store for control profiles learned during the session.
    """

    def __init__(self) -> None:
        self._profiles: Dict[str, ControlProfile] = {}

    def add_from_event(
        self,
        event: MidiEvent,
        *,
        name: Optional[str] = None,
        device_port: Optional[str] = None,
    ) -> ControlProfile:
        control_type = self._classify_event(event)
        profile_id = uuid.uuid4().hex
        profile_name = name or self._default_profile_name(event, control_type)
        profile = ControlProfile(
            id=profile_id,
            name=profile_name,
            device_port=device_port or event.source or "unknown",
            message_type=event.message_type,
            control_type=control_type,
            channel=event.channel,
            control=event.control,
            note=event.note,
            aliases=event.aliases,
        )
        self._profiles[profile.id] = profile
        return profile

    def add_profile(self, profile: ControlProfile) -> None:
        self._profiles[profile.id] = profile

    def get(self, profile_id: str) -> Optional[ControlProfile]:
        return self._profiles.get(profile_id)

    def remove(self, profile_id: str) -> None:
        self._profiles.pop(profile_id, None)

    def profiles(self) -> List[ControlProfile]:
        return list(self._profiles.values())

    def profiles_for_device(self, device_port: str) -> List[ControlProfile]:
        return [profile for profile in self._profiles.values() if profile.device_port == device_port]

    def __iter__(self) -> Iterator[ControlProfile]:
        return iter(self._profiles.values())

    def clear(self) -> None:
        self._profiles.clear()

    def serialize(self) -> List[Dict[str, object]]:
        payload: List[Dict[str, object]] = []
        for profile in self._profiles.values():
            payload.append(
                {
                    "id": profile.id,
                    "name": profile.name,
                    "device_port": profile.device_port,
                    "message_type": profile.message_type,
                    "control_type": profile.control_type,
                    "channel": profile.channel,
                    "control": profile.control,
                    "note": profile.note,
                    "aliases": list(profile.aliases),
                }
            )
        return payload

    def load(self, data: Iterable[Dict[str, object]]) -> None:
        self.clear()
        for entry in data:
            try:
                profile = ControlProfile(
                    id=str(entry["id"]),
                    name=str(entry["name"]),
                    device_port=str(entry["device_port"]),
                    message_type=str(entry["message_type"]),
                    control_type=str(entry.get("control_type", "")),
                    channel=self._coerce_optional_int(entry.get("channel")),
                    control=self._coerce_optional_int(entry.get("control")),
                    note=self._coerce_optional_int(entry.get("note")),
                    aliases=tuple(str(alias) for alias in entry.get("aliases", []) or []),
                )
            except KeyError:
                continue
            self._profiles[profile.id] = profile

    def _coerce_optional_int(self, value: object) -> Optional[int]:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _classify_event(self, event: MidiEvent) -> str:
        if event.message_type == "control_change":
            return "continuous"
        if event.message_type in {"note_on", "note_off"}:
            return "button"
        return event.message_type

    def _default_profile_name(self, event: MidiEvent, control_type: str) -> str:
        parts = []
        if event.source:
            parts.append(event.source)
        if control_type == "continuous" and event.control is not None:
            parts.append(f"CC{event.control}")
        elif event.note is not None:
            parts.append(f"NOTE{event.note}")
        else:
            parts.append(event.message_type)
        return " ".join(parts)

