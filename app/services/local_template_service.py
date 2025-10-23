from __future__ import annotations

"""Local template-based extraction service (integration stub).

This service does NOT perform real OCR/extraction. It loads a reference
template of expected fields (labels and types) from cjcode/form_fields.json
and returns a JSON structure with those fields initialized to placeholder
values. This lets the pipeline exercise planning/aggregation without calling
Azure.

Intended usage: map ML labels (e.g., Form_1040_P1/P2) to a special
"local-template:<Form Key>" model id, and dispatch to this service in the
pipeline when that model id is encountered.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO
import json
import re

# Optional heavy deps for actual extraction
try:
    import fitz  # PyMuPDF
    from PIL import Image
    HAVE_PYMUPDF = True
except Exception:
    HAVE_PYMUPDF = False

try:
    import pytesseract  # optional OCR fallback
    HAVE_TESS = True
except Exception:
    HAVE_TESS = False


def _project_root() -> Path:
    # services/ → app/ → ExtractionPipeline/
    return Path(__file__).resolve().parents[2]


def _default_template_path() -> Path:
    return _project_root() / "cjcode" / "form_fields.json"


def _template_dir() -> Path:
    """Single directory for coordinate templates (no fallback)."""
    return _project_root() / "local-templates"


def load_form_fields(template_path: Optional[Path] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Load cjcode/form_fields.json and return mapping of form key → fields list."""
    path = template_path or _default_template_path()
    with open(path, "r") as f:
        data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("form_fields.json must be a JSON object mapping form names to field definitions")
        return data


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def find_coordinate_template(form_key: str) -> Optional[Path]:
    """Find a coordinate template JSON that matches the given form key.

    Naming convention (recommended): "<profile>_<Form Key>_template.json"
    Example: "A7SDEPR3_Form 1040 Individual_template.json"
    """
    target = _normalize_name(form_key)
    candidates: List[Tuple[float, Path]] = []
    d = _template_dir()
    if d.exists():
        for p in d.glob("*_template.json"):
            # quick filename substring match on form key
            if target in _normalize_name(p.stem):
                try:
                    candidates.append((p.stat().st_mtime, p))
                except Exception:
                    candidates.append((0.0, p))
    if not candidates:
        return None
    # pick most recent
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _detect_checkbox_state(doc, page_num: int, rect_coords: List[float]) -> str:
    # Minimal implementation; requires PyMuPDF + PIL
    if not HAVE_PYMUPDF:
        return "Unknown"
    try:
        page = doc.load_page(int(page_num) - 1)
        scale = 5
        x0, y0, x1, y1 = rect_coords
        rect_to_render = fitz.Rect(x0, y0, x1, y1)
        pix = page.get_pixmap(clip=rect_to_render, matrix=fitz.Matrix(scale, scale))
        img = Image.open(BytesIO(pix.tobytes("ppm"))) if hasattr(Image, 'open') else None
        if img is None:
            return "Unknown"
        img = img.convert('L')
        width, height = img.size
        check_box = (
            int(width * 0.2),
            int(height * 0.2),
            int(width * 0.8),
            int(height * 0.8)
        )
        central_pixels = img.crop(check_box).getdata()
        dark_pixel_count = sum(1 for pixel in central_pixels if pixel < 100)
        total_pixels = len(central_pixels)
        dark_pixel_ratio = (dark_pixel_count / total_pixels) if total_pixels else 0.0
        return "Checked" if dark_pixel_ratio > 0.1 else "Unchecked"
    except Exception:
        return "Error"


def _extract_text_pymupdf(doc, page_num: int, rect_coords: List[float]) -> Optional[str]:
    if not HAVE_PYMUPDF:
        return None
    try:
        page = doc.load_page(int(page_num) - 1)
        rect = fitz.Rect(rect_coords)
        text = page.get_text(clip=rect, sort=True).strip()
        return text if text else None
    except Exception:
        return None


def _extract_text_tesseract(doc, page_num: int, rect_coords: List[float]) -> Optional[str]:
    """OCR fallback using Tesseract on a cropped, scaled image region.

    Requires PyMuPDF (to render) and pytesseract. Returns stripped text or None.
    """
    if not (HAVE_PYMUPDF and HAVE_TESS):
        return None
    try:
        page = doc.load_page(int(page_num) - 1)
        # Render full page at higher scale, then crop
        scale = 3
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
        img = Image.open(BytesIO(pix.tobytes("ppm"))) if hasattr(Image, 'open') else None
        if img is None:
            return None
        x0, y0, x1, y1 = rect_coords
        x0, y0, x1, y1 = [int(c * scale) for c in (x0, y0, x1, y1)]
        cropped = img.crop((x0, y0, x1, y1))
        text = pytesseract.image_to_string(cropped).strip()
        return text if text else None
    except Exception:
        return None


def _extract_with_coordinate_template(file_path: Path, pages: str, tmpl_path: Path, form_key: str) -> Dict[str, Any]:
    """Use a coordinate template (list of fields) to extract values with PyMuPDF."""
    if not HAVE_PYMUPDF:
        raise RuntimeError("PyMuPDF is required for coordinate template extraction")
    try:
        with open(tmpl_path, "r") as f:
            fields_def = json.load(f)
        if not isinstance(fields_def, list):
            raise ValueError("Coordinate template must be a list of field definitions")
    except Exception as e:
        raise RuntimeError(f"Failed to load template {tmpl_path}: {e}")

    out_fields: Dict[str, Any] = {}
    try:
        doc = fitz.open(file_path)
    except Exception as e:
        raise RuntimeError(f"Failed to open PDF {file_path}: {e}")

    try:
        for fld in fields_def:
            label = str(fld.get("label", "")).strip()
            if not label:
                continue
            ftype = str(fld.get("type", "text")).strip().lower()
            rect = fld.get("rect")
            page_num = fld.get("page")
            value = None
            if isinstance(rect, (list, tuple)) and page_num:
                if ftype == "checkbox":
                    value = _detect_checkbox_state(doc, int(page_num), list(rect))
                else:
                    # Try PyMuPDF text first, then OCR fallback
                    value = _extract_text_pymupdf(doc, int(page_num), list(rect))
                    if (value is None or str(value).strip() == ""):
                        ocr = _extract_text_tesseract(doc, int(page_num), list(rect))
                        value = ocr if (ocr is not None and ocr.strip() != "") else None
            out_fields[label] = {
                "type": "checkbox" if ftype == "checkbox" else "text",
                "value": value,
                "confidence": 0.0 if value in (None, "") else 0.5,  # placeholder confidence
            }
    finally:
        try:
            doc.close()
        except Exception:
            pass

    result = {
        "service": "local_form_template",
        "document": Path(file_path).name,
        "pages": pages,
        "form_key": form_key,
        "template_path": str(tmpl_path.resolve()),
        "fields": out_fields,
    }
    # If no field contains any data, signal failure like Azure by raising.
    has_any = False
    for k, v in out_fields.items():
        val = v.get("value")
        if isinstance(val, str):
            if val.strip():
                has_any = True
                break
        elif val not in (None, "", []):
            has_any = True
            break
    if not has_any:
        raise RuntimeError("No data extracted from local template regions")
    return result

def analyze_form_with_template(
    file_path: Path,
    *,
    pages: str,
    form_key: str = "Form 1040 Individual",
    template_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Analyze using a coordinate template; no skeleton fallback.

    - file_path: path to the PDF (opened only for coordinate templates)
    - pages: Azure-style pages spec (e.g., "1" or "1-2"); echoed in result
    - form_key: key in form_fields.json (e.g., "Form 1040 Individual")
    - template_path: optional override to the form_fields.json path
    """
    # Require a coordinate template in local-templates; otherwise signal failure
    coord_tmpl = find_coordinate_template(form_key)
    if coord_tmpl is None:
        raise FileNotFoundError(f"No coordinate template found in {_template_dir()} for form '{form_key}'")
    return _extract_with_coordinate_template(file_path, pages, coord_tmpl, form_key)
