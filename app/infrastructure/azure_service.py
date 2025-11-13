from __future__ import annotations

import json
from pathlib import Path

from azure.core.credentials import AzureKeyCredential

try:
    from azure.ai.documentintelligence import DocumentIntelligenceClient  # type: ignore
    HAS_DOCINTEL = True
except Exception:
    HAS_DOCINTEL = False
from app.core.settings import settings


def create_docint_client() -> DocumentIntelligenceClient:
    if not HAS_DOCINTEL:
        raise RuntimeError(
            "azure-ai-documentintelligence is not installed. Add it to requirements and pip install."
        )
    endpoint = settings.azure.endpoint
    key = settings.azure.key
    if not endpoint or not key:
        raise RuntimeError("AZURE_DOC_AI_ENDPOINT or AZURE_DOC_AI_KEY not set in .env")
    return DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(key))


def parse_with_azure_docint(
    file_path: Path,
    page_number: int | None = None,
    model_id: str | None = None,
    pages: str | None = None,
):
    client = create_docint_client()
    _model_id = model_id or settings.azure.prebuilt_ids.document
    _pages = pages or (str(page_number) if page_number is not None else None)
    with open(file_path, "rb") as f:
        if _pages:
            poller = client.begin_analyze_document(_model_id, body=f, pages=_pages)
        else:
            poller = client.begin_analyze_document(_model_id, body=f)
    return poller.result()


def _to_native(obj):
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (bytes, bytearray)):
        try:
            import base64
            return base64.b64encode(obj).decode("ascii")
        except Exception:
            return str(obj)
    if isinstance(obj, dict):
        return {str(k): _to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_native(v) for v in obj]
    for meth in ("to_dict", "as_dict"):
        if hasattr(obj, meth) and callable(getattr(obj, meth)):
            try:
                return _to_native(getattr(obj, meth)())
            except Exception:
                pass
    if hasattr(obj, "__dict__"):
        try:
            data = {k: v for k, v in vars(obj).items() if not k.startswith("_")}
            return _to_native(data)
        except Exception:
            return str(obj)
    return str(obj)


def azure_to_dict(result) -> dict:
    for meth in ("to_dict", "as_dict"):
        if hasattr(result, meth) and callable(getattr(result, meth)):
            try:
                out = getattr(result, meth)()
                return _to_native(out)
            except Exception:
                pass
    if hasattr(result, "to_json") and callable(getattr(result, "to_json")):
        try:
            return json.loads(result.to_json())
        except Exception:
            pass
    return _to_native(result)


def azure_fields_to_dict(result):
    try:
        d = azure_to_dict(result)
        docs = d.get("documents") or []
        if not docs:
            return {}
        if len(docs) == 1:
            return docs[0].get("fields") or {}
        out = []
        for i, doc in enumerate(docs):
            out.append(
                {
                    "index": i,
                    "docType": doc.get("doc_type") or doc.get("docType"),
                    "fields": doc.get("fields") or {},
                }
            )
        return out
    except Exception:
        try:
            docs = getattr(result, "documents", []) or []
            if not docs:
                return {}
            if len(docs) == 1:
                return getattr(docs[0], "fields", {}) or {}
            out = []
            for i, doc in enumerate(docs):
                out.append(
                    {
                        "index": i,
                        "docType": getattr(doc, "doc_type", None),
                        "fields": getattr(doc, "fields", {}) or {},
                    }
                )
            return out
        except Exception:
            return {}

