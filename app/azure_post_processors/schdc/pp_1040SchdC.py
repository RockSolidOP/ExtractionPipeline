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
    "*SchCUnit",
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


def remap_run_to_row(result: dict, unit_index: int) -> dict:
    row = {k: "" for k in FIELD_ORDER}

    # --- basic ids ---
    row["*SchCUnit"] = unit_index
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
    for idx, run in enumerate(sched_c_runs, start=1):
        result = run.get("result") or {}
        rows.append(remap_run_to_row(result, idx))

    out_path = output_name_for(pipeline_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return out_path


def main():
    # Discover all azure pipeline JSON files in BASE_DIR
    inputs = sorted(BASE_DIR.glob(PIPELINE_GLOB))
    # Exclude previously written outputs like azure_pipeline_*__schedule_c.json
    inputs = [p for p in inputs if not p.name.endswith("__schedule_c.json")]
    if not inputs:
        raise SystemExit(f"No pipeline JSONs matched {BASE_DIR / PIPELINE_GLOB}")

    written = []
    for p in inputs:
        out = process_pipeline_file(p)
        if out is not None:
            print(f"written -> {out}")
            written.append(out)
        else:
            print(f"skip (no Schedule C) -> {p}")

    if not written:
        print("No Schedule C outputs produced.")


if __name__ == "__main__":
    main()
