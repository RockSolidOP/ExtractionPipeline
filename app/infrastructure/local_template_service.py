from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from io import BytesIO
import json
import re

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
    return Path(__file__).resolve().parents[2]


def _template_dir() -> Path:
    return _project_root() / "local-templates"


def _normalize_name(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def find_coordinate_template(form_key: str) -> Optional[Path]:
    target = _normalize_name(form_key)
    candidates: List[Tuple[float, Path]] = []
    d = _template_dir()
    if d.exists():
        for p in d.glob("*_template.json"):
            if target in _normalize_name(p.stem):
                try:
                    candidates.append((p.stat().st_mtime, p))
                except Exception:
                    candidates.append((0.0, p))
    if not candidates:
        return None
    candidates.sort(key=lambda t: t[0], reverse=True)
    return candidates[0][1]


def _detect_checkbox_state(doc, page_num: int, rect_coords: List[float]) -> str:
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
    if not (HAVE_PYMUPDF and HAVE_TESS):
        return None
    try:
        page = doc.load_page(int(page_num) - 1)
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
                    value = _extract_text_pymupdf(doc, int(page_num), list(rect))
                    if (value is None or str(value).strip() == ""):
                        ocr = _extract_text_tesseract(doc, int(page_num), list(rect))
                        value = ocr if (ocr is not None and ocr.strip() != "") else None
            out_fields[label] = {
                "type": "checkbox" if ftype == "checkbox" else "text",
                "value": value,
                "confidence": 0.0 if value in (None, "") else 0.5,
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
    coord_tmpl = find_coordinate_template(form_key)
    if coord_tmpl is None:
        raise FileNotFoundError(f"No coordinate template found in {_template_dir()} for form '{form_key}'")
    return _extract_with_coordinate_template(file_path, pages, coord_tmpl, form_key)

