"""Unit tests for src.symbol_table -- no PLC hardware required."""

import tempfile
import unittest
from pathlib import Path

from src.symbol_table import SymbolTableError, load_symbol_table

SAMPLE_CSV = (
    "Name,Path,Data Type,Logical Address,Comment,"
    "Hmi Visible,Hmi Access,Hmi Write,Typeobject,Version ID\n"
    "motor_speed,Default tag table,UInt,%MW14,,True,True,True,,\n"
    "temp,Default tag table,UInt,%MW16,,True,True,True,,\n"
    "status,Default tag table,Bool,%M12.0,,True,True,True,,\n"
)


class TestLoadSymbolTable(unittest.TestCase):
    def _write_temp_csv(self, content: str) -> Path:
        tmp_dir = Path(tempfile.mkdtemp())
        path = tmp_dir / "symbols.csv"
        path.write_text(content)
        return path

    def test_loads_expected_tags(self):
        path = self._write_temp_csv(SAMPLE_CSV)
        tags = load_symbol_table(path)
        self.assertEqual(len(tags), 3)
        names = [tag.name for tag in tags]
        self.assertEqual(names, ["motor_speed", "temp", "status"])

    def test_tag_fields_are_populated(self):
        path = self._write_temp_csv(SAMPLE_CSV)
        tags = load_symbol_table(path)
        motor_speed = tags[0]
        self.assertEqual(motor_speed.data_type, "UInt")
        self.assertEqual(motor_speed.logical_address, "%MW14")
        self.assertEqual(motor_speed.path, "Default tag table")

    def test_missing_file_raises(self):
        with self.assertRaises(SymbolTableError):
            load_symbol_table("/nonexistent/path/symbols.csv")

    def test_missing_required_column_raises(self):
        bad_csv = "Name,Data Type\nmotor_speed,UInt\n"
        path = self._write_temp_csv(bad_csv)
        with self.assertRaises(SymbolTableError):
            load_symbol_table(path)

    def test_unsupported_extension_raises(self):
        path = self._write_temp_csv(SAMPLE_CSV)
        renamed = path.with_suffix(".txt")
        path.rename(renamed)
        with self.assertRaises(SymbolTableError):
            load_symbol_table(renamed)

    def test_blank_rows_are_skipped(self):
        csv_with_blank = SAMPLE_CSV + ",,,,,,,,,\n"
        path = self._write_temp_csv(csv_with_blank)
        tags = load_symbol_table(path)
        self.assertEqual(len(tags), 3)


if __name__ == "__main__":
    unittest.main()
