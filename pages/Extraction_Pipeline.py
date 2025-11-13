from __future__ import annotations

"""Extraction Pipeline page (ML-only)

What this page does
- Upload a PDF
- Classify all pages with the local ML classifier (FAISS/CLIP)
- Pair P1/P2 within each base_label; extra pages are singles
- Run Azure models on planned pages using ML label → model mapping
- Show a compact combined result JSON (page_plan + Azure runs)

Notes
- No regex classifier here; ML labels are used end-to-end.
- Model mapping and post-processor selection live in app/config_classifier_ml_labels.py.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from time import perf_counter

import fitz  # PyMuPDF
import streamlit as st

# Ensure project root is on sys.path when running this page directly
try:  # noqa: SIM105 - deliberate try/except import shim
    from app.services.azure_service import parse_with_azure_docint, azure_to_dict, azure_fields_to_dict
    from app.services.reducto_service import create_client as create_reducto_client, extract_with_schema as reducto_extract_with_schema
    from app.services.reducto_schema_registry import get_schema_config_for_key
    from app.services.ml_classify_service import classify_document_ml
    from app.services.local_template_service import analyze_form_with_template
    from app.config_classifier_ml_labels import ML_LABEL_MODEL_MAP
    from app.post_processing import select_postprocessor, run_postprocessor
except ModuleNotFoundError:  # Running via `streamlit run pages/Extraction_Pipeline.py`
    import sys as _sys
    from pathlib import Path as _Path

    _ROOT = _Path(__file__).resolve().parents[1]
    if str(_ROOT) not in _sys.path:
        _sys.path.insert(0, str(_ROOT))
    from app.services.azure_service import parse_with_azure_docint, azure_to_dict, azure_fields_to_dict
    from app.services.reducto_service import create_client as create_reducto_client, extract_with_schema as reducto_extract_with_schema
    from app.services.reducto_schema_registry import get_schema_config_for_key
    from app.services.ml_classify_service import classify_document_ml
    from app.services.local_template_service import analyze_form_with_template
    from app.config_classifier_ml_labels import ML_LABEL_MODEL_MAP
    from app.post_processing import select_postprocessor, run_postprocessor
from app.ui.components import download_json_button, file_uploader
from app.utils.storage import save_uploaded_file


# -----------------------------
# Models
# -----------------------------


@dataclass
class ClassifiedPage:
    file_name: str
    page: int
    label: str  # ML label used end-to-end
    base_label: Optional[str] = None  # normalized base form (e.g., 1040, Schedule_C)
    page_in_form: Optional[int] = None  # 1/2 when known


@dataclass
class AzureJob:
    job_id: str
    file_name: str
    model_id: str
    pages: str
    reason: str


@dataclass
class PagePlan:
    page: int
    label: str
    status: str  # "paired" | "single"
    group_id: Optional[str]
    job_id: Optional[str]
    action: str  # "analyze" | "skip"
    model_id: Optional[str] = None  # model selected for this page (if any)




# -----------------------------
# Helpers
# -----------------------------

# No fallback inference: base_label is taken from ML output or defaults to "Other".


## (removed) canonical mapping — we use raw ML labels end-to-end now.

def _select_model_for_page(label: str, base_label: Optional[str]) -> Optional[str]:
    """Return model id from ML_LABEL_MODEL_MAP with base-label fallback.

    Tries exact label first, then base_label, then common P1/P2 forms.
    """
    mdl = ML_LABEL_MODEL_MAP.get(label)
    if mdl is not None:
        return mdl
    if base_label:
        # try base form and common variants
        for k in (base_label, f"{base_label}_P1", f"{base_label}_P2"):
            if k in ML_LABEL_MODEL_MAP:
                return ML_LABEL_MODEL_MAP[k]
    return None


def _build_plan_generic(classified: List[ClassifiedPage]) -> Tuple[List[AzureJob], List[PagePlan]]:
    """Pair P1/P2 within each base_label; extras become singles. Analyze all pages."""
    if not classified:
        return [], []

    file_name = classified[0].file_name
    groups: Dict[str, List[ClassifiedPage]] = {}
    for c in sorted(classified, key=lambda x: int(x.page)):
        bl = c.base_label or "Other"
        groups.setdefault(bl, []).append(c)

    import re
    def _n(s: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", (s or "").lower())

    def is_p1(c: ClassifiedPage) -> bool:
        if c.page_in_form == 1:
            return True
        n = _n(c.label)
        return n.endswith("_p1") or "page_1" in n or "pg_1" in n

    def is_p2(c: ClassifiedPage) -> bool:
        if c.page_in_form == 2:
            return True
        n = _n(c.label)
        return n.endswith("_p2") or "page_2" in n or "pg_2" in n

    def tag(bl: str) -> str:
        return _n(bl).upper()

    jobs: List[AzureJob] = []
    plan: List[PagePlan] = []
    pair_no = 0

    for bl, pages in groups.items():
        unmatched_p1: List[ClassifiedPage] = []
        unmatched_p2: List[ClassifiedPage] = []
        singles: List[ClassifiedPage] = []

        roles: List[Tuple[str, ClassifiedPage]] = []
        for c in pages:
            if is_p1(c):
                roles.append(("p1", c))
            elif is_p2(c):
                roles.append(("p2", c))
            else:
                roles.append(("single", c))

        for role, c in roles:
            if role == "p2":
                if unmatched_p1:
                    first = unmatched_p1.pop(0)
                    pair_no += 1
                    a, b = (int(first.page), int(c.page))
                    if a > b:
                        a, b = b, a
                    gid = f"{file_name}#{tag(bl)}#{pair_no}({a},{b})"
                    jid = gid
                    mdl = _select_model_for_page(first.label, bl)
                    if mdl is None:
                        plan.append(PagePlan(page=a, label=first.label, status="paired", group_id=gid, job_id=None, action="skip", model_id=None))
                        plan.append(PagePlan(page=b, label=c.label, status="paired", group_id=gid, job_id=None, action="skip", model_id=None))
                    else:
                        jobs.append(AzureJob(job_id=jid, file_name=file_name, model_id=mdl, pages=f"{a}-{b}", reason=f"Paired {bl} pages"))
                        plan.append(PagePlan(page=a, label=first.label, status="paired", group_id=gid, job_id=jid, action="analyze", model_id=mdl))
                        plan.append(PagePlan(page=b, label=c.label, status="paired", group_id=gid, job_id=jid, action="analyze", model_id=mdl))
                else:
                    unmatched_p2.append(c)
            elif role == "p1":
                if unmatched_p2:
                    second = unmatched_p2.pop(0)
                    pair_no += 1
                    a, b = (int(c.page), int(second.page))
                    if a > b:
                        a, b = b, a
                    gid = f"{file_name}#{tag(bl)}#{pair_no}({a},{b})"
                    jid = gid
                    mdl = _select_model_for_page(c.label, bl)
                    if mdl is None:
                        plan.append(PagePlan(page=a, label=c.label, status="paired", group_id=gid, job_id=None, action="skip", model_id=None))
                        plan.append(PagePlan(page=b, label=second.label, status="paired", group_id=gid, job_id=None, action="skip", model_id=None))
                    else:
                        jobs.append(AzureJob(job_id=jid, file_name=file_name, model_id=mdl, pages=f"{a}-{b}", reason=f"Paired {bl} pages"))
                        plan.append(PagePlan(page=a, label=c.label, status="paired", group_id=gid, job_id=jid, action="analyze", model_id=mdl))
                        plan.append(PagePlan(page=b, label=second.label, status="paired", group_id=gid, job_id=jid, action="analyze", model_id=mdl))
                else:
                    unmatched_p1.append(c)
            else:
                singles.append(c)

        for c in unmatched_p1 + unmatched_p2 + singles:
            pair_no += 1
            gid = f"{file_name}#{tag(bl)}#{pair_no}({int(c.page)})"
            jid = gid
            # For singles, use the same selection with base-label fallback
            mdl = _select_model_for_page(c.label, bl)
            if mdl is None:
                plan.append(PagePlan(page=int(c.page), label=c.label, status="single", group_id=gid, job_id=None, action="skip", model_id=None))
            else:
                jobs.append(AzureJob(job_id=jid, file_name=file_name, model_id=mdl, pages=str(int(c.page)), reason=f"Single {bl} page"))
                plan.append(PagePlan(page=int(c.page), label=c.label, status="single", group_id=gid, job_id=jid, action="analyze", model_id=mdl))

    plan.sort(key=lambda x: x.page)
    return jobs, plan

    # End of generic planning
    plan.sort(key=lambda x: x.page)
    return jobs, plan


 


def _derive_form_key_from_label_hint(label_hint: str) -> Optional[str]:
    """Best-effort derive a template key from ML label(s).

    Examples: "Form_1040_P1" → "Form_1040"; "Schedule_C_P2" → "Schedule_C".
    If multiple labels, uses the first.
    """
    try:
        first = (label_hint or "").split(",", 1)[0].strip()
        if not first:
            return None
        # Remove common page suffixes like _P1, _P2, _PAGE_1, _PG_1 (case-insensitive)
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


def _analyze_with_azure(pdf_path: Path, *, model_id: str, pages: str, label_hint: Optional[str] = None) -> Any:
    """Dispatch to Azure or local template service based on model_id.

    - If model_id starts with "local-template:", use the local form template service.
      When the suffix is "auto" or empty, infer the template key from label_hint.
    - Otherwise, use Azure Document Intelligence.
    """
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
        # Expect forms: reducto:schema:<key> or reducto:schema:auto
        suffix = mid.split(":", 1)[1].strip() if ":" in mid else ""
        if suffix.lower().startswith("schema"):
            parts = suffix.split(":", 1)
            key = None
            if len(parts) == 2:
                # schema:<key>
                key = parts[1].strip()
            else:
                # schema or schema:auto → infer
                key = None
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
        else:
            raise RuntimeError(f"Unsupported Reducto mode: {suffix}")
    return parse_with_azure_docint(pdf_path, page_number=1, model_id=model_id, pages=pages)


# -----------------------------
# UI
# -----------------------------


def run() -> None:
    st.set_page_config(page_title="Extraction Pipeline", layout="wide")
    st.title("Extraction Pipeline")
    st.caption("Classification (ML) → 1040 routing → Azure extraction → Single JSON output")

    # Upload a single PDF
    uploaded = file_uploader("Upload a PDF (single file)", types=["pdf"])
    if not uploaded:
        st.info("Upload a PDF to start.")
        st.stop()
    pdf_path = save_uploaded_file(uploaded)
    st.caption(f"Saved: {pdf_path}")

    # Post-processor options
    st.markdown("#### Post-Processor Options")
    use_jsonic_dependents = st.checkbox("Dependents as JSONic objects (else array)", value=False)

    # Optional: open for validation if needed (currently not used)

    # Run classifier on all pages (ML classifier only)
    try:
        t_clf0 = perf_counter()
        rows = classify_document_ml(Path(pdf_path), topk=1)
        t_clf = perf_counter() - t_clf0
        classified = []
        for r in rows:
            raw_lbl = str(r.get("predicted_label"))
            base_val = str(r.get("predicted_family") or r.get("base_label") or "Other")
            pif = r.get("page_in_form")
            try:
                pif_int = int(pif) if pif is not None else None
            except Exception:
                pif_int = None
            classified.append(
                ClassifiedPage(
                    file_name=Path(pdf_path).name,
                    page=int(r.get("page")),
                    label=raw_lbl,
                    base_label=base_val,
                    page_in_form=pif_int,
                )
            )
    except Exception as e:
        st.error("Classification failed.")
        st.code(f"{type(e).__name__}: {e}")
        st.stop()

    # Show classification summary (ML labels)
    with st.expander("Classification (ML labels)", expanded=False):
        st.json([
            {"page": c.page, "label": c.label, "base_label": c.base_label, "page_in_form": c.page_in_form}
            for c in classified
        ])

    # Build plan (pairing by base_label)
    t_plan0 = perf_counter()
    azure_jobs, page_plan = _build_plan_generic(classified)
    t_plan = perf_counter() - t_plan0

    # Compute total pages to analyze
    def _count_pages(spec: str) -> int:
        try:
            if "-" in spec:
                a, b = spec.split("-", 1)
                return max(0, int(b) - int(a) + 1)
            return 1 if spec.strip() else 0
        except Exception:
            return 0
    pages_to_analyze = sum(_count_pages(job.pages) for job in azure_jobs)

    # Show quick plan summary
    st.markdown("#### Plan Summary")
    col_s1, col_s2, col_s3 = st.columns(3)
    col_s1.metric("Classify time", f"{t_clf*1000:.0f} ms")
    col_s2.metric("Plan time", f"{t_plan*1000:.0f} ms")
    col_s3.metric("Pages to analyze", str(pages_to_analyze))

    # Show page plan only
    with st.expander("Details: page plan", expanded=False):
        st.json({
            "file_name": Path(pdf_path).name,
            "page_plan": [vars(p) for p in page_plan],
        })

    # If a previous combined result exists in session, show it for convenience
    if "combined_out" in st.session_state:
        st.markdown("#### Latest Combined Result (previous run)")
        st.json(st.session_state.get("combined_out"))
        download_json_button(
            "Download last result",
            data=st.session_state.get("combined_out"),
            filename=f"azure_pipeline_{Path(pdf_path).stem}.json",
        )

    # Run button
    if st.button("Run Extraction", type="primary"):
        # Progress across analyzable pages only
        total_pages = max(0, int(pages_to_analyze))
        done_pages = 0
        prog = st.progress(0.0, text=f"0/{total_pages} Done — waiting to start…")
        status = st.empty()
        job_log_placeholder = st.empty()

        # Execute Azure jobs
        azure_results: Dict[str, Dict[str, Any]] = {}
        job_timings: List[Dict[str, Any]] = []
        api_total = 0.0
        for job in azure_jobs:
            label_text = ", ".join(sorted({p.label for p in page_plan if p.job_id == job.job_id})) or "1040"
            # Show job as running before the call
            job_log_placeholder.write({"running": job.job_id, "pages": job.pages, "label": label_text})
            status.text(f"Analyzing {job.pages} — {label_text}")
            t0 = perf_counter()
            try:
                result = _analyze_with_azure(pdf_path, model_id=job.model_id, pages=job.pages, label_hint=label_text)
                secs = perf_counter() - t0
                api_total += secs
                azure_results[job.job_id] = {"ok": True, "result": result}
                job_timings.append({"job_id": job.job_id, "model_id": job.model_id, "pages": job.pages, "secs": secs, "ok": True})
            except Exception as e:
                secs = perf_counter() - t0
                api_total += secs
                # Normalize exception message for local-template failures
                msg = str(e)
                if job.model_id.lower().startswith("local-template:") and not msg:
                    msg = "Local template extraction failed"
                azure_results[job.job_id] = {"ok": False, "error": msg}
                job_timings.append({"job_id": job.job_id, "model_id": job.model_id, "pages": job.pages, "secs": secs, "ok": False, "error": str(e)})

            # Increment progress by number of pages in this job
            inc = _count_pages(job.pages)
            done_pages += inc
            frac = 1.0 if total_pages == 0 else min(1.0, max(0.0, done_pages / float(total_pages)))
            prog.progress(frac, text=f"{min(done_pages, total_pages)}/{total_pages} Done — {label_text}")
            # Update job log with latest entry
            job_log_placeholder.json(job_timings)

        # Summarize outputs
        st.success("Pipeline complete.")
        st.markdown("#### Timings")
        st.json({
            "classify_ms": int(t_clf * 1000),
            "plan_ms": int(t_plan * 1000),
            "azure_api_ms_total": int(api_total * 1000),
            "job_timings": job_timings,
        })

        # Build a compact combined result
        combined = {
            "document": Path(pdf_path).name,
            "page_plan": [vars(p) for p in page_plan],
            "runs": [],
        }
        for job in azure_jobs:
            payload = azure_results.get(job.job_id) or {}
            ok = bool(payload.get("ok"))
            entry = {
                "job_id": job.job_id,
                "model_id": job.model_id,
                "pages": job.pages,
                "ok": ok,
            }
            if ok:
                try:
                    # For Azure models, show only document fields; for local-template, keep full result
                    res_obj = payload.get("result")
                    if isinstance(job.model_id, str) and (job.model_id.lower().startswith("local-template:") or job.model_id.lower().startswith("reducto:")):
                        entry["result"] = res_obj
                    else:
                        entry["result"] = azure_fields_to_dict(res_obj)
                except Exception:
                    entry["result"] = None
            else:
                entry["error"] = payload.get("error")
            combined["runs"].append(entry)

        # Post-processing phase (optional per config)
        post_summaries = []
        # Run at most one post-processor per Azure job (based on label/base_label/model id)
        jobs_by_id = {job.job_id: job for job in azure_jobs}
        for job in azure_jobs:
            # Derive a representative label for the job
            labels_for_job = [p.label for p in page_plan if p.job_id == job.job_id]
            label0 = labels_for_job[0] if labels_for_job else None

            # Best-effort derive base_label from label text
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
                post_summaries.append({
                    "job_id": job.job_id,
                    "spec": spec,
                    "summary": summary,
                })
            except Exception as e:
                post_summaries.append({
                    "job_id": job.job_id,
                    "spec": spec,
                    "error": f"{type(e).__name__}: {e}",
                })

        # If post-processors returned mapped JSON payloads, embed them into combined
        # replacing the Azure fields for those jobs (do not retain raw Azure fields).
        mapped_by_job = {}
        for item in post_summaries:
            summ = item.get("summary") or {}
            jid = item.get("job_id") or summ.get("job_id")
            if jid and isinstance(summ, dict) and "json_data" in summ:
                mapped_by_job[jid] = summ["json_data"]

        if mapped_by_job:
            for r in combined.get("runs", []):
                jid = r.get("job_id")
                if jid in mapped_by_job:
                    # Replace Azure fields with post-processed mapping; do not keep raw fields
                    r["result"] = mapped_by_job[jid]

        # Do not include post-process summaries inside combined output

        # Build a lean combined output for display/download (exclude planning details)
        combined_out = dict(combined)
        combined_out.pop("page_plan", None)

        # Persist result in session so it remains after reruns (e.g., after downloads)
        st.session_state["combined_out"] = combined_out

        st.markdown("#### Combined Result (JSON)")
        st.json(combined_out)
        download_json_button(
            "Download azure_pipeline.json",
            data=combined_out,
            filename=f"azure_pipeline_{Path(pdf_path).stem}.json",
        )


if __name__ == "__main__":
    run()
