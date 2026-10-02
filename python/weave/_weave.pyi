from typing import Any

def merge(
    left: dict[Any, Any], right: dict[Any, Any], *, concat_lists: bool = False
) -> dict[Any, Any]:
    """Merge dicts recursively, optionally concatenating conflicting lists."""
    ...
