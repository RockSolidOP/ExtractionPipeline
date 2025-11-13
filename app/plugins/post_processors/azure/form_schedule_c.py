import json
from pathlib import Path

# This script remaps Schedule C fields from Azure pipeline JSON files
# and writes JSON output(s) into the same directory as the input pipeline JSON.

# Directories
HERE = Path(__file__).resolve().parent  # directory of this script
# Base directory containing the pipeline JSON(s). The provided sample JSON
# lives one folder above this script (../azure_pipeline_*.json)
BASE_DIR = HERE.parent

# Default glob to discover pipeline JSONs
PIPELINE_GLOB = "azure_pipeline_*.json"

# Output filename pattern per input pipeline file (without extension)
# Example: azure_pipeline_foo.json -> azure_pipeline_foo__schedule_c.json
def output_name_for(pipeline_path: Path) -> Path:
    # Always write output JSON next to this Python file
    return HERE / f"{pipeline_path.stem}__schedule_c.json"


FIELD_ORDER = [
    "TSJ",
    "BusinessName",
    "BusinessCode",
    "FEIN",
    "Address",
    "CityStateZip",
    "AcctMthdCash",
    "AcctMthdAcc",
    "AcctMthdOth",
    "OthAcctMthd",
    "InventoryMthdC",
    "InventoryMthdLoCorM",
    "InventoryMthdOth",
    "InvMthCodeC",
    "ChgInvSTMT",
]


def get_string(field_dict, default=""):
    """Extract string/number from an Azure field object."""
    if not isinstance(field_dict, dict):
        return default
    t = field_dict.get("type")
    if t == "string":
        return field_dict.get("valueString", default) or field_dict.get("content", default)
    if t == "number":
        return field_dict.get("valueNumber", default)
    # address and other types have no simple scalar value
    return default


def selected_line(lines: list[str], i: int) -> bool:
    return i < len(lines) and isinstance(lines[i], str) and "selected" in lines[i]


def remap_run_to_row(result: dict) -> dict:
    row = {k: "" for k in FIELD_ORDER}

    # --- basic ids ---
    row["TSJ"] = ""  # Not present in Azure Schedule C output; left blank

    # --- business header from Azure ---
    row["BusinessName"] = get_string(result.get("BoxC", {}))
    row["BusinessCode"] = get_string(result.get("BoxB", {}))
    row["FEIN"] = get_string(result.get("BoxD", {}))

    # Address -> BoxE (address object)
    addr_obj = result.get("BoxE", {})
    addr_val = addr_obj.get("valueAddress") or {}
    street = addr_val.get("streetAddress", "")
    city = addr_val.get("city", "")
    state = addr_val.get("state", "")
    postal = addr_val.get("postalCode", "")
    row["Address"] = street
    row["CityStateZip"] = " ".join(part for part in [city, state, postal] if part)

    # --- accounting method (BoxF) ---
    acct_sel = (result.get("BoxF") or {}).get("valueSelectionGroup", []) or []
    row["AcctMthdCash"] = 1 if any(s == "Cash" for s in acct_sel) else 0
    row["AcctMthdAcc"] = 1 if any(s == "Accrual" for s in acct_sel) else 0
    row["AcctMthdOth"] = 1 if any(s == "Other" for s in acct_sel) else 0
    row["OthAcctMthd"] = get_string(result.get("BoxFExtraInfo", {}))

    # --- inventory method (Part III) -> Box33 selectionGroup lines
    inv_content = (result.get("Box33") or {}).get("content", "")
    inv_lines = inv_content.splitlines() if inv_content else []
    row["InventoryMthdC"] = 1 if selected_line(inv_lines, 0) else 0
    row["InventoryMthdLoCorM"] = 1 if selected_line(inv_lines, 1) else 0
    row["InventoryMthdOth"] = 1 if selected_line(inv_lines, 2) else 0
    # If "other" specifics were provided, Azure payload doesn't expose a separate text
    row["InvMthCodeC"] = ""

    # --- change in inventory method -> Box34 (yes/no, first line selected = yes)
    chg_content = (result.get("Box34") or {}).get("content", "")
    chg_lines = chg_content.splitlines() if chg_content else []
    row["ChgInvSTMT"] = 1 if (chg_lines and "selected" in chg_lines[0]) else 0

    return row


def find_schedule_c_runs(pipeline: dict) -> list[dict]:
    runs = []
    for r in pipeline.get("runs", []):
        model = str(r.get("model_id", ""))
        if model.endswith("ScheduleC"):
            runs.append(r)
    return runs


def process_pipeline_file(pipeline_path: Path) -> Path | None:
    with open(pipeline_path, "r", encoding="utf-8") as f:
        pipeline = json.load(f)

    # If this file is our own output or otherwise not a dict payload, skip it.
    if not isinstance(pipeline, dict):
        return None

    sched_c_runs = find_schedule_c_runs(pipeline)
    if not sched_c_runs:
        # no Schedule C in this pipeline
        return None

    rows = []
    for run in sched_c_runs:
        result = run.get("result") or {}
        rows.append(remap_run_to_row(result))

    out_path = output_name_for(pipeline_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return out_path


def postprocess_combined(combined: dict, output_dir=None, options: dict | None = None) -> dict:
    """Adapter entrypoint to integrate with the Streamlit pipeline page.

    - Expects `combined` to contain `page_plan` and `runs`.
    - Identifies the first successful Schedule C run.
    - Remaps it to a single Schedule C row (unit 1) and returns an artifact summary
      and the remapped JSON payload for embedding in the combined results.
    """
    # Collect Schedule C job_ids from page_plan where action == analyze
    job_ids = set()
    for item in combined.get("page_plan", []):
        label = str(item.get("label") or "")
        if label.startswith("Schedule_C") and item.get("job_id") and item.get("action") == "analyze":
            job_ids.add(item["job_id"])

    # Find the first successful run matching those job_ids (or any Schedule C run)
    chosen_run = None
    for r in combined.get("runs", []):
        if not r.get("ok"):
            continue
        mid = str(r.get("model_id") or "")
        is_schc = mid.endswith("ScheduleC") or mid.lower().endswith("schedulec")
        if not is_schc:
            continue
        if job_ids and r.get("job_id") not in job_ids:
            continue
        chosen_run = r
        break

    if not chosen_run:
        raise RuntimeError("postprocess_combined (Schedule C): No successful Schedule C run found")

    result = chosen_run.get("result") or {}
    row = remap_run_to_row(result)

    # Do not write artifacts to disk in pipeline adapter; return only in-memory JSON
    return {
        "artifacts": {},
        "job_id": chosen_run.get("job_id"),
        "pages": chosen_run.get("pages"),
        "json_data": row,
    }

