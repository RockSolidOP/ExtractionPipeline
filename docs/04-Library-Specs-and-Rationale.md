# Library Specs and Rationale

This document explains the key libraries used by the project and why they are required. It focuses on direct runtime dependencies used by the code paths in this repo. Packages that are transient or primarily for development are not listed exhaustively.

## UI and App Runtime

- streamlit
  - Purpose: Web UI for upload, progress, and JSON viewing/downloading.
  - Where: `pages/Extraction_Pipeline.py`, `app/ui/components.py`.
- pydantic-settings
  - Purpose: Typed configuration management via `.env`/env vars for Azure, Reducto, Uploads, PyMuPDF.
  - Where: `app/core/settings.py`.

## Cloud Integrations

- azure-ai-documentintelligence, azure-core
  - Purpose: Analyze PDFs with Microsoft’s prebuilt tax models (e.g., 1040, Schedule C).
  - Where: `app/infrastructure/azure_service.py` uses the `DocumentIntelligenceClient`.
- reductoai (module name: `reducto`)
  - Purpose: Schema‑based document extraction with controllable OCR, chunking, and timeouts.
  - Where: `app/infrastructure/reducto_service.py` creates a client and calls `parse.run`/`extract.run`.
- httpx
  - Purpose: Underlying HTTP client for Reducto to set timeouts, retries, and explicit proxy behavior.
  - Where: `app/infrastructure/reducto_service.py` constructs `httpx.Client` with `trust_env=False` by default.

## Local Extraction and PDF Handling

- PyMuPDF (imported as `fitz`)
  - Purpose: Local text extraction and region rendering for coordinate templates; quick page counting in ML wrapper.
  - Where: `app/infrastructure/local_template_service.py`, `app/infrastructure/ml_classify_service.py`.
- pytesseract (+ system binary: Tesseract OCR)
  - Purpose: OCR fallback for regions where PyMuPDF text extraction yields nothing.
  - Where: `app/infrastructure/local_template_service.py` optional code path.
- pypdfium2
  - Purpose: Efficient page rendering to PIL images for CLIP embeddings.
  - Where: `app/resources/classifier_module/_suggester.py`.
- Pillow (PIL)
  - Purpose: Image representation and basic cropping used by embedding and OCR paths.
  - Where: `app/resources/classifier_module/_suggester.py`, `app/infrastructure/local_template_service.py`.

## ML Classification

- open-clip-torch
  - Purpose: OpenCLIP model and preprocessing to generate embeddings from page images.
  - Where: `app/resources/classifier_module/_suggester.py`.
- torch
  - Purpose: Tensor operations for OpenCLIP; CPU mode is sufficient here.
  - Where: `app/resources/classifier_module/_suggester.py`.
- faiss-cpu
  - Purpose: Approximate nearest neighbor index to look up the most similar labeled pages.
  - Where: `app/resources/classifier_module/_suggester.py`.
- numpy
  - Purpose: Array math around embeddings and FAISS search outputs.
  - Where: `app/resources/classifier_module/_suggester.py`.

## Data and Utilities (select)

- jsonschema, pydantic, pandas, pyarrow (present in requirements)
  - Purpose: General data validation/processing; not directly referenced in the core pipeline paths shown, but useful for downstream processing and Streamlit widgets.
- requests
  - Purpose: General HTTP; core pipeline primarily uses `httpx` via Reducto.

## Environment Variables

- `REDUCTO_API_KEY`
  - Used by Reducto client creation. Required to call Reducto APIs.
- `AZURE_DOC_AI_ENDPOINT`, `AZURE_DOC_AI_KEY`
  - Used to create Azure Document Intelligence client.
- `CLASSIFIER_FAISS_DIR` (optional)
  - Overrides the default location of FAISS artifacts if you are not using the embedded copies.
- Reducto advanced overrides (optional):
  - `REDUCTO_USE_PROXY`, `REDUCTO_PROXY_URL`, `REDUCTO_CONNECT_TIMEOUT`, `REDUCTO_READ_TIMEOUT`, `REDUCTO_WRITE_TIMEOUT`, `REDUCTO_POOL_TIMEOUT`, `REDUCTO_MAX_RETRIES` — see `app/infrastructure/reducto_service.py` for details.

## Optional System Packages

- Tesseract OCR
  - Needed only if you want OCR fallback for coordinate templates (`pytesseract`).
- Build tools (on Linux)
  - Some Python wheels may require basic build tools. The Dockerfile installs `build-essential`.
