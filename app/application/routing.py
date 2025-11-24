from __future__ import annotations

from typing import Dict

from app.core.settings import settings


# Exact ML labels → engine selector (model_id or special prefixes)
ML_LABEL_MODEL_MAP: Dict[str, str] = {
    # 1040 main (Local Template)
    "Form_1040_P1": "local-template:auto",
    "Form_1040_P2": "local-template:auto",


    # Schedule C (Azure prebuilt)
    "Schedule_C_P1": settings.azure.prebuilt_ids.schedule_c,
    "Schedule_C_P2": settings.azure.prebuilt_ids.schedule_c,


    # Federal Asset Report (Reducto schema, auto key from label)
    # Base label mapping will cover page-suffixed variants like *_P1
    "Federal_Asset_Report_Schedule_C": "reducto:schema:auto",
}
