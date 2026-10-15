import pytest

from etk_core.values import dim_indices, parse_enum_value, parse_number


@pytest.mark.parametrize("text, expected", [
    ("0x1F", 31),
    ("0X10", 16),
    ("  0x0 ", 0),
    ("#101", 5),
    ("0b11", 3),
    ("42", 42),
    ("1_000", 1000),
])
def test_parse_number_accepts_svd_forms(text, expected):
    assert parse_number(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "zz", "0x", "1.5", "-1"])
def test_parse_number_rejects_bad_input(text):
    with pytest.raises(ValueError):
        parse_number(text)


def test_enum_concrete_value_uses_full_width_mask():
    assert parse_enum_value("3", 2) == (3, 3)


def test_enum_binary_with_dont_care_bits():
    assert parse_enum_value("#1XX", 3) == (4, 4)
    assert parse_enum_value("#0x1", 3) == (1, 5)


def test_dim_index_ranges_and_lists():
    assert dim_indices(3, "A-C") == ["A", "B", "C"]
    assert dim_indices(4, "1-4") == ["1", "2", "3", "4"]
    assert dim_indices(2, "a,b") == ["a", "b"]
    assert dim_indices(3, "a-c") == ["a", "b", "c"]
    assert dim_indices(2, None) == ["0", "1"]
    assert dim_indices(3, "0,2-3") == ["0", "2", "3"]
