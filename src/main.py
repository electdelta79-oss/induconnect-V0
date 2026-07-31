"""CLI entry point: load a symbol table, read tags from a live PLC,
and write the resolved values to a JSON file for downstream dashboard
consumption.

Example:
    python -m src.main --ip 192.168.0.10 \\
        --symbol-table sample_data/sample_symbol_table.csv \\
        --output plc_tag_values.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List

from .connectors.siemens_connector import SiemensConnector
from .models import TagReading
from .symbol_table import SymbolTableError, load_symbol_table

logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Read Siemens PLC tags per a TIA Portal symbol table export."
    )
    parser.add_argument("--ip", required=True, help="IP address of the target PLC.")
    parser.add_argument(
        "--symbol-table",
        required=True,
        help="Path to the TIA Portal symbol table export (.csv or .xlsx).",
    )
    parser.add_argument(
        "--output",
        default="plc_tag_values.json",
        help="Path to write the resolved tag values as JSON (default: %(default)s).",
    )
    parser.add_argument(
        "--rack", type=int, default=0, help="S7 rack number (default: %(default)s)."
    )
    parser.add_argument(
        "--slot", type=int, default=1, help="S7 slot number (default: %(default)s)."
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: %(default)s).",
    )
    return parser


def write_readings(readings: List[TagReading], output_path: Path) -> None:
    """Write tag readings to a JSON file in dashboard-friendly form."""
    payload = {
        "tags": [reading.to_dict() for reading in readings],
        "tag_count": len(readings),
        "success_count": sum(1 for r in readings if r.success),
        "failure_count": sum(1 for r in readings if not r.success),
    }
    output_path.write_text(json.dumps(payload, indent=2))
    logger.info(
        "Wrote %d tag readings (%d ok, %d failed) to %s",
        payload["tag_count"], payload["success_count"], payload["failure_count"],
        output_path,
    )


def run(argv: List[str] | None = None) -> int:
    """Run the CLI. Returns a process exit code."""
    args = build_arg_parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        tags = load_symbol_table(args.symbol_table)
    except SymbolTableError as exc:
        logger.error("Failed to load symbol table: %s", exc)
        return 1

    logger.info("Loaded %d tag(s) from %s", len(tags), args.symbol_table)

    try:
        with SiemensConnector(ip=args.ip, rack=args.rack, slot=args.slot) as plc:
            readings = plc.read_tags(tags)
    except ConnectionError as exc:
        logger.error("Could not connect to PLC: %s", exc)
        return 1

    write_readings(readings, Path(args.output))

    if any(not r.success for r in readings):
        logger.warning("One or more tags failed to read; see output file for details.")

    return 0


if __name__ == "__main__":
    sys.exit(run())
