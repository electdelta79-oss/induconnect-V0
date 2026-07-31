"""PLC connector implementations.

This package defines a brand-agnostic ``PLCConnector`` interface
(see ``base_connector.py``) plus concrete implementations per PLC
brand. Phase 1 only ships ``SiemensConnector``; future brands should
be added here as additional modules implementing the same interface.
"""
