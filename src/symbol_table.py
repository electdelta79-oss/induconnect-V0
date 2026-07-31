"""Loader for TIA Portal symbol/tag table exports.

Supports the export format observed in practice, with columns:

    Name, Path, Data Type, Logical Address, Comment,
    Hmi Visible, Hmi Access, Hmi Write, Typeobject, Version ID

Only ``Name``, ``Data Type``, and ``Logical Address`` are required;
``Path`` and ``Comment`` are captured if present. All other columns
are ignored -- they describe TIA Portal/HMI configuration, not data
needed to read a tag's live value.

Both ``.csv`` and ``.xlsx`` exports are supported.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

from .models import Tag

# Required columns in the export (case-sensitive, matches TIA Portal's
# own export headers). If your export uses different header text,
# adjust this mapping rather than the parsing logic below.
_REQUIRED_COLUMNS = {"Name", "Data Type", "Logical Address"}
_OPTIONAL_COLUMNS = {"Path", "Comment"}


class SymbolTableError(ValueError):
    """Raised when a symbol table file is missing or malformed."""


def load_symbol_table(path: str | Path) -> List[Tag]:
    """Load a TIA Portal symbol table export into a list of Tags.

    Args:
        path: Path to a ``.csv`` or ``.xlsx`` symbol table export.

    Returns:
        A list of :class:`~src.models.Tag` objects, one per non-empty
        row in the export.

    Raises:
        SymbolTableError: If the file is missing, has an unsupported
            extension, is missing required columns, or contains rows
            that cannot be parsed.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise SymbolTableError(f"Symbol table file not found: {file_path}")

    suffix = file_path.suffix.lower()
    try:
        if suffix == ".csv":
            frame = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        elif suffix in (".xlsx", ".xls"):
            frame = pd.read_excel(file_path, dtype=str)
            frame = frame.fillna("")
        else:
            raise SymbolTableError(
                f"Unsupported symbol table file type: {suffix!r}. "
                "Expected .csv or .xlsx."
            )
    except SymbolTableError:
        raise
    except Exception as exc:  # pragma: no cover - depends on file I/O
        raise SymbolTableError(
            f"Failed to read symbol table file {file_path}: {exc}"
        ) from exc

    missing = _REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise SymbolTableError(
            f"Symbol table is missing required column(s): {sorted(missing)}. "
            f"Found columns: {list(frame.columns)}"
        )

    tags: List[Tag] = []
    for row_number, row in frame.iterrows():
        name = str(row["Name"]).strip()
        data_type = str(row["Data Type"]).strip()
        logical_address = str(row["Logical Address"]).strip()

        if not name or not data_type or not logical_address:
            # Skip blank/placeholder rows (e.g. TIA's trailing
            # "<Add new>" row, or fully empty spreadsheet rows).
            continue

        comment = str(row["Comment"]).strip() if "Comment" in frame.columns else ""
        table_path = str(row["Path"]).strip() if "Path" in frame.columns else ""

        tags.append(
            Tag(
                name=name,
                data_type=data_type,
                logical_address=logical_address,
                comment=comment,
                path=table_path,
            )
        )

    if not tags:
        raise SymbolTableError(
            f"Symbol table {file_path} contained no usable tag rows."
        )

    return tags
