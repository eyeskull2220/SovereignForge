"""
SovereignForge - Shared Utilities

Centralised helpers used across multiple modules.
"""

import logging
from types import ModuleType
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# psutil singleton loader
# ---------------------------------------------------------------------------
_psutil_checked = False
_psutil_module: Optional[ModuleType] = None


def get_psutil() -> Optional[ModuleType]:
    """Return the ``psutil`` module if available, or ``None``.

    A single WARNING is logged on the first call when psutil is not
    installed.  Subsequent calls return the cached result silently.
    """
    global _psutil_checked, _psutil_module

    if _psutil_checked:
        return _psutil_module

    _psutil_checked = True
    try:
        import psutil as _ps
        _psutil_module = _ps
    except ImportError:
        logger.warning(
            "psutil is not installed — system metrics (CPU, memory, disk) "
            "will be unavailable. Install with: pip install psutil"
        )
        _psutil_module = None

    return _psutil_module
