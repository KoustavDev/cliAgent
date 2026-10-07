"""Path resolution and lightweight filesystem inspection helpers."""

from pathlib import Path


def resolve_path(base: str | Path, path: str | Path):
    """Resolve an absolute path or anchor a relative path to ``base``."""
    # Step 1: Preserve absolute paths; resolve relative paths against the base.
    path = Path(path)
    if path.is_absolute():
        return path.resolve()

    return Path(base).resolve() / path


def display_path_rel_to_cwd(path: str, cwd: Path | None) -> str:
    """Format a path relative to the workspace when that is possible."""
    # Step 1: Prefer a concise path relative to the current working directory.
    try:
        p = Path(path)
    except Exception:
        return path

    if cwd:
        try:
            return str(p.relative_to(cwd))
        except ValueError:
            pass

    return str(p)


def ensure_parent_directory(path: str | Path) -> Path:
    """Create missing parent directories and return the normalized path."""
    # Step 1: Create missing parent directories before returning the path.
    path = Path(path)

    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def is_binary_file(path: str | Path) -> bool:
    """Detect a binary file by checking an initial chunk for null bytes."""
    # Step 1: Inspect an initial chunk for a null byte without decoding the file.
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, IOError):
        return False
