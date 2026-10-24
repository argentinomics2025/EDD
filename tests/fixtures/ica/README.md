# Source-cell regression fixtures

These JSON files are exact cell-value extractions from the two XLS attachments
supplied by the user. They are not synthetic workbooks and are not independently
verified economic oracles. `null` represents an empty Excel cell. Positions in
the arrays retain original row/column coordinates. Original XLS files are not
modified or included in the checkout.

- 2026-01-cells.json: original ica_cuadros_19_02_26.xls,
  SHA256 c1c4bf98e92969972082cc73e77ad7d2c9dda75f893dcef16504ef2300bfad99;
  sheets c10/c12/c19, edition 2026-02-19.
- 2026-02-cells.json: original ica_cuadros_19_03_26.xls,
  SHA256 2ecad32e0682b24c7e4cea4d3e0e0cefdf6ac2007d12337d44b021fc08517937;
  sheets c12/c14/c21, edition 2026-03-19.

Snapshot regressions run without the original files. OriginalWorkbookTests
separately reads the actual XLS, verifies these hashes, edition metadata and
number formats, and runs the four validations. Supply the originals under
ICA_OFFICIAL_FIXTURES_DIR (recursive lookup), or use /workspace/attachments.
When originals are absent that class explicitly skips; no downloader is used.
Neither path invokes publication, HTTP or database functions. No passing test
unlocks writes or authorizes promotion to production.

Final review also compares every snapshot cell directly with xlrd's original
workbook cells (without the application parsers), checks an independently
inspected coordinate inventory of all rubro amounts exactly once, and uses
Peru's January import amount from c16 as a cross-table nonzero reference.
These are independent controls of extraction, not external economic certification.
