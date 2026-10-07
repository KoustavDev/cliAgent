"""Helpers for normalizing environment mappings before subprocess execution."""

from collections.abc import Mapping
from typing import Any


def normalize_process_environment(
    environment: Mapping[Any, Any],
) -> dict[str, str]:
    """Convert configuration-provided environment entries to subprocess values."""
    normalized: dict[str, str] = {}
    # Step 1: Convert every non-null key/value pair to subprocess-safe strings.
    for key, value in environment.items():
        if key is None or value is None:
            raise ValueError(
                "Process environment entries cannot have null keys or values"
            )
        normalized[str(key)] = str(value)
    return normalized
