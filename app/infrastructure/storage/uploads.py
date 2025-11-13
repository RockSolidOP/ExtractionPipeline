from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


def get_uploads_dir() -> Path:
    d = Path("uploads")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sanitize_filename(name: str) -> str:
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name or "file"


def save_uploaded_file(uploaded_file) -> Path:
    uploads = get_uploads_dir()
    original = getattr(uploaded_file, "name", "uploaded.pdf")
    safe = _sanitize_filename(original)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if "." in safe:
        stem = safe.rsplit(".", 1)[0]
        suffix = "." + safe.rsplit(".", 1)[1]
    else:
        stem = safe
        suffix = ""
    final_name = f"{stem}-{ts}{suffix}"
    path = uploads / final_name
    path.write_bytes(uploaded_file.read())
    return path


def dir_size_bytes(path: Path | None = None) -> int:
    d = path or get_uploads_dir()
    total = 0
    for p in d.glob("*"):
        try:
            if p.is_file():
                total += p.stat().st_size
        except FileNotFoundError:
            continue
    return total


def format_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024.0 or u == units[-1]:
            return f"{size:.1f} {u}"
        size /= 1024.0
    return f"{n} B"


def cleanup_uploads(
    *,
    max_age_days: int | None = None,
    max_total_size_mb: int | None = None,
    max_files: int | None = None,
) -> Dict[str, Any]:
    uploads = get_uploads_dir()
    files: List[Path] = [p for p in uploads.glob("*") if p.is_file()]

    entries = []
    for f in files:
        try:
            st = f.stat()
            entries.append({"path": f, "mtime": st.st_mtime, "size": st.st_size})
        except FileNotFoundError:
            pass

    deleted = []
    freed_bytes = 0

    if max_age_days is not None and max_age_days >= 0:
        cutoff = time.time() - max_age_days * 86400
        to_delete = [e for e in entries if e["mtime"] < cutoff]
        for e in sorted(to_delete, key=lambda x: x["mtime"]):
            try:
                e["path"].unlink(missing_ok=True)
                deleted.append(e["path"])
                freed_bytes += e["size"]
            except Exception:
                pass
        survivors = [e for e in entries if e["mtime"] >= cutoff]
        entries = survivors

    total_size = sum(e["size"] for e in entries)

    if max_total_size_mb is not None and max_total_size_mb >= 0:
        cap = max_total_size_mb * 1024 * 1024
        if total_size > cap:
            for e in sorted(entries, key=lambda x: x["mtime"]):
                if total_size <= cap:
                    break
                try:
                    e["path"].unlink(missing_ok=True)
                    deleted.append(e["path"])
                    total_size -= e["size"]
                    freed_bytes += e["size"]
                except Exception:
                    pass
            survivors = [e for e in entries if e["path"].exists()]
            entries = survivors

    if max_files is not None and max_files >= 0:
        if len(entries) > max_files:
            extras = sorted(entries, key=lambda x: x["mtime"])[: len(entries) - max_files]
            for e in extras:
                try:
                    e["path"].unlink(missing_ok=True)
                    deleted.append(e["path"])
                    freed_bytes += e["size"]
                except Exception:
                    pass
            survivors = [e for e in entries if e not in extras and e["path"].exists()]
            entries = survivors

    return {
        "deleted_count": len(deleted),
        "freed_bytes": int(freed_bytes),
        "remaining_count": len(entries),
        "remaining_size_bytes": int(sum(e["size"] for e in entries if e["path"].exists())),
    }

