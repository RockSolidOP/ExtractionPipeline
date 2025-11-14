from __future__ import annotations

from importlib import import_module
from typing import Any, Callable, Optional, Dict

# Post-processor selection maps
# Precedence: LABEL → BASE_LABEL → MODEL_PREFIX
POSTPROCESSOR_BY_LABEL: Dict[str, str] = {}
POSTPROCESSOR_BY_BASE_LABEL: Dict[str, str] = {
    "Form_1040": "app.plugins.post_processors.azure.form_1040:postprocess_combined",
    "Schedule_C": "app.plugins.post_processors.azure.form_schedule_c:postprocess_combined",
}
POSTPROCESSOR_BY_MODEL_PREFIX: Dict[str, str] = {}


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
