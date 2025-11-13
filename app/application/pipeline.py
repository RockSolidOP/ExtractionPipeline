from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

from app.application.planning import build_page_plan
from app.domain.models import ClassifiedPage, AzureJob, PagePlan


def _derive_form_key_from_label_hint(label_hint: str) -> Optional[str]:
    """Best-effort derive a template key from ML label(s).

    Examples: "Form_1040_P1" → "Form_1040"; "Schedule_C_P2" → "Schedule_C".
    If multiple labels, uses the first.
    """
    try:
        first = (label_hint or "").split(",", 1)[0].strip()
        if not first:
            return None
        import re as _re
        base = _re.sub(r"(_P\d+|_PAGE_\d+|_PG_\d+)$", "", first, flags=_re.IGNORECASE)
        return base or None
    except Exception:
        return None


def _parse_pages_spec(pages: str) -> tuple[int, int]:
    try:
        s = str(pages or "").strip()
        if "-" in s:
            a, b = s.split("-", 1)
            return (int(a), int(b)) if int(a) <= int(b) else (int(b), int(a))
        v = int(s)
        return (v, v)
    except Exception:
        return (1, 1)


def _analyze_dispatch(pdf_path: Path, *, model_id: str, pages: str, label_hint: Optional[str] = None) -> Any:
    """Dispatch analyze call based on model_id.

    - local-template:<key|auto> → local coordinate template service
    - reducto:schema:<key|auto> → Reducto schema extraction
    - default → Azure Document Intelligence
    """
    from app.infrastructure.azure_service import parse_with_azure_docint
    from app.infrastructure.reducto_schema_registry import get_schema_config_for_key
    from app.infrastructure.reducto_service import create_client as create_reducto_client, extract_with_schema as reducto_extract_with_schema
    from app.infrastructure.local_template_service import analyze_form_with_template

    mid = (model_id or "").strip()
    if mid.lower().startswith("local-template:"):
        suffix = mid.split(":", 1)[1].strip() if ":" in mid else ""
        if not suffix or suffix.lower() == "auto":
            key = _derive_form_key_from_label_hint(label_hint or "")
            if not key:
                raise RuntimeError("local-template:auto could not derive template key from labels")
            form_key = key
        else:
            form_key = suffix
        return analyze_form_with_template(pdf_path, pages=pages, form_key=form_key)

    if mid.lower().startswith("reducto:"):
        suffix = mid.split(":", 1)[1].strip() if ":" in mid else ""
        if suffix.lower().startswith("schema"):
            parts = suffix.split(":", 1)
            key = parts[1].strip() if len(parts) == 2 else None
            if not key or key.lower() == "auto":
                key = _derive_form_key_from_label_hint(label_hint or "")
            if not key:
                raise RuntimeError("reducto:schema:auto could not derive schema key from labels")
            cfg = get_schema_config_for_key(key)
            start, end = _parse_pages_spec(pages)
            client = create_reducto_client()
            return reducto_extract_with_schema(
                client,
                pdf_path,
                schema=cfg.get("schema", {}),
                start_page=start,
                end_page=end,
                system_prompt=str(cfg.get("system_prompt", "")),
            )
        raise RuntimeError(f"Unsupported Reducto mode: {suffix}")

    return parse_with_azure_docint(pdf_path, page_number=1, model_id=model_id, pages=pages)


def _classify_document(pdf_path: Path) -> List[ClassifiedPage]:
    from app.infrastructure.ml_classify_service import classify_document_ml

    rows = classify_document_ml(Path(pdf_path), topk=1)
    out: List[ClassifiedPage] = []
    for r in rows:
        raw_lbl = str(r.get("predicted_label"))
        base_val = str(r.get("predicted_family") or r.get("base_label") or "Other")
        pif = r.get("page_in_form")
        try:
            pif_int = int(pif) if pif is not None else None
        except Exception:
            pif_int = None
        out.append(
            ClassifiedPage(
                file_name=Path(pdf_path).name,
                page=int(r.get("page")),
                label=raw_lbl,
                base_label=base_val,
                page_in_form=pif_int,
            )
        )
    return out


def run_pipeline(pdf_path: Path, *, use_jsonic_dependents: bool = False) -> Dict[str, Any]:
    """Run the full pipeline: classify → plan → execute → aggregate (+ postprocess).

    Returns a dict with keys: classified, page_plan, combined_out, timings, job_timings.
    """
    from app.infrastructure.azure_service import azure_fields_to_dict
    from app.plugins.registry import select_postprocessor, run_postprocessor

    # 1) Classification
    t_clf0 = perf_counter()
    classified = _classify_document(Path(pdf_path))
    t_clf = perf_counter() - t_clf0

    # 2) Planning
    t_plan0 = perf_counter()
    azure_jobs, page_plan = build_page_plan(classified)
    t_plan = perf_counter() - t_plan0

    # 3) Execute jobs (network-bound): run with thread pool
    def _worker(job: AzureJob) -> Tuple[str, Dict[str, Any]]:
        label_text = ", ".join(sorted({p.label for p in page_plan if p.job_id == job.job_id})) or ""
        t0 = perf_counter()
        try:
            result = _analyze_dispatch(Path(pdf_path), model_id=job.model_id, pages=job.pages, label_hint=label_text)
            secs = perf_counter() - t0
            return job.job_id, {"ok": True, "result": result, "secs": secs}
        except Exception as e:
            secs = perf_counter() - t0
            msg = str(e) or "analysis failed"
            return job.job_id, {"ok": False, "error": msg, "secs": secs}

    job_results: Dict[str, Dict[str, Any]] = {}
    job_timings: List[Dict[str, Any]] = []
    api_total = 0.0
    max_workers = min(4, max(1, len(azure_jobs)))
    if azure_jobs:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_worker, job) for job in azure_jobs]
            for fut in as_completed(futures):
                jid, payload = fut.result()
                job_results[jid] = payload
        # Timings and cumulative API time
        for job in azure_jobs:
            payload = job_results.get(job.job_id, {})
            api_total += float(payload.get("secs", 0.0))
            job_timings.append(
                {
                    "job_id": job.job_id,
                    "model_id": job.model_id,
                    "pages": job.pages,
                    "secs": float(payload.get("secs", 0.0)),
                    "ok": bool(payload.get("ok")),
                    **({"error": payload.get("error")} if not payload.get("ok") else {}),
                }
            )

    # 4) Build combined result
    combined = {
        "document": Path(pdf_path).name,
        "page_plan": [asdict(p) for p in page_plan],
        "runs": [],
    }
    for job in azure_jobs:
        payload = job_results.get(job.job_id) or {}
        ok = bool(payload.get("ok"))
        entry: Dict[str, Any] = {
            "job_id": job.job_id,
            "model_id": job.model_id,
            "pages": job.pages,
            "ok": ok,
        }
        if ok:
            try:
                res_obj = payload.get("result")
                if isinstance(job.model_id, str) and (
                    job.model_id.lower().startswith("local-template:") or job.model_id.lower().startswith("reducto:")
                ):
                    entry["result"] = res_obj
                else:
                    entry["result"] = azure_fields_to_dict(res_obj)
            except Exception:
                entry["result"] = None
        else:
            entry["error"] = payload.get("error")
        combined["runs"].append(entry)

    # 5) Post-processing selection and mapping
    mapped_by_job: Dict[str, Any] = {}
    for job in azure_jobs:
        labels_for_job = [p.label for p in page_plan if p.job_id == job.job_id]
        label0 = labels_for_job[0] if labels_for_job else None
        try:
            base_hint = _derive_form_key_from_label_hint(label0 or "")
        except Exception:
            base_hint = None
        spec = select_postprocessor(label0, base_hint, job.model_id)
        if not spec:
            continue
        try:
            summary = run_postprocessor(
                spec,
                combined,
                output_dir=None,
                dependents_format=("jsonic" if use_jsonic_dependents else "array"),
            )
            if isinstance(summary, dict) and "json_data" in summary:
                mapped_by_job[job.job_id] = summary["json_data"]
        except Exception:
            # Fail silently into raw Azure fields if post-processing fails
            continue

    if mapped_by_job:
        for r in combined.get("runs", []):
            jid = r.get("job_id")
            if jid in mapped_by_job:
                r["result"] = mapped_by_job[jid]

    combined_out = dict(combined)
    combined_out.pop("page_plan", None)

    timings = {
        "classify_ms": int(t_clf * 1000),
        "plan_ms": int(t_plan * 1000),
        "azure_api_ms_total": int(api_total * 1000),
        "job_timings": job_timings,
    }

    # Return a friendly package for the UI to render
    return {
        "classified": [asdict(c) for c in classified],
        "page_plan": [asdict(p) for p in page_plan],
        "combined_out": combined_out,
        "timings": timings,
    }
