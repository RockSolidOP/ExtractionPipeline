from __future__ import annotations

"""Minimal ML label → model and post‑processor routing.

Only Form_1040_P1 and Form_1040_P2 are routed; all other labels are skipped
implicitly by not appearing in ML_LABEL_MODEL_MAP.
"""

from typing import Dict
from app.config import AZURE_CONFIG


# Exact ML labels → Azure model IDs
ML_LABEL_MODEL_MAP: Dict[str, str] = {
    "Form_1040_P1": AZURE_CONFIG.get("model_id_1040", "prebuilt-tax.us.1040"),
    "Form_1040_P2": AZURE_CONFIG.get("model_id_1040", "prebuilt-tax.us.1040"),
}

# Legacy/optional mappings (kept for reference; intentionally commented out)
# To re-enable any, move the entry above into ML_LABEL_MODEL_MAP.
#
# "Schedule_C_P1": AZURE_CONFIG.get("model_id_1040_schedule_c", "prebuilt-tax.us.1040ScheduleC"),
# "Schedule_C_P2": AZURE_CONFIG.get("model_id_1040_schedule_c", "prebuilt-tax.us.1040ScheduleC"),
# "Schedule_F_P1": AZURE_CONFIG.get("model_id_1040_schedule_f", "prebuilt-tax.us.1040ScheduleF"),
# "Schedule_F_P2": AZURE_CONFIG.get("model_id_1040_schedule_f", "prebuilt-tax.us.1040ScheduleF"),
#
# # Asset report (Schedule C) — route to Reducto schema with auto key
# "Federal_Asset_Report_Schedule_C_P1": "reducto:schema:auto",

# No explicit skip list: unmapped labels are skipped implicitly by the planner.

# Post‑processor selection
# Precedence: LABEL → BASE_LABEL → MODEL_PREFIX
POSTPROCESSOR_BY_LABEL: Dict[str, str] = {}

POSTPROCESSOR_BY_BASE_LABEL: Dict[str, str] = {
    "Form_1040": "app.azure_post_processors.1040_1_2.pp_1040_main:postprocess_combined",
}

POSTPROCESSOR_BY_MODEL_PREFIX: Dict[str, str] = {}
