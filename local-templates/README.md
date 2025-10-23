Local Coordinate Templates
==========================

Purpose
- Store coordinate-based extraction templates used by the local template service
  for integration testing without Azure.

Naming Convention
- Use the pattern: <profile>_<Form Key>_template.json
- Examples:
  - A7SDEPR3_Form 1040 Individual_template.json

Schema
- Top-level JSON: an array of field definitions.
- Each field:
  {
    "label": "First name",
    "type": "text" | "checkbox",
    "page": 1,                         // 1-based page number
    "rect": [x0, y0, x1, y1]           // page coordinate rectangle
  }

Lookup
- The service searches ONLY this folder (`ExtractionPipeline/local-templates`). There is no fallback.

Fallback
- If no coordinate template is found, the service raises an error and the pipeline marks the job as failed (no skeleton output).
