"""Unit tests for src.address_parser -- no PLC hardware required."""

import unittest

from src.address_parser import (
    AddressParseError,
    AddressSize,
    MemoryArea,
    parse_address,
)


class TestParseAddress(unittest.TestCase):
    def test_word_address(self):
        result = parse_address("%MW14")
        self.assertEqual(result.area, MemoryArea.MERKER)
        self.assertEqual(result.byte_offset, 14)
        self.assertEqual(result.size, AddressSize.WORD)
        self.assertIsNone(result.bit_offset)

    def test_bit_address(self):
        result = parse_address("%M12.0")
        self.assertEqual(result.area, MemoryArea.MERKER)
        self.assertEqual(result.byte_offset, 12)
        self.assertEqual(result.size, AddressSize.BIT)
        self.assertEqual(result.bit_offset, 0)

    def test_input_bit_address(self):
        result = parse_address("%I0.1")
        self.assertEqual(result.area, MemoryArea.INPUT)
        self.assertEqual(result.byte_offset, 0)
        self.assertEqual(result.bit_offset, 1)

    def test_output_word_address(self):
        result = parse_address("%QW4")
        self.assertEqual(result.area, MemoryArea.OUTPUT)
        self.assertEqual(result.size, AddressSize.WORD)
        self.assertEqual(result.byte_offset, 4)

    def test_dword_address(self):
        result = parse_address("%MD10")
        self.assertEqual(result.size, AddressSize.DWORD)
        self.assertEqual(result.byte_offset, 10)

    def test_data_block_word_address(self):
        result = parse_address("%DB1.DBW0")
        self.assertEqual(result.area, MemoryArea.DATA_BLOCK)
        self.assertEqual(result.db_number, 1)
        self.assertEqual(result.byte_offset, 0)
        self.assertEqual(result.size, AddressSize.WORD)

    def test_data_block_bit_address(self):
        result = parse_address("%DB3.DBX2.1")
        self.assertEqual(result.area, MemoryArea.DATA_BLOCK)
        self.assertEqual(result.db_number, 3)
        self.assertEqual(result.byte_offset, 2)
        self.assertEqual(result.bit_offset, 1)

    def test_lowercase_input_is_accepted(self):
        result = parse_address("%mw14")
        self.assertEqual(result.area, MemoryArea.MERKER)

    def test_whitespace_is_stripped(self):
        result = parse_address("  %MW14  ")
        self.assertEqual(result.byte_offset, 14)

    def test_invalid_address_raises(self):
        with self.assertRaises(AddressParseError):
            parse_address("not_an_address")

    def test_missing_size_and_bit_raises(self):
        with self.assertRaises(AddressParseError):
            parse_address("%M12")


if __name__ == "__main__":
    unittest.main()
