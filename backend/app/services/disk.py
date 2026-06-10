import shutil
from pathlib import Path

DEFAULT_HEADROOM_BYTES = 1024 * 1024 * 1024


def ensure_disk_space(path: Path, required_bytes: int, headroom_bytes: int = DEFAULT_HEADROOM_BYTES) -> None:
    """Raise RuntimeError if disk at *path* lacks required_bytes + headroom."""
    usage = shutil.disk_usage(path)
    needed = required_bytes + headroom_bytes
    if usage.free < needed:
        free_gb = usage.free / (1024**3)
        needed_gb = needed / (1024**3)
        raise RuntimeError(
            f"Insufficient disk space at {path}: {free_gb:.2f}GB free, "
            f"{needed_gb:.2f}GB required (output + 1GB headroom)"
        )
