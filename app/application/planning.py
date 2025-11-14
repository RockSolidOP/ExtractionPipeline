from __future__ import annotations

from typing import List, Tuple, Dict, Optional
import re

from app.domain.models import ClassifiedPage, AzureJob, PagePlan
from app.application.routing import ML_LABEL_MODEL_MAP


def _select_model_for_page(label: str, base_label: Optional[str]) -> Optional[str]:
    """Return model id from ML_LABEL_MODEL_MAP with base-label fallback.

    Tries exact label first, then base_label, then common P1/P2 forms.
    """
    mdl = ML_LABEL_MODEL_MAP.get(label)
    if mdl is not None:
        return mdl
    if base_label:
        for k in (base_label, f"{base_label}_P1", f"{base_label}_P2"):
            if k in ML_LABEL_MODEL_MAP:
                return ML_LABEL_MODEL_MAP[k]
    return None


def build_page_plan(classified: List[ClassifiedPage]) -> Tuple[List[AzureJob], List[PagePlan]]:
    """Pair P1/P2 within each base_label; extras become singles. Analyze all pages.

    Returns (jobs, page_plan) where jobs are execution units and page_plan contains
    per-page decisions (analyze/skip, grouping, chosen model when applicable).
    """
    if not classified:
        return [], []

    file_name = classified[0].file_name
    groups: Dict[str, List[ClassifiedPage]] = {}
    for c in sorted(classified, key=lambda x: int(x.page)):
        bl = c.base_label or "Other"
        groups.setdefault(bl, []).append(c)

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
            mdl = _select_model_for_page(c.label, bl)
            if mdl is None:
                plan.append(PagePlan(page=int(c.page), label=c.label, status="single", group_id=gid, job_id=None, action="skip", model_id=None))
            else:
                jobs.append(AzureJob(job_id=jid, file_name=file_name, model_id=mdl, pages=str(int(c.page)), reason=f"Single {bl} page"))
                plan.append(PagePlan(page=int(c.page), label=c.label, status="single", group_id=gid, job_id=jid, action="analyze", model_id=mdl))

    plan.sort(key=lambda x: x.page)
    return jobs, plan
