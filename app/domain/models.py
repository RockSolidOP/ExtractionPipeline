from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


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

