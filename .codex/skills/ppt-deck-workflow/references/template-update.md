# Fixed-template updates

Use the previous approved deck or the supplied corporate template as the structural source. A reference image supplies visual direction only. Determine whether the requested pages and fields already exist before promising a fixed-template update.

Run `template-inventory --template <path>` through the workflow helper. Match requested metrics to the current page, object and old value. Use the source's units and the user's new data. Resolve ambiguous matches before applying changes. Treat labels duplicated in a title, table and chart as distinct targets when the request covers them.

For an existing deck, run `template-update --template <path> --changes <updates.json> --run-dir output/<new-quarter>`. This revision produces a fresh delivery. For new decks, use the normal outline, content and page-plan approvals. When PPTD is selected and a supplied PPTD project's fixed page roster fits the approved plan, run `prepare-render-jobs`, then `apply-pptd-template` with the same flags and the active run directory. Continue with normal visual QA and export. Use a separate run for an already-authored project.

## Editable PPTD source

Pass its project directory or its manifest. Each change names a one-based page number or the manifest's page path, an element ID and one field from inventory. Row and column offsets inside a field are zero-based.

```json
[
  {"page": 1, "element": "period", "field": "content.text", "expected": "2026 Q2", "value": "2026 Q3"},
  {"page": 2, "element": "revenue", "field": "data.rows[1][1]", "expected": 125, "value": 138},
  {"page": 2, "element": "budget", "field": "rows[1][2].text", "expected": "84%", "value": "92%"}
]
```

The result includes the updated editable project and PPTX. On the standalone revision path, ordinary category charts and changed rectangular text tables undergo native-object readback. Review longer replacement copy at the original font size and width. A rasterized number has no data slot. Page additions, chart redesigns and changes that need new geometry belong in the staged authoring workflow.

## Original PowerPoint source

Pass the original `.pptx` to preserve its masters, layouts, artwork and native objects. Use one-based slide order and the inventory's numeric `shape_id`. Table addresses use A1 notation. Chart series and points are zero-based.

```json
[
  {"slide": 1, "shape_id": 3, "expected": "Q2", "text": "Q3"},
  {"slide": 2, "shape_id": 7, "cell": "B2", "expected": "125", "value": "138"},
  {"slide": 2, "shape_id": 9, "series": 0, "point": 1, "expected": 125, "value": 138}
]
```

This route delivers a native PPTX plus a command result listing changed package parts. Each changed chart point needs a directly referenced numeric input in an embedded workbook. Text edits must fit within a single formatted run. External spreadsheets, pictures of charts and structural edits require a different source or an explicitly scoped rebuild. Importing an arbitrary PowerPoint as an editable PPTD project is a separate conversion task.
