# Extraction Pipeline — Low‑Level Technical Design

This document maps the codebase into concrete responsibilities, data models, and call paths with file references to entry points and key functions.

## UI Orchestration

- Entry point: `ExtractionPipeline/pages/Extraction_Pipeline.py:301`
  - `run()` sets up the page, handles upload, executes the pipeline, and renders outputs.
  - Dataclasses used:
    - `ClassifiedPage` — `ExtractionPipeline/pages/Extraction_Pipeline.py:57`
    - `AzureJob` — `ExtractionPipeline/pages/Extraction_Pipeline.py:71`
    - `PagePlan` — `ExtractionPipeline/pages/Extraction_Pipeline.py:81`

- Planning: `_build_plan_generic(classified)` — `ExtractionPipeline/pages/Extraction_Pipeline.py:103`
  - Groups pages by base_label, infers P1/P2, pairs when possible, and creates Azure jobs for analyzable items.
  - Produces two structures:
    - `jobs: List[AzureJob]` — execution units (model_id + pages span).
    - `plan: List[PagePlan]` — per‑page decisions (analyze vs skip, model used, grouping IDs).

- Analysis dispatcher: `_analyze_with_azure(...)` — `ExtractionPipeline/pages/Extraction_Pipeline.py:246`
  - Routes by `model_id` prefix:
    - `local-template:<Form Key|auto>` → `app/services/local_template_service.analyze_form_with_template`
    - `reducto:schema:<key|auto>` → `app/services/reducto_schema_registry.get_schema_config_for_key` + `reducto_service.extract_with_schema`
    - default → Azure Document Intelligence via `app/services/azure_service.parse_with_azure_docint`

- Aggregation
  - Azure outputs are normalized to a field‑centric dict via `azure_fields_to_dict`.
  - Local template and Reducto schema outputs are included verbatim under each run.
  - Combined JSON includes: `document`, `page_plan`, and `runs` (per job `ok/error` and `result`).

## ML Classification (FAISS + OpenCLIP)

- Service wrapper: `ExtractionPipeline/app/services/ml_classify_service.py:54`
  - `classify_document_ml(pdf_path, topk=1, root=None)`
    - Uses PyMuPDF to count pages.
    - For each page, calls the embedded classifier module (`classifier_module`) to get the top label or top‑k suggestions.
    - Normalizes label strings to a consistent underscore style for routing.
  - `classify_to_result_ml(...)` returns a UI‑friendly summary payload compatible with older regex classifier shapes.

- Embedded module: `ExtractionPipeline/app/resources/classifier_module/api.py`
  - `get_suggestions(pdf_path, page, topk=5, root=None)` — returns ranked neighbors from FAISS with labels and metadata.
  - `get_label(...)` — top suggestion (with base_label and page_in_form hints when available).
  - `classify_pdf(...)` — convenience for all pages.

- Core search logic: `ExtractionPipeline/app/resources/classifier_module/_suggester.py`
  - OpenCLIP model creation and preprocessing on CPU.
  - Page rendering via `pypdfium2` → PIL image → OpenCLIP embedding.
  - FAISS index search using artifacts under `classifier_module/data/faiss/` by default, or via `CLASSIFIER_FAISS_DIR`.

## Azure Document Intelligence

- Client and helpers: `ExtractionPipeline/app/services/azure_service.py`
  - `create_azure_client()` — `:20` reads `AZURE_DOC_AI_ENDPOINT` and `AZURE_DOC_AI_KEY` from env/.env.
  - `parse_with_azure(file_path, page_number=None, model_id=None, pages=None)` — `:45`
  - `parse_with_azure_docint(...)` — `:83` (new SDK mirror) used by the UI.
  - `azure_to_dict(result)` — `:139` best‑effort conversion to JSON‑serializable dict.
  - `azure_fields_to_dict(result)` — `:162` extracts `documents[].fields` as a compact dict/list.

- Config: `ExtractionPipeline/app/config.py`
  - `AZURE_CONFIG` defines default model IDs (e.g., 1040 main, Schedule C).

## Reducto (Schema‑Based Extraction)

- Client and helpers: `ExtractionPipeline/app/services/reducto_service.py`
  - `create_client(...)` — `:15` creates a `reducto.Reducto` client with explicit `httpx` timeouts and proxy controls via env overrides.
  - `parse_document*` — page and range helpers around `client.parse.run`.
  - `extract_with_schema(...)` — `:120` uploads once and executes `client.extract.run` with schema + system prompt.

- Schema registry: `ExtractionPipeline/app/services/reducto_schema_registry.py`
  - `get_schema_config_for_key(key)` — `:89` finds the most recent `*_schema.json` containing the key under `reducto_schema/`, returns `{schema, system_prompt, schema_path, key}`.
  - Default prompts tailored for specific keys (e.g., asset schedules) with strict schema adherence.

## Local Coordinate Templates (PyMuPDF + OCR)

- Service: `ExtractionPipeline/app/services/local_template_service.py`
  - `find_coordinate_template(form_key)` — `:48` finds most recent matching `*_template.json` under `local-templates/`.
  - `analyze_form_with_template(file_path, pages, form_key, template_path=None)` — `:208` loads the coordinate template and extracts values.
  - Text extraction via PyMuPDF `get_text(clip=...)`; OCR fallback via Tesseract when available; checkbox heuristic via central pixel density.

- Template format
  - Array of fields: `{ label, type: text|checkbox, page, rect: [x0,y0,x1,y1] }`.
  - Naming convention: `<profile>_<Form Key>_template.json`; the service selects the latest matching file.

## Routing and Skip Logic

- Mapping: `ExtractionPipeline/app/config_classifier_ml_labels.py`
  - `ML_LABEL_MODEL_MAP` maps exact ML labels to model IDs.
    - Examples: 1040 P1/P2 → prebuilt 1040; Schedule C → prebuilt Schedule C; asset reports → `reducto:schema:auto`.
  - `SKIP_LABELS` lists labels to ignore (no job creation).

## Utilities and UI helpers

- Uploads and cleanup: `ExtractionPipeline/app/utils/storage.py`
  - `save_uploaded_file(...)` — `:26` persists Streamlit’s `UploadedFile` into `uploads/` with a timestamped name.
  - `cleanup_uploads(...)` — `:70` supports age/size/count caps.

- UI components: `ExtractionPipeline/app/ui/components.py`
  - `file_uploader(...)` — `:33` consistent wrapper for Streamlit’s uploader.
  - `download_json_button(...)` — `:41` standard JSON download widget.
  - `pages_list_from_spec(...)` — `:86` helper for Azure‑style `pages` strings.

## Error Handling and Timeouts

- Reducto client uses explicit `httpx.Timeout` and disables `trust_env` unless a proxy is explicitly provided via env or parameters.
- Azure calls are wrapped so results are normalized; exceptions are captured per job and surfaced in the combined JSON.
- Local templates raise on missing templates or when no fields yield data; the UI records the error in the run entry.

## File/Folder Overview

- `pages/Extraction_Pipeline.py` — Streamlit page running the pipeline.
- `app/services/` — integration services: `azure_service.py`, `reducto_service.py`, `local_template_service.py`, `reducto_schema_registry.py`, `ml_classify_service.py`.
- `app/resources/classifier_module/` — embedded FAISS + CLIP classification artifacts and APIs.
- `local-templates/` — JSON coordinate templates.
- `reducto_schema/` — JSON Schemas for Reducto extraction flows.
- `uploads/` — persisted uploads (git‑ignored).

