from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

try:
    import mido
except ImportError:  # pragma: no cover - optional dependency.
    mido = None  # type: ignore[assignment]


@dataclass(frozen=True)
class MidiEvent:
    """
    Normalized representation of a MIDI message.
    """

    message_type: str
    channel: int | None
    control: int | None
    value: int | None
    note: int | None
    velocity: int | None
    raw: Any
    source: str | None = None
    aliases: tuple[str, ...] = ()

    @classmethod
    def from_message(
        cls,
        message: "mido.Message",
        *,
        source: str | None = None,
        aliases: Sequence[str] | None = None,
    ) -> "MidiEvent":
        """
        Convert a `mido.Message` into a `MidiEvent`.
        """

        return cls(
            message_type=message.type,
            channel=getattr(message, "channel", None),
            control=getattr(message, "control", None),
            value=getattr(message, "value", None),
            note=getattr(message, "note", None),
            velocity=getattr(message, "velocity", None),
            raw=message,
            source=source,
            aliases=tuple(aliases or ()),
        )

