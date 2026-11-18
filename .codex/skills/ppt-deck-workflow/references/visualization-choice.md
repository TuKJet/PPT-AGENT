# Choosing an expression for the data

Start with the question a reader should be able to answer. Put that reason and the selected encoding into each data visual's per-page plan. Choose a different encoding when the data or the question calls for it.

| Reader's question | Usual expression | Check before drawing |
| --- | --- | --- |
| How did the same measure change over time? | Line for a trend, columns for discrete periods | Keep time order, unit and missing periods explicit. |
| Which factors moved the starting figure to the ending figure? | Waterfall or signed contribution bars | Contributions must reconcile to the change. A total for each quarter alone cannot explain the drivers. |
| Which teams exceeded budget, and by how much? | Paired bars for budget vs actual, diverging bars for variances | Use a common baseline. Use a table if exact amounts are the decision input. |
| Which category leads? How is a total split? | Ranked bars for comparison; stacked bars for composition | Use a common denominator for shares; keep unlike units separate. |
| How are observations distributed or related? | Histogram for spread; scatter for two measured variables | Use source observations and disclose units. |
| Where does a request branch or change owners? | Directed process or swimlane | Use the existing diagram specification for topology. |

Record the source-backed expectation in the approved plan. A page may have several objects; each needs its own stable ID. `editability` describes what the editable PPTD deliverable must support. IMG uses the same selected design and data as visual input. Use `visual` for illustrations or diagrams without a data-object promise. Call out unsupported chart types before promising an editable workbook.

```json
{"data_visuals": [
  {
    "element_id": "revenue", "relationship": "change_over_time", "encoding": "line",
    "reason": "Compare the direction of quarterly revenue in millions.",
    "editability": "native_chart",
    "series": [{"name": "Revenue", "categories": ["Q1", "Q2"], "values": [12, 15]}]
  },
  {
    "element_id": "budget", "relationship": "budget_execution", "encoding": "table",
    "reason": "Finance needs the exact approved and actual amounts for each team.",
    "editability": "native_table", "cells": [["Team", "Budget", "Actual"], ["A", "12", "15"]]
  }
]}
```

Keep categories and units aligned to the source. A missing value is `null`; an observed zero is `0`. For native tables, record the exact displayed text, including units and precision. The PPTD exporter verifies declared native objects by page and element ID, series and workbook data, or table dimensions and cells.
