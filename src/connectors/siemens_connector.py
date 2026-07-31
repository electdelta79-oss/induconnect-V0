"""Siemens S7 connector, built on ``python-snap7``.

Phase 1 scope: reads global PLC tags (Input / Output / Merker memory)
addressed via standard Siemens logical addresses (e.g. ``%MW14``,
``%M12.0``). Data Block (DB) addressing is parsed by
``address_parser`` for forward compatibility, but reading Data Blocks
reliably by fixed byte offset only works when "optimized block
access" is *disabled* for that DB in TIA Portal.

Why: S7-1200/1500 CPUs default to "optimized" DB storage, where
variables are *not* laid out at fixed byte offsets internally --
TIA Portal manages the layout and only exposes symbolic access.
There is no S7comm query that reports "is this DB optimized"; the
practical way to find out is to attempt a raw offset read and see
whether it is rejected. That detection + a symbolic-read fallback is
stubbed out below (see ``_read_db_tag``) as a documented extension
point for Phase 2, rather than being fully implemented now, since
Phase 1 testing only exercises non-DB tags.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from ..address_parser import AddressSize, MemoryArea, ParsedAddress, parse_address
from ..models import Tag, TagReading
from .base_connector import PLCConnector

logger = logging.getLogger(__name__)

try:
    import snap7
    from snap7.util import get_bool, get_dint, get_dword, get_int, get_real, get_word
except ImportError as exc:  # pragma: no cover - exercised only without the dep
    raise ImportError(
        "python-snap7 is required for SiemensConnector. Install it via "
        "'pip install python-snap7' (see requirements.txt), and ensure the "
        "underlying snap7 C library is available on this system."
    ) from exc

# python-snap7's area-code location has moved between versions; this
# shim keeps the rest of the module version-agnostic. If your
# installed version fails both imports, check python-snap7's release
# notes for the current location of these constants.
try:
    from snap7.type import Area  # newer python-snap7 releases

    _AREA_CODE = {
        MemoryArea.INPUT: Area.PE,
        MemoryArea.OUTPUT: Area.PA,
        MemoryArea.MERKER: Area.MK,
        MemoryArea.DATA_BLOCK: Area.DB,
    }
except ImportError:  # pragma: no cover - depends on installed snap7 version
    from snap7.types import S7AreaDB, S7AreaMK, S7AreaPA, S7AreaPE  # older releases

    _AREA_CODE = {
        MemoryArea.INPUT: S7AreaPE,
        MemoryArea.OUTPUT: S7AreaPA,
        MemoryArea.MERKER: S7AreaMK,
        MemoryArea.DATA_BLOCK: S7AreaDB,
    }

# Number of bytes to read for each declared PLC data type. Extend this
# map if you need additional types (e.g. "LReal", "Time", "String").
_TYPE_BYTE_LENGTH = {
    "BOOL": 1,
    "BYTE": 1,
    "USINT": 1,
    "SINT": 1,
    "CHAR": 1,
    "INT": 2,
    "UINT": 2,
    "WORD": 2,
    "DINT": 4,
    "UDINT": 4,
    "DWORD": 4,
    "REAL": 4,
}


def _decode(data_type: str, raw: bytearray, bit_offset: Optional[int]):
    """Decode raw bytes into a Python value per the declared data type.

    Args:
        data_type: Declared PLC data type, e.g. ``"UInt"`` (matched
            case-insensitively).
        raw: The raw bytes read from the PLC, sized to match the type.
        bit_offset: Bit index within ``raw[0]``, required for BOOL.

    Returns:
        A ``bool``, ``int``, or ``float`` matching the data type.

    Raises:
        ValueError: If the data type is unsupported or a required
            bit offset is missing.
    """
    normalized = data_type.strip().upper()

    if normalized == "BOOL":
        if bit_offset is None:
            raise ValueError("BOOL tags require a bit offset in their address.")
        return get_bool(raw, 0, bit_offset)
    if normalized in ("BYTE", "USINT", "CHAR"):
        return raw[0]
    if normalized == "SINT":
        return raw[0] - 256 if raw[0] > 127 else raw[0]
    if normalized == "INT":
        return get_int(raw, 0)
    if normalized in ("UINT", "WORD"):
        return get_word(raw, 0)
    if normalized == "DINT":
        return get_dint(raw, 0)
    if normalized in ("UDINT", "DWORD"):
        return get_dword(raw, 0)
    if normalized == "REAL":
        return get_real(raw, 0)

    raise ValueError(f"Unsupported data type for decoding: {data_type!r}")


class SiemensConnector(PLCConnector):
    """Reads tags from a Siemens S7 PLC (S7-1200 / S7-200 Smart) over Ethernet.

    Args:
        ip: IP address of the target PLC.
        rack: S7 rack number. Defaults to 0 (standard for S7-1200).
        slot: S7 slot number. Defaults to 1 (standard for S7-1200).
            S7-200 Smart deployments may require a different value;
            confirm against your CPU's configuration if reads fail.
        connect_timeout_s: Reserved for future use if the installed
            snap7 version supports configurable connect timeouts.
    """

    def __init__(
        self,
        ip: str,
        rack: int = 0,
        slot: int = 1,
        connect_timeout_s: float = 5.0,
    ) -> None:
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.connect_timeout_s = connect_timeout_s
        self._client: Optional["snap7.client.Client"] = None

    def connect(self) -> None:
        """Connect to the PLC via S7comm.

        Raises:
            ConnectionError: If the connection attempt fails (PLC
                unreachable, wrong rack/slot, or PUT/GET communication
                disabled on the CPU).
        """
        client = snap7.client.Client()
        try:
            client.connect(self.ip, self.rack, self.slot)
        except Exception as exc:
            raise ConnectionError(
                f"Could not connect to Siemens PLC at {self.ip} "
                f"(rack={self.rack}, slot={self.slot}): {exc}. "
                "Confirm the CPU is reachable on port 102 and that "
                "'Permit access with PUT/GET communication' is enabled "
                "in TIA Portal (CPU Properties -> Protection & Security)."
            ) from exc

        if not client.get_connected():
            raise ConnectionError(
                f"Connection to {self.ip} did not succeed (rack={self.rack}, "
                f"slot={self.slot})."
            )

        self._client = client
        logger.info("Connected to Siemens PLC at %s (rack=%d, slot=%d)",
                    self.ip, self.rack, self.slot)

    def disconnect(self) -> None:
        """Disconnect from the PLC, if currently connected."""
        if self._client is not None:
            try:
                self._client.disconnect()
            finally:
                self._client = None
                logger.info("Disconnected from Siemens PLC at %s", self.ip)

    def read_tag(self, tag: Tag) -> TagReading:
        """Read a single tag's value.

        Returns a :class:`TagReading` with ``error`` set (rather than
        raising) if the address can't be parsed, the type is
        unsupported, or the underlying read fails -- so a single bad
        tag does not abort a larger batch read.
        """
        if self._client is None:
            return TagReading(
                tag=tag, value=None,
                error="Not connected to a PLC (call connect() first).",
            )

        try:
            address = parse_address(tag.logical_address)
        except Exception as exc:
            return TagReading(tag=tag, value=None, error=f"Address parse error: {exc}")

        try:
            if address.area is MemoryArea.DATA_BLOCK:
                value = self._read_db_tag(tag, address)
            else:
                value = self._read_non_db_tag(tag, address)
        except Exception as exc:
            return TagReading(tag=tag, value=None, error=str(exc))

        return TagReading(tag=tag, value=value, timestamp=datetime.utcnow())

    def _read_non_db_tag(self, tag: Tag, address: ParsedAddress):
        """Read a tag from Input, Output, or Merker memory."""
        byte_length = 1 if address.size is AddressSize.BIT else _TYPE_BYTE_LENGTH.get(
            tag.data_type.strip().upper()
        )
        if byte_length is None:
            raise ValueError(f"Unsupported data type: {tag.data_type!r}")

        area_code = _AREA_CODE[address.area]
        raw = self._client.read_area(area_code, 0, address.byte_offset, byte_length)
        return _decode(tag.data_type, raw, address.bit_offset)

    def _read_db_tag(self, tag: Tag, address: ParsedAddress):
        """Read a tag from a Data Block (Phase 2 extension point).

        Attempts a raw byte-offset read. If the DB has "optimized
        block access" enabled, this read will fail (S7 returns an
        access-denied style error) because optimized DBs don't expose
        fixed offsets over S7comm. That failure is caught here and
        re-raised with a clear, actionable message rather than a raw
        snap7 error, so batch reads can flag it distinctly from other
        failure types (e.g. via a message prefix check upstream).

        A full Phase 2 implementation would add a symbolic read path
        (matching by tag name against a non-optimized layout, or
        requiring the DB's optimization to be disabled) -- that is
        intentionally not implemented yet.
        """
        if address.db_number is None:
            raise ValueError(f"Data block address missing DB number: {tag.logical_address!r}")

        byte_length = 1 if address.size is AddressSize.BIT else _TYPE_BYTE_LENGTH.get(
            tag.data_type.strip().upper()
        )
        if byte_length is None:
            raise ValueError(f"Unsupported data type: {tag.data_type!r}")

        area_code = _AREA_CODE[MemoryArea.DATA_BLOCK]
        try:
            raw = self._client.read_area(
                area_code, address.db_number, address.byte_offset, byte_length
            )
        except Exception as exc:
            raise RuntimeError(
                f"Raw offset read failed for DB{address.db_number} tag "
                f"{tag.name!r} -- this DB may have 'optimized block access' "
                "enabled, which blocks fixed-offset reads over S7comm. "
                "See README for the Phase 2 symbolic-read plan. "
                f"Underlying error: {exc}"
            ) from exc

        return _decode(tag.data_type, raw, address.bit_offset)
