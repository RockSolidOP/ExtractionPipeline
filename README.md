# Extraction Pipeline Setup Guide

A Streamlit app that classifies PDF pages and routes them to the right extraction engine (Azure Document Intelligence, Reducto schema, or a local coordinate template), then aggregates outputs into a single JSON. This README covers local setup, environment configuration, running the app, and Docker.

## Requirements

- Python 3.10–3.13 (tested with 3.13)
- macOS/Linux/WSL2
- Internet access to Reducto API and Azure Document Intelligence

## Environment Variables

Create a `.env` file in the project root with the following keys:

```
REDUCTO_API_KEY=your_reducto_api_key
AZURE_DOC_AI_ENDPOINT=https://<your-azure-endpoint>.cognitiveservices.azure.com/
AZURE_DOC_AI_KEY=your_azure_key
```

Optional (only if your network requires an outbound proxy):

```
# Example format if needed by your network tooling (NOT required by default)
HTTP_PROXY=http://user:pass@host:port
HTTPS_PROXY=http://user:pass@host:port
NO_PROXY=localhost,127.0.0.1
```

Note: The app’s Reducto client uses an explicit httpx client with `trust_env=False`. The included smoke test can use a hardcoded proxy in-code (see testing section below). If you need full app-wide proxy support, see “Proxy Options”.

## Local Setup

1) Create and activate a virtualenv

```
python -m venv .venv
source .venv/bin/activate
```

2) Install dependencies

```
pip install -r requirements.txt
```

3) Verify environment loads

```
python -c "from dotenv import load_dotenv; import os; load_dotenv(); print(bool(os.getenv('REDUCTO_API_KEY')), os.getenv('AZURE_DOC_AI_ENDPOINT'))"
```

## Run the Streamlit App

Recommended (modular entrypoint):

```
streamlit run ExtractionPipeline/pages/Extraction_Pipeline.py 
```


- Open http://localhost:8501
- Upload a PDF and try Reducto and Azure analysis

Required environment variables (names only): `REDUCTO_API_KEY`, `AZURE_DOC_AI_ENDPOINT`, `AZURE_DOC_AI_KEY`.

Notes:
- Keep your `.env` untracked (see `.gitignore`).
- Configuration is centralized via `app/core/settings.py` (Pydantic Settings). Environment keys are loaded from `.env`.

## Quick Smoke Test (CLI)

If you keep CLI utilities, ensure they import from `app/infrastructure` and `app/application` modules. Sample tests can classify a local PDF using the embedded classifier and run the pipeline.


### Rancher Desktop (Windows)

- Install Rancher Desktop (Step-by-Step):
  - https://trten.sharepoint.com/sites/intr-docker/SitePages/Install-Rancher-Desktop(-Step-by-Step.aspx
- If WSL2 is not installed yet (Windows):
  - https://learn.microsoft.com/windows/wsl/install

Notes for Rancher Desktop on Windows:
- Container runtime: Select `dockerd (moby)` in Rancher Desktop → Settings → Container Engine. This ensures the `docker` CLI works as expected. If you previously used `containerd`, switch to `dockerd` and restart Rancher Desktop.
- Kubernetes: Disable Kubernetes in Rancher Desktop unless you specifically need it, to avoid port/resource conflicts.
- WSL2 backend: Ensure WSL2 is installed and enabled; set default with `wsl --set-default-version 2`. A reboot may be required after enabling Windows features.

Troubleshooting (Rancher Desktop + WSL2):
- `docker: command not found` or `Cannot connect to the Docker daemon`:
  - Verify Rancher Desktop is running and the runtime is set to `dockerd (moby)`.
  - Close and reopen your terminal after switching runtimes.
- Images/containers not visible after switching runtime:
  - `containerd` and `dockerd` keep separate stores. Re-pull images after switching, or stick to `dockerd` for this project.
- WSL errors (e.g., 0x80370102):
  - Ensure virtualization is enabled in BIOS, and Windows features "Virtual Machine Platform" and "Windows Subsystem for Linux" are enabled. Then run `wsl --install` and reboot.
- Network/proxy issues:
  - If behind a corporate proxy, configure proxy in Rancher Desktop (Settings → Network) and/or use `.env` as described in Proxy Options.


## Docker (recommended for “it just runs”)

Build the image:

```
docker build -t reducto-azure-ui:latest .
```

Run the app (env vars provided at runtime, not baked into the image):

```
docker run --rm -it \
  --env-file .env \
  -p 8501:8501 \
  reducto-azure-ui:latest
```

Optionally mount local folders for persistence:

```
docker run --rm -it \
  --env-file .env \
  -p 8501:8501 \
  -v "$(pwd)/uploads:/app/uploads" \
  -v "$(pwd)/testing_files:/app/testing_files" \
  reducto-azure-ui:latest
```

Open http://localhost:8501 in your browser.


## Proxy Options (Not required as of now)

- Test script proxy: `testing_files/reducto_files/test_reducto.py` includes an optional proxy host; set `USE_PROXY = True` and `PROXY_HOST = "host:port"`. It DNS-checks the host and falls back to direct if unresolved.
- App-wide proxy: The Reducto client is created in `app/infrastructure/reducto_service.py`. It disables environment proxy variables by default (`trust_env=False`) and only uses a proxy if passed explicitly or configured in settings. If you need global proxy via env vars, provide `REDUCTO_USE_PROXY=true` and `REDUCTO_PROXY_URL=...` in `.env` (see `app/core/settings.py`).



## Troubleshooting

- Missing API key: `reducto.ReductoError: api_key must be set` → Ensure `.env` contains `REDUCTO_API_KEY` and that you run from the project root so `load_dotenv()` finds it.
- Azure credentials not set: `AZURE_DOC_AI_ENDPOINT or AZURE_DOC_AI_KEY not set` → Add both to `.env`.
- Proxy errors / hangs: If you see `httpx.ConnectError` or timeouts and you’re off VPN, disable the proxy in the test script or ensure the proxy hostname resolves. The app path uses bounded timeouts and does not inherit env proxies by default.
- Different behavior across folders: Confirm same venv and package versions (`pip freeze`), same `.env` values, and that you’re importing the intended files (print `module.__file__`).

## Project Layout

- UI
  - `pages/Extraction_Pipeline.py` — Thin Streamlit page. Upload → calls `app/application/pipeline.py` → renders.
  - `app/ui/components.py` — UI helpers (upload, download button, minor utilities).
- Core
  - `app/core/settings.py` — Typed Pydantic Settings (Azure, Reducto, Uploads, PyMuPDF).
- Domain
  - `app/domain/models.py` — ClassifiedPage, AzureJob, PagePlan dataclasses.
- Application (use cases)
  - `app/application/planning.py` — build_page_plan(classified).
  - `app/application/pipeline.py` — run_pipeline(pdf) orchestrates classify → plan → execute → aggregate (+ post-process).
- Infrastructure (adapters)
  - `app/infrastructure/azure_service.py` — Azure client + analyze + serialization helpers.
  - `app/infrastructure/reducto_service.py` — Reducto client + parse/extract helpers.
  - `app/infrastructure/reducto_schema_registry.py` — schema discovery and prompts.
  - `app/infrastructure/local_template_service.py` — PyMuPDF+OCR local template extraction.
  - `app/infrastructure/ml_classify_service.py` — ML classifier wrapper (FAISS + CLIP).
  - `app/infrastructure/storage/uploads.py` — uploads persistence and cleanup.
- Plugins
  - `app/plugins/registry.py` — post-processor registry (select/run).
  - `app/plugins/post_processors/azure/form_1040.py` — 1040 mapper.
  - `app/plugins/post_processors/azure/form_schedule_c.py` — Schedule C mapper.
- Resources
  - `app/resources/classifier_module/...` — embedded classifier artifacts.
- Other
  - `requirements.txt`, `Dockerfile`, `.dockerignore`
  - `docs/` — technical overview and design notes (updated to current layout).

## License

Proprietary code. Do not redistribute without permission.
