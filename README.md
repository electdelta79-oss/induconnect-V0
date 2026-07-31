# Siemens PLC Tag Reader

Reads named tags from a Siemens PLC (S7-1200 / S7-200 Smart) over
Ethernet, using a symbol table exported from TIA Portal to resolve
tag names, data types, and addresses. Outputs a structured JSON file
suitable for feeding a production-monitoring dashboard.

This is **Phase 1** of a planned multi-brand tool: the architecture
uses a brand-agnostic `PLCConnector` interface so future PLC brands
can be added without touching the rest of the pipeline.

## Status / Scope

- ✅ Global PLC tags (Input `%I`, Output `%Q`, Merker `%M` memory),
  addressed via standard Siemens notation (`%MW14`, `%M12.0`, etc.)
- 🚧 Data Block (DB) tags are **parsed** but only partially supported
  for **reading** -- see [Known Limitation: Optimized Data Blocks](#known-limitation-optimized-data-blocks-db)
  below. This is a documented Phase 2 extension point, not a bug.
- This tool performs **read-only** operations. It never writes to PLC
  memory.

## Setup

1. Install Python dependencies:

   ```bash
   pip install -r requirements.txt
   ```

   `python-snap7` also requires the underlying `snap7` C library to
   be installed on your system. See the
   [python-snap7 documentation](https://github.com/gijzelaerr/python-snap7)
   for OS-specific install instructions if `import snap7` fails.

2. On each target PLC, confirm **"Permit access with PUT/GET
   communication"** is enabled in TIA Portal
   (CPU Properties → Protection & Security). Without this, the PLC
   will refuse even read-only connections.

3. Export your symbol table from TIA Portal (see
   [Symbol Table Format](#symbol-table-format) below) and note its path.

## Usage

```bash
python -m src.main \
    --ip 192.168.0.10 \
    --symbol-table sample_data/sample_symbol_table.csv \
    --output plc_tag_values.json
```

| Argument          | Required | Default               | Description                                  |
|-------------------|----------|------------------------|-----------------------------------------------|
| `--ip`            | Yes      | —                      | IP address of the target PLC.                 |
| `--symbol-table`  | Yes      | —                      | Path to a `.csv` or `.xlsx` symbol table export. |
| `--output`        | No       | `plc_tag_values.json` | Where to write resolved tag values.           |
| `--rack`          | No       | `0`                    | S7 rack number.                               |
| `--slot`          | No       | `1`                    | S7 slot number (S7-1200 default).             |
| `--log-level`     | No       | `INFO`                 | `DEBUG` / `INFO` / `WARNING` / `ERROR`.       |

## Symbol Table Format

Exported from TIA Portal (PLC Tags → select tag table → Export) as
`.csv` or `.xlsx`, with these columns:

```
Name, Path, Data Type, Logical Address, Comment,
Hmi Visible, Hmi Access, Hmi Write, Typeobject, Version ID
```

Only **Name**, **Data Type**, and **Logical Address** are required;
**Path** and **Comment** are captured if present. The remaining
columns (Hmi Visible/Access/Write, Typeobject, Version ID) are TIA
Portal/HMI configuration metadata and are ignored by this tool.

Example rows (see `sample_data/sample_symbol_table.csv`):

| Name         | Path               | Data Type | Logical Address |
|--------------|--------------------|-----------| -----------------|
| motor_speed  | Default tag table  | UInt      | %MW14            |
| temp         | Default tag table  | UInt      | %MW16            |
| status       | Default tag table  | Bool      | %M12.0           |

## Output Format

```json
{
  "tags": [
    {
      "name": "motor_speed",
      "data_type": "UInt",
      "logical_address": "%MW14",
      "comment": "",
      "value": 1523,
      "timestamp": "2026-07-17T12:00:00.000000Z",
      "success": true,
      "error": null
    }
  ],
  "tag_count": 3,
  "success_count": 3,
  "failure_count": 0
}
```

### Example dashboard mapping

If your dashboard shows an **Efficiency Rate** KPI computed as
`actual / target * 100`, you'd map two tags from the output above,
e.g.:

```python
actual = next(t["value"] for t in payload["tags"] if t["name"] == "current_hour_count")
target = next(t["value"] for t in payload["tags"] if t["name"] == "current_hour_target")
efficiency_rate = round(actual / target * 100, 1)
```

The same pattern applies to "Current Hour", "Total Shift", and "Line
Status" KPIs -- each is just a named tag (or a small calculation over
a couple of named tags) once real production tags are added to the
symbol table.

## Known Limitation: Optimized Data Blocks (DB)

S7-1200/1500 CPUs default to **"optimized" block access** for Data
Blocks, where TIA Portal manages variable layout internally rather
than exposing fixed byte offsets. There is no S7comm query that
reports whether a DB is optimized -- the only way to find out is to
attempt a raw offset read and see whether the CPU rejects it.

This tool's `SiemensConnector._read_db_tag()` attempts exactly that
raw read, and raises a clear, actionable error (rather than a cryptic
snap7 exception) if it's rejected, identifying the likely cause and
pointing back to this section. **Reading optimized DBs reliably is
out of scope for Phase 1** and is left as a documented extension
point. Options for a future Phase 2, in rough order of effort:

1. **Disable optimized access** on the specific DB in TIA Portal
   (DB Properties → uncheck "Optimized block access"), which makes it
   behave like the classic, fixed-offset DBs from S7-300/400 days.
   Simplest option if you control the PLC program.
2. **Symbolic reads**, matching by tag name against TIA Portal's
   internal layout -- more complex, and typically requires a
   different library/approach than raw `read_area` offset access.

## Extending to a New PLC Brand

1. Create `src/connectors/<brand>_connector.py` implementing the
   `PLCConnector` interface from `src/connectors/base_connector.py`
   (`connect`, `disconnect`, `read_tag`).
2. If the new brand uses a different address notation, add a parser
   for it (parallel to `src/address_parser.py`) and adapt
   `read_tag` to use it.
3. Wire the new connector into `src/main.py` (e.g. a `--brand` flag
   selecting which connector class to instantiate).

No changes should be needed to `symbol_table.py`, `models.py`, or the
output/JSON logic -- those are already brand-agnostic.

## Running Tests

```bash
python -m unittest discover tests
```

Tests cover address parsing and symbol table loading, and do not
require live PLC hardware or the `snap7` C library to be installed.
