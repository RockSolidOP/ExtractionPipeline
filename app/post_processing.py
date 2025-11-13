from __future__ import annotations

"""Post-processor plugin utilities.

Provides a small indirection layer so the pipeline UI can select and run
post-processors based on ML label, base_label, or model id.
"""

from importlib import import_module
from typing import Any, Callable, Optional

from app.config_classifier_ml_labels import (
    POSTPROCESSOR_BY_BASE_LABEL,
    POSTPROCESSOR_BY_LABEL,
    POSTPROCESSOR_BY_MODEL_PREFIX,
)


def load_callable(spec: str) -> Callable[..., Any]:
    """Load a callable from a "module:attr" spec string."""
    if not spec or ":" not in spec:
        raise ValueError(f"Invalid callable spec: {spec!r}")
    mod_name, func_name = spec.split(":", 1)
    mod = import_module(mod_name)
    fn = getattr(mod, func_name)
    if not callable(fn):
        raise TypeError(f"Target {spec!r} is not callable")
    return fn


def select_postprocessor(label: Optional[str], base_label: Optional[str], model_id: Optional[str]) -> Optional[str]:
    """Select a post-processor spec using config precedence.

    Precedence: exact label → base_label → model_id prefix match.
    """
    if label and label in POSTPROCESSOR_BY_LABEL:
        return POSTPROCESSOR_BY_LABEL[label]
    if base_label and base_label in POSTPROCESSOR_BY_BASE_LABEL:
        return POSTPROCESSOR_BY_BASE_LABEL[base_label]
    if model_id:
        low = model_id.lower()
        for prefix, spec in POSTPROCESSOR_BY_MODEL_PREFIX.items():
            if low.startswith(prefix.lower()):
                return spec
    return None


def run_postprocessor(spec: str, combined: dict, output_dir=None, **options) -> Any:
    """Load and run the specified post-processor callable.

    The callable signature is expected to be:
        fn(combined: dict, output_dir: Optional[pathlib.Path], options: dict) -> Any
    """
    fn = load_callable(spec)
    return fn(combined, output_dir, options)

