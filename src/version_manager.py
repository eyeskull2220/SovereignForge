#!/usr/bin/env python3
"""
SovereignForge - Version Manager

Handles semantic version bumping (patch level) and learnings log updates.
Version is stored in core/config.py as VERSION = "vX.Y.Z".
"""

import logging
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "core" / "config.py"
LEARNINGS_PATH = Path(__file__).parent.parent / "learnings" / "LEARNINGS.md"


def get_current_version() -> str:
    """Read the current version from core/config.py."""
    if not CONFIG_PATH.exists():
        return "v1.0.0"

    content = CONFIG_PATH.read_text()
    match = re.search(r'VERSION:\s*str\s*=\s*"(v\d+\.\d+\.\d+)"', content)
    if match:
        return match.group(1)
    return "v1.0.0"


def bump_version() -> str:
    """Increment the patch version in core/config.py and return the new version."""
    current = get_current_version()

    match = re.match(r'v(\d+)\.(\d+)\.(\d+)', current)
    if not match:
        logger.warning(f"Could not parse version '{current}', defaulting to v1.0.1")
        new_version = "v1.0.1"
    else:
        major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
        new_version = f"v{major}.{minor}.{patch + 1}"

    # Update config file
    if CONFIG_PATH.exists():
        content = CONFIG_PATH.read_text()
        updated = re.sub(
            r'VERSION:\s*str\s*=\s*"v\d+\.\d+\.\d+"',
            f'VERSION: str = "{new_version}"',
            content
        )
        CONFIG_PATH.write_text(updated)
        logger.info(f"Version bumped: {current} → {new_version}")
    else:
        logger.warning(f"Config file not found at {CONFIG_PATH}")

    return new_version


def log_learning(version: str, message: str) -> None:
    """Append a versioned entry to learnings/LEARNINGS.md."""
    LEARNINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not LEARNINGS_PATH.exists():
        LEARNINGS_PATH.write_text("# SovereignForge Training Learnings\n\n")

    with open(LEARNINGS_PATH, "a") as f:
        f.write(f"\n## {version} — {timestamp}\n")
        f.write(f"- {message}\n")

    logger.info(f"Learning logged for {version}")
