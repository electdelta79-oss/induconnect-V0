"""Parsing for Siemens logical address notation.

Siemens addresses (as seen in TIA Portal exports) follow patterns like:

    %MW14       -> Merker (M) area, Word, byte offset 14
    %M12.0      -> Merker (M) area, single bit, byte offset 12, bit 0
    %MB5        -> Merker (M) area, Byte, byte offset 5
    %MD10       -> Merker (M) area, DWord, byte offset 10
    %I0.1       -> Input (I) area, single bit, byte offset 0, bit 1
    %QW4        -> Output (Q) area, Word, byte offset 4
    %DB1.DBW0   -> Data Block 1, Word, byte offset 0
    %DB3.DBX2.1 -> Data Block 3, single bit, byte offset 2, bit 1

This module converts those strings into a structured
:class:`ParsedAddress` that connector implementations can use to
issue the correct low-level read call.

Note: Data Block addressing (the ``%DBn.DBx...`` form) is parsed here
for forward-compatibility, but reading optimized Data Blocks by fixed
offset is not reliable -- see the Siemens connector module and the
project README for details on that limitation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class MemoryArea(str, Enum):
    """Which PLC memory area an address refers to."""

    INPUT = "I"
    OUTPUT = "Q"
    MERKER = "M"
    DATA_BLOCK = "DB"


class AddressSize(str, Enum):
    """The size/granularity implied by the address notation itself.

    This is distinct from the tag's declared *data type* (e.g. "UInt"),
    though the two usually agree. The data type from the symbol table
    should be treated as authoritative for decoding; this enum mainly
    helps validate that the address and data type are consistent.
    """

    BIT = "X"
    BYTE = "B"
    WORD = "W"
    DWORD = "D"


@dataclass(frozen=True)
class ParsedAddress:
    """Structured representation of a parsed Siemens logical address.

    Attributes:
        area: Which memory area the address refers to.
        byte_offset: Starting byte offset within that area.
        size: The size/granularity implied by the address notation.
        bit_offset: Bit index (0-7) within the byte, only meaningful
            when ``size`` is :attr:`AddressSize.BIT`.
        db_number: Data Block number, only set when
            ``area`` is :attr:`MemoryArea.DATA_BLOCK`.
    """

    area: MemoryArea
    byte_offset: int
    size: AddressSize
    bit_offset: Optional[int] = None
    db_number: Optional[int] = None


class AddressParseError(ValueError):
    """Raised when a logical address string cannot be parsed."""


# %DB<n>.DB<X|B|W|D><offset>(.<bit>)?
_DB_PATTERN = re.compile(
    r"^%DB(?P<db_number>\d+)\.DB(?P<size>[XBWD])(?P<byte_offset>\d+)"
    r"(?:\.(?P<bit_offset>\d+))?$",
    re.IGNORECASE,
)

# %<area><size?><offset>(.<bit>)?  e.g. %MW14, %M12.0, %MB5, %MD10, %I0.1
_AREA_PATTERN = re.compile(
    r"^%(?P<area>[IQM])(?P<size>[XBWD]?)(?P<byte_offset>\d+)"
    r"(?:\.(?P<bit_offset>\d+))?$",
    re.IGNORECASE,
)


def parse_address(address: str) -> ParsedAddress:
    """Parse a Siemens logical address string into a structured form.

    Args:
        address: Logical address string, e.g. ``"%MW14"`` or
            ``"%M12.0"``. Leading/trailing whitespace is ignored.

    Returns:
        A :class:`ParsedAddress` describing the area, offsets, and size.

    Raises:
        AddressParseError: If the string does not match any known
            Siemens address pattern.
    """
    cleaned = address.strip().upper()

    db_match = _DB_PATTERN.match(cleaned)
    if db_match:
        return _build_from_match(
            db_match,
            area=MemoryArea.DATA_BLOCK,
            db_number=int(db_match.group("db_number")),
        )

    area_match = _AREA_PATTERN.match(cleaned)
    if area_match:
        area = MemoryArea(area_match.group("area"))
        return _build_from_match(area_match, area=area, db_number=None)

    raise AddressParseError(
        f"Unrecognized Siemens logical address format: {address!r}"
    )


def _build_from_match(
    match: "re.Match[str]",
    area: MemoryArea,
    db_number: Optional[int],
) -> ParsedAddress:
    """Build a ParsedAddress from a successful regex match."""
    raw_size = match.group("size")
    byte_offset = int(match.group("byte_offset"))
    bit_group = match.group("bit_offset")

    if bit_group is not None:
        # Explicit bit present (e.g. "%M12.0") implies bit-level access
        # regardless of whether a size letter was also given.
        size = AddressSize.BIT
        bit_offset = int(bit_group)
    elif raw_size:
        size = AddressSize(raw_size)
        bit_offset = None
    else:
        # No size letter and no bit suffix -- not a valid combination
        # for the non-DB pattern (bit addresses require a bit suffix).
        raise AddressParseError(
            "Address is missing a size specifier (W/B/D) or a bit "
            "suffix (e.g. '.0')."
        )

    return ParsedAddress(
        area=area,
        byte_offset=byte_offset,
        size=size,
        bit_offset=bit_offset,
        db_number=db_number,
    )
