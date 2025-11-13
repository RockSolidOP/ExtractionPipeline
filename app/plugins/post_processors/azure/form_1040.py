#!/usr/bin/env python3
from pathlib import Path
import os
import json
import csv

HERE = Path(__file__).resolve().parent

OUTPUT_CSV_PATH = HERE / "mapped_output.csv"
OUTPUT_JSON_PATH = HERE / "mapped_output.json"

DEFAULT_FIELD_NAMES = [
    "FSTATUSS", "FSTATUSH", "FSTATUSJ", "FSTATUSM", "FSTATUSQ", "FSTATUSNF",
    "TPFIRST", "TPLAST", "SSNTP", "SPFIRST", "SPLAST", "SSNSP",
    "OCCUPTP", "OCCUPSP",
    "STREET", "APTNO", "CITY", "STATE", "ZIP",
    "PRESELTP", "PRESELSP",
    "BLINDTP", "BLINDSP",
    "FNAME", "LNAME", "SSN", "RELATION",
    "PTIN", "PreparerPhone", "PrepEmail", "DAYPHONE", "TPEMAIL",
    "DEPANPT", "DEPANSP", "CHILDHOH",
    "InterestIncome", "DividendIncome", "SalariesWages",
    "TxblSocSec", "TxblIRADistrib", "TxblPensions",
    "TaxOnTxblIncome", "QualBusIncDed", "StandardDed",
    "IncTaxWithheld", "EstTaxPayments", "LatePenInt",
    "RoutingNumb1", "AccountNumb1", "TypeOfAcct1",
]


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
    content = field.get("content")
    if isinstance(content, str):
        digits = "".join(ch for ch in content if ch.isdigit() or ch == ".")
        if digits:
            try:
                return int(digits) if digits.isdigit() else float(digits)
            except Exception:
                return ""
    return ""


def get_field_names() -> list[str]:
    return DEFAULT_FIELD_NAMES


def _parse_dependents(result: dict) -> list[dict]:
    out: list[dict] = []
    deps = result.get("Dependents", {}).get("valueArray", []) or []
    for d in deps:
        vo = d.get("valueObject", {}) if isinstance(d, dict) else {}
        name_raw = _value_string(vo.get("Name"))
        first_name, last_name = "", ""
        if name_raw:
            parts = name_raw.split("\n")
            if len(parts) == 1:
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

    filing = get_in(result, ["FilingStatus", "valueSelectionGroup"], []) or []
    filing_selected = filing[0] if filing else None
    filing_map = {
        "Single": "FSTATUSS",
        "HeadOfHousehold": "FSTATUSH",
        "MarriedFilingJointly": "FSTATUSJ",
        "MarriedFilingSeparately": "FSTATUSM",
        "QualifyingSurvivingSpouse": "FSTATUSQ",
    }

    pres = get_in(result, ["PresidentialElectionCampaign", "valueSelectionGroup"], []) or []

    values = {}

    if filing_selected and filing_selected in filing_map:
        values[filing_map[filing_selected]] = 1

    values["TPFIRST"] = get_in(taxpayer, ["FirstNameAndInitials", "valueString"])
    values["TPLAST"] = get_in(taxpayer, ["LastName", "valueString"])
    values["SSNTP"] = get_in(taxpayer, ["SSN", "valueString"])

    values["SPFIRST"] = get_in(spouse, ["FirstNameAndInitials", "valueString"])
    values["SPLAST"] = get_in(spouse, ["LastName", "valueString"])
    values["SSNSP"] = get_in(spouse, ["SSN", "valueString"])

    values["OCCUPTP"] = get_in(sig, ["TaxpayerOccupation", "valueString"])
    values["OCCUPSP"] = get_in(sig, ["SpouseOccupation", "valueString"])

    values["STREET"] = addr.get("streetAddress")
    values["APTNO"] = ""
    values["CITY"] = addr.get("city")
    values["STATE"] = addr.get("state")
    values["ZIP"] = addr.get("postalCode")

    values["PRESELTP"] = 1 if "Taxpayer" in pres else ""
    values["PRESELSP"] = 1 if "Spouse" in pres else ""

    values["BLINDTP"] = ""
    values["BLINDSP"] = ""

    dep_name = get_in(dep1, ["Name", "valueString"])
    if dep_name:
        parts = dep_name.split("\n")
        if len(parts) > 0:
            values["FNAME"] = parts[0]
        if len(parts) > 1:
            values["LNAME"] = parts[1]
    values["SSN"] = get_in(dep1, ["SSN", "valueString"])
    values["RELATION"] = get_in(dep1, ["RelationshipToFiler", "valueString"])

    values["PTIN"] = get_in(prep, ["PreparerPTIN", "valueString"])
    values["PreparerPhone"] = get_in(prep, ["PreparerFirmPhoneNumber", "valueString"])
    values["PrepEmail"] = ""

    values["DAYPHONE"] = get_in(sig, ["TaxpayerPhoneNumber", "valueString"]) or ""
    values["TPEMAIL"] = get_in(sig, ["TaxpayerEmail", "valueString"]) or ""

    values.setdefault("SalariesWages", _value_number(_field(result, "Box1z")) or _value_number(_field(result, "Box1a")) or "")
    values.setdefault("InterestIncome", _value_number(_field(result, "Box2b")) or "")
    values.setdefault("DividendIncome", _value_number(_field(result, "Box3b")) or "")
    values.setdefault("TxblIRADistrib", _value_number(_field(result, "Box4b")) or "")
    values.setdefault("TxblPensions", _value_number(_field(result, "Box4d")) if _field(result, "Box4d") else "")
    values.setdefault("TxblSocSec", _value_number(_field(result, "Box5b")) or "")
    values.setdefault("StandardDed", _value_number(_field(result, "Box12")) or "")
    values.setdefault("QualBusIncDed", _value_number(_field(result, "Box13")) or "")
    values.setdefault("TaxOnTxblIncome", _value_number(_field(result, "Box16")) or "")

    b25a = _value_number(_field(result, "Box25a"))
    b25b = _value_number(_field(result, "Box25b"))
    b25c = _value_number(_field(result, "Box25c"))
    b25d = _value_number(_field(result, "Box25d")) if _field(result, "Box25d") else None
    if b25a or b25b or b25c:
        total_withheld = sum(v for v in [b25a, b25b, b25c] if isinstance(v, (int, float))) or ""
        values.setdefault("IncTaxWithheld", total_withheld)
    elif b25d is not None:
        values.setdefault("IncTaxWithheld", b25d)

    values.setdefault("EstTaxPayments", _value_number(_field(result, "Box26")) or "")
    values.setdefault("LatePenInt", _value_number(_field(result, "Box38")) or "")

    values.setdefault("RoutingNumb1", "")
    values.setdefault("AccountNumb1", "")
    values.setdefault("TypeOfAcct1", "")

    return {k: values.get(k, "") for k in field_names}


def postprocess_combined(combined: dict, output_dir=None, options: dict | None = None) -> dict:
    job_ids = set()
    for item in combined.get("page_plan", []):
        label = str(item.get("label") or "")
        job_id = item.get("job_id")
        action = item.get("action")
        if label.startswith("Form_1040") and job_id and action == "analyze":
            job_ids.add(job_id)

    run = None
    for r in combined.get("runs", []):
        if r.get("job_id") in job_ids and r.get("ok") and r.get("result"):
            run = r
            break
    if not run:
        raise RuntimeError("postprocess_combined: No successful 1040 run found in combined result")

    result = run.get("result") or {}
    field_names = get_field_names()
    row = build_row_from_result(result, field_names)

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
    for _k in ("FNAME", "LNAME", "SSN", "RELATION"):
        json_out.pop(_k, None)
    json_out["dependents"] = dependents_payload
    dep_objs = _parse_dependents(result)
    has_other = any(bool(o.get("other_dependent_credit", False)) for o in dep_objs)
    json_out["OtherDependents"] = bool(has_other)

    artifacts = {}
    save_artifacts = bool((options or {}).get("save_artifacts")) or (output_dir is not None)
    if save_artifacts:
        out_dir = Path(output_dir) if output_dir else HERE
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path = out_dir / "mapped_output.csv"
        json_path = out_dir / "mapped_output.json"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            writer.writerow(row)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_out, f, ensure_ascii=False, indent=2)
        artifacts = {"csv": str(csv_path), "json": str(json_path)}

    return {
        "artifacts": artifacts,
        "job_id": run.get("job_id"),
        "pages": run.get("pages"),
        "json_data": json_out,
    }

