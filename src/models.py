"""Core data models shared across the tag-reading pipeline.

These models are intentionally brand-agnostic: ``Tag`` describes an
entry from a symbol table (name, data type, logical address, and any
free-form metadata), while ``TagReading`` describes the resolved
value of a ``Tag`` after it has been read from a live PLC.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(frozen=True)
class Tag:
    """A single row from a PLC symbol/tag table export.

    Attributes:
        name: Human-readable tag name (e.g. ``"motor_speed"``).
        data_type: Declared PLC data type as a string (e.g. ``"UInt"``,
            ``"Bool"``, ``"Real"``). Case-insensitive by convention;
            callers should normalize before comparison.
        logical_address: Siemens logical address notation, e.g.
            ``"%MW14"``, ``"%M12.0"``, or ``"%DB1.DBW0"``.
        comment: Optional free-text comment/description from the
            symbol table export.
        path: Optional tag table / grouping path from the export
            (e.g. ``"Default tag table"``). Informational only.
    """

    name: str
    data_type: str
    logical_address: str
    comment: str = ""
    path: str = ""


@dataclass(frozen=True)
class TagReading:
    """The resolved value of a :class:`Tag` after a live PLC read.

    Attributes:
        tag: The originating :class:`Tag` definition.
        value: The decoded Python value (bool, int, or float),
            or ``None`` if the read failed.
        timestamp: UTC timestamp of when the read was performed.
        error: Human-readable error message if the read failed;
            ``None`` on success.
    """

    tag: Tag
    value: Optional[Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        """Whether the read completed without error."""
        return self.error is None

    def to_dict(self) -> dict:
        """Serialize this reading into a JSON-friendly dictionary."""
        return {
            "name": self.tag.name,
            "data_type": self.tag.data_type,
            "logical_address": self.tag.logical_address,
            "comment": self.tag.comment,
            "value": self.value,
            "timestamp": self.timestamp.isoformat() + "Z",
            "success": self.success,
            "error": self.error,
        }
