from __future__ import annotations

"""Extraction Pipeline page (ML-only)

What this page does
- Upload a PDF
- Runs the full pipeline (classify → plan → analyze → aggregate)
- Shows a compact JSON output and timings
"""

import streamlit as st
from pathlib import Path

# Ensure project root is on sys.path when running this page directly
try:  # noqa: SIM105
    from app.application.pipeline import run_pipeline
except ModuleNotFoundError:  # Running via `streamlit run pages/Extraction_Pipeline.py`
    import sys as _sys
    from pathlib import Path as _Path

    _ROOT = _Path(__file__).resolve().parents[1]
    if str(_ROOT) not in _sys.path:
        _sys.path.insert(0, str(_ROOT))
    from app.application.pipeline import run_pipeline

from app.ui.components import download_json_button, file_uploader
from app.infrastructure.storage.uploads import save_uploaded_file


def run() -> None:
    st.set_page_config(page_title="Extraction Pipeline", layout="wide")
    st.title("Extraction Pipeline")
    st.caption("Classification (ML) → Routing → Extraction → JSON output")

    uploaded = file_uploader("Upload a PDF (single file)", types=["pdf"])
    if not uploaded:
        st.info("Upload a PDF to start.")
        st.stop()
    pdf_path = save_uploaded_file(uploaded)
    st.caption(f"Saved: {pdf_path}")

    st.markdown("#### Post-Processor Options")
    use_jsonic_dependents = st.checkbox("Dependents as JSONic objects (else array)", value=False)

    # Show previous output if available
    if "combined_out" in st.session_state:
        st.markdown("#### Latest Combined Result (previous run)")
        st.json(st.session_state.get("combined_out"))
        download_json_button(
            "Download last result",
            data=st.session_state.get("combined_out"),
            filename=f"azure_pipeline_{Path(pdf_path).stem}.json",
        )

    if st.button("Run Extraction", type="primary"):
        result = run_pipeline(Path(pdf_path), use_jsonic_dependents=use_jsonic_dependents)

        st.success("Pipeline complete.")
        st.markdown("#### Timings")
        st.json(result.get("timings", {}))

        with st.expander("Classification (ML labels)", expanded=False):
            st.json(result.get("classified", []))

        with st.expander("Details: page plan", expanded=False):
            st.json({
                "file_name": Path(pdf_path).name,
                "page_plan": result.get("page_plan", []),
            })

        combined_out = result.get("combined_out", {})
        st.session_state["combined_out"] = combined_out
        st.markdown("#### Combined Result (JSON)")
        st.json(combined_out)
        download_json_button(
            "Download azure_pipeline.json",
            data=combined_out,
            filename=f"azure_pipeline_{Path(pdf_path).stem}.json",
        )


if __name__ == "__main__":
    run()
