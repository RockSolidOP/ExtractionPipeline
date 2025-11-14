from __future__ import annotations

from typing import Dict

from app.core.settings import settings


# Exact ML labels → engine selector (model_id or special prefixes)
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

