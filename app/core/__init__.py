"""Core infrastructure for configuration and logging.

Exposes a single `settings` object for application-wide configuration.
"""

from .settings import settings  # re-export for convenience

__all__ = ["settings"]

