"""Brand-agnostic PLC connector interface.

Every supported PLC brand implements this interface, so the rest of
the tool (CLI, output formatting, dashboard integration) never needs
to know which brand it is talking to. To add support for a new brand
in a later phase, create a new module in this package implementing
``PLCConnector`` and wire it up wherever connectors are selected
(currently ``main.py``).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Iterable, List

from ..models import Tag, TagReading

logger = logging.getLogger(__name__)


class PLCConnector(ABC):
    """Abstract interface for reading tags from a PLC.

    Implementations are expected to be usable as context managers::

        with SiemensConnector(ip="192.168.0.10") as plc:
            readings = plc.read_tags(tags)
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish a connection to the PLC.

        Raises:
            ConnectionError: If the PLC cannot be reached or the
                connection is refused.
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Close the connection to the PLC, if open."""

    @abstractmethod
    def read_tag(self, tag: Tag) -> TagReading:
        """Read a single tag's current value from the PLC.

        Implementations should not raise on a per-tag read failure;
        instead they should return a :class:`TagReading` with
        ``error`` set, so that one bad tag does not abort a whole
        batch. Connection-level failures (PLC unreachable) may still
        raise from :meth:`connect`.
        """

    def read_tags(self, tags: Iterable[Tag]) -> List[TagReading]:
        """Read multiple tags, continuing past individual failures.

        Args:
            tags: The tags to read.

        Returns:
            One :class:`TagReading` per input tag, in the same order.
            Tags that fail to read are included with ``error`` set
            rather than being omitted.
        """
        readings: List[TagReading] = []
        for tag in tags:
            try:
                readings.append(self.read_tag(tag))
            except Exception as exc:  # noqa: BLE001 - isolate per-tag failures
                logger.warning("Failed to read tag %r: %s", tag.name, exc)
                readings.append(TagReading(tag=tag, value=None, error=str(exc)))
        return readings

    def __enter__(self) -> "PLCConnector":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
