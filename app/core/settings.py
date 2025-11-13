from __future__ import annotations

from typing import Optional, Dict, Any

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class AzurePrebuiltIds(BaseModel):
    """Default Azure Document Intelligence prebuilt model IDs.

    Override via application code if needed. Environment overrides for nested
    items are not required at this time.
    """

    document: str = "prebuilt-document"
    form_1040: str = "prebuilt-tax.us.1040"
    schedule_1: str = "prebuilt-tax.us.1040Schedule1"
    schedule_a: str = "prebuilt-tax.us.1040ScheduleA"
    schedule_c: str = "prebuilt-tax.us.1040ScheduleC"
    schedule_e: str = "prebuilt-tax.us.1040ScheduleE"


class AzureSettings(BaseSettings):
    """Azure Document Intelligence credentials and defaults.

    Reads from environment using the AZURE_DOC_AI_ prefix:
      - AZURE_DOC_AI_ENDPOINT
      - AZURE_DOC_AI_KEY
    """

    model_config = SettingsConfigDict(env_prefix="AZURE_DOC_AI_", env_file=".env", extra="ignore")

    endpoint: str = ""
    key: str = ""
    prebuilt_ids: AzurePrebuiltIds = AzurePrebuiltIds()


class ReductoSettings(BaseSettings):
    """Reducto API client config, options, and timeouts.

    Environment prefix: REDUCTO_
      - REDUCTO_API_KEY
      - REDUCTO_USE_PROXY, REDUCTO_PROXY_URL
      - REDUCTO_CONNECT_TIMEOUT, REDUCTO_READ_TIMEOUT, REDUCTO_WRITE_TIMEOUT, REDUCTO_POOL_TIMEOUT
      - REDUCTO_MAX_RETRIES
    """

    model_config = SettingsConfigDict(env_prefix="REDUCTO_", env_file=".env", extra="ignore")

    api_key: str = ""

    # HTTP client behavior
    use_proxy: bool = False
    proxy_url: Optional[str] = None
    connect_timeout: float = 10.0
    read_timeout: float = 60.0
    write_timeout: float = 30.0
    pool_timeout: float = 10.0
    max_retries: int = 1

    # SDK options (used by parse/extract flows)
    options: Dict[str, Any] = {
        "ocr_mode": "agentic",
        "extraction_mode": "ocr",
        "chunking": {"chunk_mode": "variable"},
    }
    advanced_options: Dict[str, Any] = {
        "ocr_system": "multilingual",
        # default page range is overridden by call sites
        "page_range": {"start": 1, "end": 10},
        "table_output_format": "ai_json",
        "merge_tables": True,
    }
    experimental_options: Dict[str, Any] = {
        "enable_checkboxes": True,
        "return_figure_images": False,
        "rotate_pages": True,
    }


class UploadsSettings(BaseSettings):
    """Uploads directory maintenance policy.

    Environment prefix: UPLOADS_
    """

    model_config = SettingsConfigDict(env_prefix="UPLOADS_", env_file=".env", extra="ignore")

    enabled: bool = True
    max_age_days: int = 30
    max_total_size_mb: int = 512
    max_files: int = 1000


class PyMuPDFSettings(BaseSettings):
    """Local extraction preferences for PyMuPDF helpers."""

    model_config = SettingsConfigDict(env_prefix="PYMUPDF_", env_file=".env", extra="ignore")

    text_mode: str = "blocks"  # "blocks" or "dict"
    kv_enable_colon: bool = True
    kv_enable_dot_leader: bool = True
    kv_merge_strategy: str = "first"  # "first" | "last" | "list"


class Settings(BaseSettings):
    """Top-level application settings container."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure: AzureSettings = AzureSettings()
    reducto: ReductoSettings = ReductoSettings()
    uploads: UploadsSettings = UploadsSettings()
    pymupdf: PyMuPDFSettings = PyMuPDFSettings()


# Instantiate a process-wide settings object. Import as:
#   from app.core.settings import settings
settings = Settings()

