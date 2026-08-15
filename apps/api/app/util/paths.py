from pathlib import Path


def safe_path(base_dir: str, *segments: str) -> Path:
    """Resolve a path under ``base_dir``, rejecting traversal attempts."""
    base = Path(base_dir).resolve()
    target = base.joinpath(*segments).resolve()
    if target != base and not str(target).startswith(str(base) + "/"):
        raise ValueError("路径越界")
    return target
