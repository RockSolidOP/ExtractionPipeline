# Installation Guide — Local Setup

This guide helps you run the Streamlit app locally for end‑to‑end classification and extraction.

## Prerequisites

- Python 3.10–3.13 (project tested with 3.13)
- macOS, Linux, or WSL2 on Windows
- Access tokens and endpoints for:
  - Reducto: `REDUCTO_API_KEY`
  - Azure Document Intelligence: `AZURE_DOC_AI_ENDPOINT`, `AZURE_DOC_AI_KEY`
- Optional (only for local coordinate template extraction):
  - Tesseract OCR binary installed on your OS if you want OCR fallback
    - macOS: `brew install tesseract`
    - Ubuntu/Debian: `sudo apt-get install tesseract-ocr`

## 1) Create a virtual environment

```
python -m venv .venv
source .venv/bin/activate
```

## 2) Install dependencies

```
pip install --upgrade pip
pip install -r ExtractionPipeline/requirements.txt
```

Notes
- The ML classifier (OpenCLIP + FAISS) installs CPU wheels by default.
- If your environment needs different wheels (e.g., Apple Silicon), adjust pins or install from compatible wheels.

## 3) Provide environment variables

Create a `.env` file at the repository root (same folder as `ExtractionPipeline/`) with:

```
REDUCTO_API_KEY=your_reducto_api_key
AZURE_DOC_AI_ENDPOINT=https://<your-azure-endpoint>.cognitiveservices.azure.com/
AZURE_DOC_AI_KEY=your_azure_key
```

Optional proxy variables (only if required by your network tooling):

```
HTTP_PROXY=http://user:pass@host:port
HTTPS_PROXY=http://user:pass@host:port
NO_PROXY=localhost,127.0.0.1
```

## 4) Run the Streamlit app

From the repository root:

```
streamlit run ExtractionPipeline/pages/Extraction_Pipeline.py
```

- Open http://localhost:8501
- Upload a PDF; you’ll see classification, a plan, then run extraction jobs.

## 5) Sanity checks

- Verify that `.env` is loaded:
  - The app will raise if `REDUCTO_API_KEY` or Azure variables are missing when those paths run.
- If ML classification fails due to missing artifacts:
  - The embedded FAISS data lives in `ExtractionPipeline/app/resources/classifier_module/data/faiss/`.
  - You can also set `CLASSIFIER_FAISS_DIR=/path/to/dataset/v1/faiss` to use external artifacts.
- If local template extraction raises an error:
  - Ensure a matching `*_template.json` exists under `ExtractionPipeline/local-templates/`.
  - Install PyMuPDF and optionally Tesseract OCR (see prerequisites).

## Docker (optional)

A `Dockerfile` is provided at `ExtractionPipeline/Dockerfile`. It installs Python deps and exposes port 8501.

Build:
```
cd ExtractionPipeline
docker build -t extraction-pipeline:latest .
```
Run (override entry to the Streamlit page used in this repo):
```
docker run --rm -it \
  --env-file ../.env \
  -p 8501:8501 \
  extraction-pipeline:latest \
  streamlit run ExtractionPipeline/pages/Extraction_Pipeline.py --server.address=0.0.0.0 --server.port=8501
```

## Troubleshooting

- Azure credentials missing
  - `AZURE_DOC_AI_ENDPOINT or AZURE_DOC_AI_KEY not set` → populate `.env`.
- Reducto API key missing
  - `api_key must be set` or similar → populate `.env` with `REDUCTO_API_KEY`.
- Proxy issues / timeouts
  - If behind a corporate proxy, set proxy variables or disable their use for Reducto by leaving `REDUCTO_USE_PROXY` unset. The Reducto client disables env proxy usage unless explicitly configured.
- Missing Tesseract (local template OCR)
  - OCR fallback won’t run without the system binary; install it or rely on PyMuPDF text extraction only.

