"""Model backup utility -- copies current models before retraining."""

import shutil
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).parent.parent / "models" / "strategies"
BACKUP_DIR = Path(__file__).parent.parent / "models" / "backups"


def backup_models(tag: str = None) -> Path:
    """Backup current models to a timestamped directory.

    Returns the backup directory path.
    """
    if not MODELS_DIR.exists():
        logger.warning("No models directory to backup")
        return None

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    tag_str = f"_{tag}" if tag else ""
    backup_path = BACKUP_DIR / f"backup_{timestamp}{tag_str}"

    backup_path.mkdir(parents=True, exist_ok=True)

    count = 0
    for model_file in MODELS_DIR.glob("*.pth"):
        shutil.copy2(model_file, backup_path / model_file.name)
        count += 1

    # Also backup metadata files
    for meta_file in MODELS_DIR.glob("*_meta.json"):
        shutil.copy2(meta_file, backup_path / meta_file.name)
        count += 1

    logger.info(f"Backed up {count} files to {backup_path}")

    # Keep only last 3 backups
    all_backups = sorted(BACKUP_DIR.glob("backup_*"), reverse=True)
    for old_backup in all_backups[3:]:
        shutil.rmtree(old_backup, ignore_errors=True)
        logger.info(f"Removed old backup: {old_backup.name}")

    return backup_path


def restore_models(backup_path: Path) -> int:
    """Restore models from a backup directory."""
    if not backup_path.exists():
        logger.error(f"Backup not found: {backup_path}")
        return 0

    count = 0
    for model_file in backup_path.glob("*.pth"):
        shutil.copy2(model_file, MODELS_DIR / model_file.name)
        count += 1

    for meta_file in backup_path.glob("*_meta.json"):
        shutil.copy2(meta_file, MODELS_DIR / meta_file.name)
        count += 1

    logger.info(f"Restored {count} files from {backup_path}")
    return count


def list_backups() -> list:
    """List all available backups."""
    if not BACKUP_DIR.exists():
        return []
    return sorted(BACKUP_DIR.glob("backup_*"), reverse=True)
