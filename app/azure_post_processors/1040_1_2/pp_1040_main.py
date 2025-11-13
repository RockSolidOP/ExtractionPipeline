#!/usr/bin/env python3
"""
pp_1040_main.py
Identify 1040 run from pipeline JSON (page_plan + runs), extract the 1040 result,
map to GenInformation-style fields, and output CSV/JSON (no Excel dependency).
"""

from pathlib import Path
import os
import json
import csv


# ---------------------------------------------------------------------------
# CONFIG - defaults point to sample JSON next to this script
# ---------------------------------------------------------------------------
HERE = Path(__file__).resolve().parent

# Output files should live next to this script
OUTPUT_CSV_PATH = HERE / "mapped_output.csv"
OUTPUT_JSON_PATH = HERE / "mapped_output.json"

# Field order for output
DEFAULT_FIELD_NAMES = [
    # Filing status flags
    "FSTATUSS", "FSTATUSH", "FSTATUSJ", "FSTATUSM", "FSTATUSQ", "FSTATUSNF",
    # Taxpayer, Spouse
    "TPFIRST", "TPLAST", "SSNTP", "SPFIRST", "SPLAST", "SSNSP",
    # Occupations
    "OCCUPTP", "OCCUPSP",
    # Address
    "STREET", "APTNO", "CITY", "STATE", "ZIP",
    # Presidential election
    "PRESELTP", "PRESELSP",
    # Blind
    "BLINDTP", "BLINDSP",
    # Dependent 1 (first listed)
    "FNAME", "LNAME", "SSN", "RELATION",
    # Preparer / Taxpayer contact
    "PTIN", "PreparerPhone", "PrepEmail", "DAYPHONE", "TPEMAIL",
    # Common numeric placeholders that aren’t in the 1040 result payload here
    "DEPANPT", "DEPANSP", "CHILDHOH",
    "InterestIncome", "DividendIncome", "SalariesWages",
    "TxblSocSec", "TxblIRADistrib", "TxblPensions",
    "TaxOnTxblIncome", "QualBusIncDed", "StandardDed",
    "IncTaxWithheld", "EstTaxPayments", "LatePenInt",
    "RoutingNumb1", "AccountNumb1", "TypeOfAcct1",
    # Note: CTC fields removed per latest requirements
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def get_in(d, path, default=None):
    cur = d
    for p in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p)
        if cur is None:
            return default
    return cur if cur is not None else default


def first_dep(result_dict):
    deps = result_dict.get("Dependents", {}).get("valueArray", [])
    if deps and isinstance(deps, list):
        return deps[0].get("valueObject", {})
    return {}


def _field(result: dict, key: str) -> dict:
    return result.get(key) or {}


def _value_string(field: dict | None):
    if not isinstance(field, dict):
        return ""
    return field.get("valueString") or field.get("content") or ""


def _value_number(field: dict | None):
    if not isinstance(field, dict):
        return ""
    if "valueNumber" in field and field["valueNumber"] is not None:
        return field["valueNumber"]
    # try to parse numeric content like "29,200" or "47"
    content = field.get("content")
    if isinstance(content, str):
        digits = "".join(ch for ch in content if ch.isdigit() or ch == ".")
        if digits:
            try:
                # prefer int if it looks like an integer
                return int(digits) if digits.isdigit() else float(digits)
            except Exception:
                return ""
    return ""


def get_field_names() -> list[str]:
    return DEFAULT_FIELD_NAMES


# ---------------------------------------------------------------------------
# Mapping logic from 1040 JSON result -> Excel codes
# ---------------------------------------------------------------------------
def _parse_dependents(result: dict) -> list[dict]:
    """Extract dependents into a normalized list of dicts.

    Output schema per dependent:
    {
      "first_name": str,
      "last_name": str,
      "ssn": str,
      "relationship": str,
      "child_tax_credit": bool,
      "other_dependent_credit": bool,
    }
    """
    out: list[dict] = []
    deps = result.get("Dependents", {}).get("valueArray", []) or []
    for d in deps:
        vo = d.get("valueObject", {}) if isinstance(d, dict) else {}
        # Name: often captured as "First\nLast"
        name_raw = _value_string(vo.get("Name"))
        first_name, last_name = "", ""
        if name_raw:
            parts = name_raw.split("\n")
            if len(parts) == 1:
                # best effort split on whitespace if single line
                ws = parts[0].strip().split()
                if len(ws) >= 2:
                    first_name = " ".join(ws[:-1])
                    last_name = ws[-1]
                else:
                    first_name = parts[0]
            else:
                first_name = parts[0]
                last_name = parts[1]

        ssn = _value_string(vo.get("SSN"))
        relationship = _value_string(vo.get("RelationshipToFiler"))

        credit = vo.get("CreditType", {}) if isinstance(vo, dict) else {}
        sel = credit.get("valueSelectionGroup") if isinstance(credit, dict) else None
        sel = sel or []
        child_ctc = any(s == "ChildTaxCredit" for s in sel)
        other_dep = any(s == "OtherDependentCredit" for s in sel)

        out.append(
            {
                "first_name": first_name,
                "last_name": last_name,
                "ssn": ssn,
                "relationship": relationship,
                "child_tax_credit": bool(child_ctc),
                "other_dependent_credit": bool(other_dep),
            }
        )
    return out


def make_dependents_jsonic(result: dict) -> list[dict]:
    """Return dependents as an array of objects (JSONic).

    Uses labels aligned with flat fields: FNAME, LNAME, SSN, RELATION,
    and uses "ChildTaxCredit" instead of "child_tax_credit".
    """
    base = _parse_dependents(result)
    converted: list[dict] = []
    for o in base:
        converted.append(
            {
                "FNAME": o.get("first_name", ""),
                "LNAME": o.get("last_name", ""),
                "SSN": o.get("ssn", ""),
                "RELATION": o.get("relationship", ""),
                "ChildTaxCredit": bool(o.get("child_tax_credit", False)),
            }
        )
    return converted


def make_dependents_array(result: dict) -> list[list]:
    """Return dependents as an array of positional arrays.

    Each inner array has the order:
    [first_name, last_name, ssn, relationship, child_tax_credit]
    """
    objs = _parse_dependents(result)
    arr: list[list] = []
    for o in objs:
        arr.append(
            [
                o.get("first_name", ""),
                o.get("last_name", ""),
                o.get("ssn", ""),
                o.get("relationship", ""),
                bool(o.get("child_tax_credit", False)),
            ]
        )
    return arr


def build_row_from_result(result: dict, field_names: list[str]) -> dict:
    taxpayer = get_in(result, ["Taxpayer", "valueObject"], {}) or {}
    spouse = get_in(result, ["Spouse", "valueObject"], {}) or {}
    sig = get_in(result, ["SignatureDetails", "valueObject"], {}) or {}
    prep = get_in(result, ["PaidPreparer", "valueObject"], {}) or {}
    addr = get_in(taxpayer, ["Address", "valueAddress"], {}) or {}
    dep1 = first_dep(result)

    # filing status
    filing = get_in(result, ["FilingStatus", "valueSelectionGroup"], []) or []
    filing_selected = filing[0] if filing else None
    filing_map = {
        "Single": "FSTATUSS",
        "HeadOfHousehold": "FSTATUSH",
        "MarriedFilingJointly": "FSTATUSJ",
        "MarriedFilingSeparately": "FSTATUSM",
        "QualifyingSurvivingSpouse": "FSTATUSQ",
    }

    # presidential election
    pres = get_in(result, ["PresidentialElectionCampaign", "valueSelectionGroup"], []) or []

    values = {}

    # mark filing
    if filing_selected and filing_selected in filing_map:
        values[filing_map[filing_selected]] = 1

    # taxpayer / spouse
    values["TPFIRST"] = get_in(taxpayer, ["FirstNameAndInitials", "valueString"])
    values["TPLAST"] = get_in(taxpayer, ["LastName", "valueString"])
    values["SSNTP"] = get_in(taxpayer, ["SSN", "valueString"])

    values["SPFIRST"] = get_in(spouse, ["FirstNameAndInitials", "valueString"])
    values["SPLAST"] = get_in(spouse, ["LastName", "valueString"])
    values["SSNSP"] = get_in(spouse, ["SSN", "valueString"])

    # occupations
    values["OCCUPTP"] = get_in(sig, ["TaxpayerOccupation", "valueString"])
    values["OCCUPSP"] = get_in(sig, ["SpouseOccupation", "valueString"])

    # address
    values["STREET"] = addr.get("streetAddress")
    values["APTNO"] = ""  # not present
    values["CITY"] = addr.get("city")
    values["STATE"] = addr.get("state")
    values["ZIP"] = addr.get("postalCode")

    # presidential
    values["PRESELTP"] = 1 if "Taxpayer" in pres else ""
    values["PRESELSP"] = 1 if "Spouse" in pres else ""

    # blind — sample shows unselected
    values["BLINDTP"] = ""
    values["BLINDSP"] = ""

    # dependents
    dep_name = get_in(dep1, ["Name", "valueString"])
    if dep_name:
        parts = dep_name.split("\n")
        if len(parts) > 0:
            values["FNAME"] = parts[0]
        if len(parts) > 1:
            values["LNAME"] = parts[1]
    values["SSN"] = get_in(dep1, ["SSN", "valueString"])
    values["RELATION"] = get_in(dep1, ["RelationshipToFiler", "valueString"])

    # preparer
    values["PTIN"] = get_in(prep, ["PreparerPTIN", "valueString"])
    values["PreparerPhone"] = get_in(prep, ["PreparerFirmPhoneNumber", "valueString"])
    values["PrepEmail"] = ""

    # taxpayer contact
    values["DAYPHONE"] = get_in(sig, ["TaxpayerPhoneNumber", "valueString"]) or ""
    values["TPEMAIL"] = get_in(sig, ["TaxpayerEmail", "valueString"]) or ""

    # ------------------------------
    # Remap additional financial/check fields from 1040
    # ------------------------------
    # Wages: prefer total (1z) then 1a
    values.setdefault("SalariesWages", _value_number(_field(result, "Box1z")) or _value_number(_field(result, "Box1a")) or "")

    # Interest: taxable (2b); 2a is tax-exempt
    values.setdefault("InterestIncome", _value_number(_field(result, "Box2b")) or "")

    # Dividends: ordinary (3b); 3a is qualified
    values.setdefault("DividendIncome", _value_number(_field(result, "Box3b")) or "")

    # IRA distributions taxable (4b); pensions often 4d (not present in this sample)
    values.setdefault("TxblIRADistrib", _value_number(_field(result, "Box4b")) or "")
    values.setdefault("TxblPensions", _value_number(_field(result, "Box4d")) if _field(result, "Box4d") else "")

    # Social Security taxable (5b)
    values.setdefault("TxblSocSec", _value_number(_field(result, "Box5b")) or "")

    # Standard deduction (12) and QBI deduction (13)
    values.setdefault("StandardDed", _value_number(_field(result, "Box12")) or "")
    values.setdefault("QualBusIncDed", _value_number(_field(result, "Box13")) or "")

    # Tax (16)
    values.setdefault("TaxOnTxblIncome", _value_number(_field(result, "Box16")) or "")

    # Payments
    # Total federal income tax withheld (25a-d) — sum if available, else use 25d if present
    b25a = _value_number(_field(result, "Box25a"))
    b25b = _value_number(_field(result, "Box25b"))
    b25c = _value_number(_field(result, "Box25c"))
    b25d = _value_number(_field(result, "Box25d"))
    withheld_candidates = [x for x in [b25a, b25b, b25c, b25d] if isinstance(x, (int, float))]
    if withheld_candidates:
        values.setdefault("IncTaxWithheld", sum(withheld_candidates))
    else:
        values.setdefault("IncTaxWithheld", "")

    # Estimated tax payments (26)
    values.setdefault("EstTaxPayments", _value_number(_field(result, "Box26")) or "")

    # Penalty/interest (Estimated tax penalty) — often line 38
    values.setdefault("LatePenInt", _value_number(_field(result, "Box38")) or "")

    # Refund / Direct deposit banking (35a–35d)
    values.setdefault("RoutingNumb1", _value_string(_field(result, "Box35a")))
    # Type of account (35c) — selectionGroup with Checking/Savings
    type_sel = _field(result, "Box35c")
    sel = []
    if isinstance(type_sel, dict):
        sel = type_sel.get("valueSelectionGroup") or []
    if sel:
        # Use first selected option's label
        values.setdefault("TypeOfAcct1", sel[0])
    else:
        values.setdefault("TypeOfAcct1", "")
    # Account number (choose 35d, else 35b)
    acc = _value_string(_field(result, "Box35d")) or _value_string(_field(result, "Box35b"))
    values.setdefault("AccountNumb1", acc)

    # Removed top-level CTC extraction per requirements

    # Dependent of another person (taxpayer/spouse) — from ClaimStatus selectionGroup
    claim = _field(result, "ClaimStatus")
    claim_sel = []
    if isinstance(claim, dict):
        claim_sel = claim.get("valueSelectionGroup") or []
    values.setdefault("DEPANPT", 1 if any(x in ("You", "Taxpayer") for x in claim_sel) else "")
    values.setdefault("DEPANSP", 1 if any(x == "Spouse" for x in claim_sel) else "")

    # Head-of-household qualifying person — map to provided name field
    values.setdefault("CHILDHOH", _value_string(_field(result, "NameOfSpouseOrQualifyingPerson")))

    # If filing status is unavailable, mark FSTATUSNF
    if not filing_selected:
        values.setdefault("FSTATUSNF", 1)
    else:
        values.setdefault("FSTATUSNF", "")

    # finally, build the row in the same order as Excel
    row = {}
    for name in field_names:
        row[name] = values.get(name, "")
    return row


# ---------------------------------------------------------------------------
# Identify the 1040 run from the pipeline JSON
# ---------------------------------------------------------------------------
def find_1040_job_ids(pipeline: dict) -> set[str]:
    job_ids = set()
    for item in pipeline.get("page_plan", []):
        label = item.get("label", "") or ""
        model_id = item.get("model_id", "") or ""
        job_id = item.get("job_id")
        # detect pages that belong to 1040
        if (
            label.startswith("Form_1040")
            or model_id == "prebuilt-tax.us.1040"
        ) and job_id:
            job_ids.add(job_id)
    return job_ids


def find_run_by_job_id(pipeline: dict, job_id: str) -> dict | None:
    for run in pipeline.get("runs", []):
        if run.get("job_id") == job_id:
            return run
    return None


# ---------------------------------------------------------------------------
# Locate pipeline JSON near this script
# ---------------------------------------------------------------------------
def find_pipeline_json() -> Path:
    # Prefer the known sample name if present next to the script or one level up
    preferred_name = "azure_pipeline_A7SDEPR3_Input-20251105-094523.json"
    candidates: list[Path] = []

    for base in (HERE, HERE.parent):
        p = base / preferred_name
        if p.exists():
            return p
        candidates.extend(sorted(base.glob("azure_pipeline_*.json")))

    if not candidates:
        raise FileNotFoundError(
            f"No pipeline JSON found. Looked in {HERE} and {HERE.parent} for 'azure_pipeline_*.json'"
        )

    # Choose the most recently modified candidate
    candidates = [p for p in candidates if p.is_file()]
    best = max(candidates, key=lambda p: p.stat().st_mtime)
    return best


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    # 1. find and load pipeline json
    pipeline_path = find_pipeline_json()
    with open(pipeline_path, "r") as f:
        pipeline = json.load(f)
    print(f"using pipeline -> {pipeline_path}")

    # 2. find 1040 job ids from page_plan
    job_ids = find_1040_job_ids(pipeline)
    if not job_ids:
        raise RuntimeError("No 1040 job_id found in page_plan")

    # just take the first 1040 run (pages 1-2 are paired under same job_id)
    first_job_id = next(iter(job_ids))

    # 3. get the actual run
    run = find_run_by_job_id(pipeline, first_job_id)
    if run is None:
        raise RuntimeError(f"Found 1040 job_id={first_job_id} but no matching run")

    result = run.get("result", {})
    if not result:
        raise RuntimeError("1040 run has no result payload")

    # 4. determine output field names (built-in order)
    field_names = get_field_names()

    # 5. map json -> output row
    row = build_row_from_result(result, field_names)

    # 6. write outputs (CSV and JSON)
    with open(OUTPUT_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        writer.writerow(row)

    # Build enhanced JSON payload: include dependents in preferred format.
    dep_format = (os.getenv("DEPENDENTS_FORMAT", "array").strip().lower() or "array")
    if dep_format == "jsonic":
        dependents_payload = make_dependents_jsonic(result)
    else:
        dependents_payload = make_dependents_array(result)

    json_out = dict(row)
    # Remove flat dependent fields from JSON output; keep only under `dependents`
    for _k in ("FNAME", "LNAME", "SSN", "RELATION"):
        json_out.pop(_k, None)
    json_out["dependents"] = dependents_payload

    # Top-level flag: whether any dependent qualifies for Other Dependent Credit
    dep_objs = _parse_dependents(result)
    has_other = any(bool(o.get("other_dependent_credit", False)) for o in dep_objs)
    json_out["OtherDependents"] = bool(has_other)

    with open(OUTPUT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2)
    print(f"written -> {OUTPUT_CSV_PATH}")
    print(f"written -> {OUTPUT_JSON_PATH}")


if __name__ == "__main__":
    main()


# ---------------------------------------------------------------------------
# Adapter for pipeline integration
# ---------------------------------------------------------------------------
def postprocess_combined(combined: dict, output_dir=None, options: dict | None = None) -> dict:
    """Adapter entrypoint for the Streamlit pipeline.

    - Expects `combined` with keys: page_plan (list) and runs (list).
    - Locates the 1040 run by job_id from page_plan where label startswith "Form_1040".
    - Writes mapped_output.csv/json next to this module unless output_dir is provided.
    - Returns a small artifact summary.
    """
    options = options or {}

    # Find 1040 job ids from the page_plan
    job_ids = set()
    for item in combined.get("page_plan", []):
        label = str(item.get("label") or "")
        job_id = item.get("job_id")
        action = item.get("action")
        if label.startswith("Form_1040") and job_id and action == "analyze":
            job_ids.add(job_id)

    # Find the first successful run corresponding to those job_ids
    run = None
    for r in combined.get("runs", []):
        if r.get("job_id") in job_ids and r.get("ok") and r.get("result"):
            run = r
            break
    if not run:
        raise RuntimeError("postprocess_combined: No successful 1040 run found in combined result")

    result = run.get("result") or {}

    # Build row and outputs
    field_names = get_field_names()
    row = build_row_from_result(result, field_names)

    # Choose output directory
    out_dir = Path(output_dir) if output_dir else HERE
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "mapped_output.csv"
    json_path = out_dir / "mapped_output.json"

    # Write CSV
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=field_names)
        writer.writeheader()
        writer.writerow(row)

    # Dependents formatting (prefer explicit option over env var)
    dep_format = None
    if isinstance(options, dict):
        dep_format = str(options.get("dependents_format") or "").strip().lower() or None
    if not dep_format:
        dep_format = (os.getenv("DEPENDENTS_FORMAT", "array").strip().lower() or "array")
    if dep_format == "jsonic":
        dependents_payload = make_dependents_jsonic(result)
    else:
        dependents_payload = make_dependents_array(result)

    json_out = dict(row)
    # Remove flat dependent fields from JSON output; keep only under `dependents`
    for _k in ("FNAME", "LNAME", "SSN", "RELATION"):
        json_out.pop(_k, None)
    json_out["dependents"] = dependents_payload
    dep_objs = _parse_dependents(result)
    has_other = any(bool(o.get("other_dependent_credit", False)) for o in dep_objs)
    json_out["OtherDependents"] = bool(has_other)

    # Write JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_out, f, ensure_ascii=False, indent=2)

    return {
        "artifacts": {
            "csv": str(csv_path),
            "json": str(json_path),
        },
        "job_id": run.get("job_id"),
        "pages": run.get("pages"),
        # Provide the mapped JSON payload so callers can embed it into combined
        "json_data": json_out,
    }
