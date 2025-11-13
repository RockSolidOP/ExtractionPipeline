# Extraction Pipeline — High‑Level Technical Overview

This project provides a Streamlit UI that classifies pages of a PDF and routes them to the appropriate extraction engine, then aggregates results into a single JSON artifact.

- Inputs: one uploaded PDF per run.
- Core steps: ML page classification → page pairing and routing → extraction (Azure/Reducto/local template) → combined JSON.
- Outputs: a compact JSON containing the page plan and per‑job results, downloadable from the UI.

## Architecture

- UI (Streamlit)
  - Single page at `pages/Extraction_Pipeline.py` renders upload, shows a plan, runs jobs, and downloads final JSON.
- Services
  - ML classification: OpenCLIP + FAISS k‑NN over a curated index to assign labels per page.
  - Azure Document Intelligence: prebuilt tax models (e.g., 1040, Schedule C) for document field extraction.
  - Reducto (schema‑based): structured extraction against JSON Schemas stored under `reducto_schema/`.
  - Local coordinate templates: PyMuPDF + optional OCR to read specific fields defined by JSON templates.
- Configuration
  - Label→model routing and skip list in `app/config_classifier_ml_labels.py`.
  - Extraction knobs for Reducto and Azure in `app/config.py`.
  - Cloud keys via `.env`: `REDUCTO_API_KEY`, `AZURE_DOC_AI_ENDPOINT`, `AZURE_DOC_AI_KEY`.
- Storage
  - Uploaded files are persisted under the repository‑level `uploads/` folder.

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

- `pages/Extraction_Pipeline.py` — orchestrates the pipeline: classification → planning → execution → aggregation.
- `app/services/ml_classify_service.py` — wraps the embedded classifier module for per‑page labeling.
- `app/services/azure_service.py` — Azure client creation and result normalization.
- `app/services/reducto_service.py` — Reducto client configuration, timeouts, and helpers.
- `app/services/reducto_schema_registry.py` — loads JSON Schemas and default prompts.
- `app/services/local_template_service.py` — coordinate template extraction with PyMuPDF and OCR fallback.

## Configuration Surfaces

- Cloud credentials
  - `REDUCTO_API_KEY`, `AZURE_DOC_AI_ENDPOINT`, `AZURE_DOC_AI_KEY` via `.env`.
- Routing
  - Edit `app/config_classifier_ml_labels.py` to add or change label→model mappings, or to skip certain labels.
- Reducto behavior
  - `app/config.py` exposes OPTIONS, ADVANCED_OPTIONS, EXPERIMENTAL_OPTIONS for OCR/chunking and page‑range control.
- Azure behavior
  - Default model IDs under `AZURE_CONFIG` in `app/config.py`.

## Outputs and Persistence

- Combined result JSON is rendered in the UI and downloadable (file name `azure_pipeline_<pdf-stem>.json`).
- Uploads are stored under `uploads/`. A periodic cleanup policy is available in `app/utils/storage.py` and can be used by future background jobs.

## Limitations and Notes

- The ML classifier relies on a prebuilt FAISS index; it does not train on the fly.
- The local coordinate template mode requires PyMuPDF and, for OCR fallback, Tesseract installed on the host.
- Some 1040 schedules may be intentionally skipped via `SKIP_LABELS` until routing and post‑processing are finalized.

