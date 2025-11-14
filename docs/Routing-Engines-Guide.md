# Routing Engines Guide

This guide explains how to route ML-classified pages to Azure, Reducto (schema), or Local Template extraction without touching the UI. All routing is configuration-driven and handled by the application layer.

## Overview
- Edit routing in `app/application/routing.py` via `ML_LABEL_MODEL_MAP`.
- The pipeline reads these selectors and dispatches automatically.
- Required assets live under `reducto_schema/` (for Reducto) and `local-templates/` (for Local Template).

## Where To Edit
- Routing map: `app/application/routing.py`
- Azure settings (endpoint, key, prebuilt IDs): `app/core/settings.py`
- Reducto schemas: `reducto_schema/` (files must end with `_schema.json`)
- Local templates: `local-templates/` (files must end with `_template.json`)

## Model Selectors (values in ML_LABEL_MODEL_MAP)
- Azure prebuilt model ID (string)
  - Example: `settings.azure.prebuilt_ids.form_1040` or literal ID like `"prebuilt-tax.us.1040"`
- Local Template: `local-template:<key>` or `local-template:auto`
- Reducto Schema: `reducto:schema:<key>` or `reducto:schema:auto`

## Examples

### Route to Azure (prebuilt)
```python
from app.core.settings import settings

ML_LABEL_MODEL_MAP.update({
    "Form_1040_P1": settings.azure.prebuilt_ids.form_1040,
    "Form_1040_P2": settings.azure.prebuilt_ids.form_1040,
    "Schedule_C_P1": settings.azure.prebuilt_ids.schedule_c,
    "Schedule_C_P2": settings.azure.prebuilt_ids.schedule_c,
})
```

### Route to Local Template
```python
ML_LABEL_MODEL_MAP.update({
    # Infer key from label (e.g., "Form_1040_P1" -> "Form_1040")
    "Form_1040_P1": "local-template:auto",
    # Or specify a template key explicitly
    "Form_1040_P2": "local-template:Form_1040",
})
```
Ensure a coordinate template exists under `local-templates/` and its filename contains the template key and ends with `_template.json`. The most recent matching file is used.

### Route to Reducto Schema
```python
ML_LABEL_MODEL_MAP.update({
    # Infer schema key from label
    "Federal_Asset_Report_Schedule_C_P1": "reducto:schema:auto",
    # Or specify an explicit schema key
    "Federal_Asset_Report_Schedule_C_P2": "reducto:schema:Asset_Schedule_C",
})
```
Matching rule (simple and important):
- The "key" must be a contiguous substring of the schema filename stem (case‑insensitive), and the file must end with `_schema.json`.
- Example: file `reducto_schema/Federal_Asset_Report_Schedule_C_schema.json`
  - Keys that match: `Federal_Asset_Report_Schedule_C`, `Schedule_C`
  - Key that does NOT match: `Asset_Schedule_C` (not contiguous in that filename)

Tip: Prefer `reducto:schema:auto` so the base key is derived from the label (e.g., `Federal_Asset_Report_Schedule_C_P2` → `Federal_Asset_Report_Schedule_C`).

## How "auto" Key Derivation Works
- The pipeline strips common page suffixes like `_P1`, `_P2`, `_PAGE_1`, `_PG_1` from the ML label to get a base key.
  - Example: `Form_1040_P1` → base key `Form_1040`.
- `local-template:auto` → searches `local-templates/*<base key>*_template.json`.
- `reducto:schema:auto` → searches `reducto_schema/*<base key>*_schema.json`.

## Base-Label Fallback (Planning)
- Planning tries exact label first, then base label (and common `_P1`/`_P2` variants).
- You can map a base family once to cover all variants, e.g.:
```python
ML_LABEL_MODEL_MAP.update({
    "Form_1040": settings.azure.prebuilt_ids.form_1040,
})
```

## Post-Processing (Optional)
- Configure post-processors in `app/plugins/registry.py`:
```python
POSTPROCESSOR_BY_BASE_LABEL.update({
    "Form_1040": "app.plugins.post_processors.azure.form_1040:postprocess_combined",
    "Schedule_C": "app.plugins.post_processors.azure.form_schedule_c:postprocess_combined",
})
```

## Preview & Verification (No UI Logic)
- The UI calls `preview_pipeline(pdf_path)` to show:
  - Classification: list of `{file_name, page, label, base_label, page_in_form}`
  - Page plan: list of per-page decisions `{page, label, status, model_id, job_id, ...}`
- On run, `run_pipeline(pdf_path)` executes jobs and returns combined output + timings.

## Quick Checklist
- [ ] Update label → model selector in `app/application/routing.py`.
- [ ] Azure: ensure endpoint/key in `.env`; edit `app/core/settings.py` if you need different prebuilt IDs.
- [ ] Local Template: add `*_template.json` under `local-templates/` with the form key in the filename.
- [ ] Reducto Schema: add `*_schema.json` under `reducto_schema/` with the schema key in the filename.
- [ ] (Optional) Post-processing: update `app/plugins/registry.py` mappings.

## Troubleshooting
- Missing Azure credentials: set `AZURE_DOC_AI_ENDPOINT` and `AZURE_DOC_AI_KEY` in `.env`.
- No local-template data extracted: verify coordinates, page numbers, and presence of PyMuPDF/Tesseract.
- Reducto schema not found: confirm filename contains the key and ends with `_schema.json`.
- Nothing runs: confirm labels from the classifier match keys in `ML_LABEL_MODEL_MAP`.
