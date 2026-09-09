from crm_reconciliation.normalize import (
    normalize_email,
    normalize_name,
    normalize_phone,
    normalize_zip,
)


def test_normalize_phone() -> None:
    variants = [
        "2107554721",
        "(210) 755-4721",
        "210-755-4721",
        "+1 210 755 4721",
    ]

    assert {
        normalize_phone(value)
        for value in variants
    } == {
        "2107554721"
    }


def test_normalize_email() -> None:
    assert (
        normalize_email(
            " Sarah@example.COM "
        )
        == "sarah@example.com"
    )


def test_normalize_name() -> None:
    assert (
        normalize_name(
            "Sarah Bartlett"
        )
        == normalize_name(
            "SARAH  BARTLETT"
        )
    )


def test_normalize_zip() -> None:
    assert (
        normalize_zip(
            "78240-1234"
        )
        == "78240"
    )
