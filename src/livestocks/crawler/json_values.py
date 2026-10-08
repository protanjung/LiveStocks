"""Helpers for reading loosely typed JSON without leaking unknown types.
as_dict and as_list narrow an arbitrary decoded value to a typed container, or None.
as_float and as_int accept only real numbers, never bools.
"""

from typing import Any, cast


def as_dict(value: Any) -> dict[str, Any] | None:
    """Return value as a str-keyed dict, or None if it is not a dict.
    Lets strict type checking see inside decoded JSON objects.
    Keys are assumed to be strings, as JSON guarantees.
    """
    return cast("dict[str, Any]", value) if isinstance(value, dict) else None


def as_list(value: Any) -> list[Any] | None:
    """Return value as a list of Any, or None if it is not a list.
    Lets strict type checking iterate decoded JSON arrays.
    Elements stay untyped until narrowed by the caller.
    """
    return cast("list[Any]", value) if isinstance(value, list) else None


def as_float(value: Any) -> float | None:
    """Return value as a float if it is a real number, else None.
    Booleans are rejected even though Python treats them as ints.
    Strings are never parsed.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def as_int(value: Any) -> int | None:
    """Return value as an int if it is a real number, else None.
    Booleans are rejected even though Python treats them as ints.
    Floats are truncated toward zero.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)
