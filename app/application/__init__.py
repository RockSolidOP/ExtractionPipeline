"""Application layer: orchestration and use-cases.

Exports functions for planning and (later) pipeline orchestration.
"""

from .planning import build_page_plan

__all__ = ["build_page_plan"]

