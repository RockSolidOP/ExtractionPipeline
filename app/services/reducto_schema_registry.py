from __future__ import annotations

"""Dynamic registry for Reducto schema-based extraction.

Loads JSON Schemas from `ExtractionPipeline/reducto_schema/` based on a logical
key (usually derived from the ML label base, e.g., Federal_Asset_Report_Schedule_C).
The selected schema file is the most recently modified file whose name contains
the key and ends with `_schema.json` (case-insensitive).
"""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import json
import re


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _schema_dir() -> Path:
    return _project_root() / "reducto_schema"


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def get_asset_form_extraction_prompt() -> str:
    """
    System prompt for extracting data from Asset Depreciation Form (AssetForm)
    into JSON with strict schema adherence.
    """
    return (
        "You are extracting data from an Asset Depreciation Form into JSON. "
        "Return only a single JSON object that exactly conforms to the provided JSON Schema—no extra keys, comments, or text.\n"
        "Where to look & how to read\n"
        "• Match asset rows by their printed labels (description) and capture numeric/date fields directly from the same row. "
        "• Use the nearest bold+underlined section header above the row as assetType. "
        "If no clear header is found, set assetType = \"OTHER\".\n"
        "• Process all pages; include every asset row, regardless of section. "
        "Do not generate synthetic IDs.\n"
        "Value rules\n"
        "• Dates must be in ISO format (YYYY-MM-DD). "
        "• For money amounts: strip $ and commas; if parentheses are printed, return the negative value (e.g., “(1,234)” → -1234). "
        "• Percentages: return numeric value only (e.g., 50 for 50%).\n"
        "• If a field is blank, missing, unreadable, or marked with dash (—)/N/A, output null.\n"
        "• Status must be inferred: "
        "– If under Sold/Scrapped section, status = \"disposed\"; "
        "– If notes mention scrapped, status = \"scrapped\"; "
        "– Otherwise status = \"active\".\n"
        "• Do not compute totals or derive missing values—copy only printed values.\n"
        "Output\n"
        "• Produce exactly one JSON object matching the schema. "
        "• If uncertain between multiple possible values, choose null."
    )


def _default_prompt_for_key(key: str) -> str:
    k = _normalize(key)
    if "asset" in k and "schedule_c" in k:
        return get_asset_form_extraction_prompt()
    # Generic fallback prompt
    return (
        "Extract fields into a JSON object that strictly conforms to the provided JSON Schema. "
        "Return exactly one JSON object with no extra commentary."
    )


def find_schema_file_for_key(key: str) -> Optional[Path]:
    """Find the most recent *_schema.json containing the key in its name."""
    target = _normalize(key)
    d = _schema_dir()
    if not d.exists():
        return None
    candidates: list[Tuple[float, Path]] = []
    for p in d.glob("*_schema.json"):
        if target in _normalize(p.stem):
            try:
                candidates.append((p.stat().st_mtime, p))
            except Exception:
                candidates.append((0.0, p))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def get_schema_config_for_key(key: str) -> Dict[str, Any]:
    """Return a dict with {schema, system_prompt} loaded from disk, inferred by key.

    Raises FileNotFoundError if no matching schema file is found.
    Raises ValueError if the schema file is invalid JSON.
    """
    p = find_schema_file_for_key(key)
    if not p:
        raise FileNotFoundError(f"No schema file found for key '{key}' in {_schema_dir()}")
    with open(p, "r") as f:
        schema = json.load(f)
    return {
        "schema": schema,
        "system_prompt": _default_prompt_for_key(key),
        "schema_path": str(p.resolve()),
        "key": key,
    }

