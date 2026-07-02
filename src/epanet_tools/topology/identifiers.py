"""Deterministic identifier helpers for EPANET elements."""

from __future__ import annotations


def make_sequential_id(prefix: str, number: int, width: int = 6) -> str:
    """Return a stable sequential identifier such as ``J000001``.

    Parameters
    ----------
    prefix:
        Prefix used to identify the element class.
    number:
        Positive sequence number.
    width:
        Number of digits after the prefix.
    """
    if number < 1:
        msg = "Identifier sequence numbers must be positive."
        raise ValueError(msg)
    if not prefix:
        msg = "Identifier prefix cannot be empty."
        raise ValueError(msg)
    return f"{prefix}{number:0{width}d}"
