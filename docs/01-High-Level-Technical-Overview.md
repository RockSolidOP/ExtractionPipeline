# Extraction Pipeline — High‑Level Technical Overview

This project provides a Streamlit UI that classifies pages of a PDF and routes them to the appropriate extraction engine, then aggregates results into a single JSON artifact. The UI is thin; orchestration lives in the application layer.

- Inputs: one uploaded PDF per run.
- Core steps: ML page classification → page pairing and routing → extraction (Azure/Reducto/local template) → combined JSON.
- Outputs: a compact JSON containing the page plan and per‑job results, downloadable from the UI.

## Architecture

- UI (Streamlit)
  - `pages/Extraction_Pipeline.py` uploads a PDF and calls `app/application/pipeline.py:run_pipeline`.
- Application (use cases)
  - Planning: `app/application/planning.py:build_page_plan` (pair P1/P2, choose models).
  - Pipeline: `app/application/pipeline.py:run_pipeline` (classify → plan → execute → aggregate → post-process).
- Infrastructure (adapters)
  - ML classification: `app/infrastructure/ml_classify_service.py` (OpenCLIP + FAISS).
  - Azure Document Intelligence: `app/infrastructure/azure_service.py`.
  - Reducto schema: `app/infrastructure/reducto_service.py` and `reducto_schema_registry.py`.
  - Local coordinate templates: `app/infrastructure/local_template_service.py`.
- Plugins (post-processing)
  - `app/plugins/post_processors/azure/form_1040.py`, `form_schedule_c.py` via `app/plugins/registry.py`.
- Configuration
  - `app/core/settings.py` (Pydantic Settings). Cloud keys via `.env`.
- Storage
  - Uploads under `uploads/` via `app/infrastructure/storage/uploads.py`.

## Data Flow

1) Upload
- User selects a PDF. The app saves it to `uploads/` with a timestamped filename.

2) Page Classification (ML)
- Each PDF page is embedded via OpenCLIP and retrieved against a FAISS index.
- The top suggestion becomes the page’s label; the index also encodes “base family” (e.g., 1040, Schedule_C) and occasional page‑in‑form hints.

3) Planning and Routing
- Pages are grouped by base family; P1 ↔ P2 pages are paired when present.
- For each page or pair:
  - If the label is in `SKIP_LABELS`, it is skipped.
  - Otherwise, a model ID is chosen from `ML_LABEL_MODEL_MAP` (e.g., Azure prebuilt 1040; Reducto schema; or a local template).

4) Extraction
- Azure: prebuilt models are invoked via `azure-ai-documentintelligence`.
- Reducto schema: the document is uploaded; `extract.run` executes against the selected JSON Schema and a system prompt.
- Local template: a coordinate template is located under `local-templates/` using the form key and read via PyMuPDF with OCR fallback.

5) Aggregation
- A compact JSON is assembled containing:
  - `page_plan`: the decision log (pages, labels, chosen model, analyze/skip).
  - `runs`: one entry per executed job with `result` or `error`.
- The UI displays and offers a download button.

## Key Responsibilities

- `pages/Extraction_Pipeline.py` — UI; calls `run_pipeline` and renders outputs.
- `app/application/pipeline.py` — pipeline orchestration.
- `app/application/planning.py` — plan construction.
- `app/infrastructure/*` — adapters for ML, Azure, Reducto, local templates, storage.
- `app/plugins/*` — post-processors and registry.

## Configuration Surfaces

- Cloud credentials: `REDUCTO_API_KEY`, `AZURE_DOC_AI_ENDPOINT`, `AZURE_DOC_AI_KEY` via `.env`.
- Routing: `app/application/routing.py` (label → model).
- Reducto behavior: options surfaced via `app/core/settings.py`.
- Azure behavior: prebuilt model ids via `app/core/settings.py`.

## Outputs and Persistence

- Combined result JSON is rendered in the UI and downloadable (file name `azure_pipeline_<pdf-stem>.json`).
- Uploads are stored under `uploads/`. Cleanup helpers live in `app/infrastructure/storage/uploads.py`.

## Limitations and Notes

- The ML classifier relies on a prebuilt FAISS index; it does not train on the fly.
- The local coordinate template mode requires PyMuPDF and, for OCR fallback, Tesseract installed on the host.
- Some 1040 schedules may be intentionally skipped via `SKIP_LABELS` until routing and post‑processing are finalized.
