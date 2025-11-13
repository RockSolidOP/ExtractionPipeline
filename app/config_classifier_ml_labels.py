from __future__ import annotations

"""ML label → extraction engine mapping (simple and explicit).

How it works
- Keys are the exact ML labels produced by the classifier (e.g., "Form_1040_P1").
- Values are engine selectors. Supported forms:
  - Azure models: "prebuilt-tax.us.1040", "prebuilt-tax.us.1040ScheduleC", etc.
  - Reducto schema: "reducto:schema:auto" or "reducto:schema:<key>".
  - Local template service: "local-template:auto" or "local-template:<Form_1040>".

Unmapped labels are skipped by the planner. Keep this file small and readable.
"""

from typing import Dict
from app.core.settings import settings


# Exact ML labels → engine selector
ML_LABEL_MODEL_MAP: Dict[str, str] = {
    # 1040 main (Azure prebuilt)
    "Form_1040_P1": settings.azure.prebuilt_ids.form_1040,
    "Form_1040_P2": settings.azure.prebuilt_ids.form_1040,

    # Schedule C (Azure prebuilt)
    "Schedule_C_P1": settings.azure.prebuilt_ids.schedule_c,
    "Schedule_C_P2": settings.azure.prebuilt_ids.schedule_c,
    # Some classifier outputs may provide only base label — map it too
    "Schedule_C": settings.azure.prebuilt_ids.schedule_c,
}

"""
Optional examples (commented):

# Use local template service for 1040 (auto‑infer template key from label)
# ML_LABEL_MODEL_MAP.update({
#     "Form_1040_P1": "local-template:auto",
#     "Form_1040_P2": "local-template:auto",
# })

# Route an asset report to Reducto schema (auto‑derive schema key from label)
# ML_LABEL_MODEL_MAP.update({
#     "Federal_Asset_Report_Schedule_C_P1": "reducto:schema:auto",
# })
"""

# No explicit skip list: unmapped labels are skipped implicitly by the planner.

# Post‑processor selection (used by the UI pipeline after extraction)
# Precedence: LABEL → BASE_LABEL → MODEL_PREFIX
POSTPROCESSOR_BY_LABEL: Dict[str, str] = {}

POSTPROCESSOR_BY_BASE_LABEL: Dict[str, str] = {
    "Form_1040": "app.plugins.post_processors.azure.form_1040:postprocess_combined",
    "Schedule_C": "app.plugins.post_processors.azure.form_schedule_c:postprocess_combined",
}

POSTPROCESSOR_BY_MODEL_PREFIX: Dict[str, str] = {}
