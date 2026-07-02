import pytest

from epanet_tools.topology.identifiers import make_sequential_id


def test_make_sequential_id_defaults() -> None:
    assert make_sequential_id("J", 1) == "J000001"
    assert make_sequential_id("P", 42) == "P000042"


def test_make_sequential_id_custom_width() -> None:
    assert make_sequential_id("N", 7, width=3) == "N007"


def test_make_sequential_id_rejects_non_positive_numbers() -> None:
    with pytest.raises(ValueError, match="positive"):
        make_sequential_id("J", 0)


def test_make_sequential_id_rejects_empty_prefix() -> None:
    with pytest.raises(ValueError, match="prefix"):
        make_sequential_id("", 1)
