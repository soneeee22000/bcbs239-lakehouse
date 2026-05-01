"""Cold-start sanity test — verifies the package imports and the version is set."""

from __future__ import annotations

import pytest

import bcbs239_lakehouse


@pytest.mark.smoke
def test_package_imports() -> None:
    """The top-level package must import without side effects."""
    assert bcbs239_lakehouse.__version__ == "0.1.0"


@pytest.mark.smoke
def test_synthetic_module_importable() -> None:
    """The synthetic data generator module must import."""
    from bcbs239_lakehouse.data import synthetic

    assert synthetic.SYNTHETIC_LEI_PREFIX == "9999"


@pytest.mark.smoke
def test_quality_module_importable() -> None:
    """The DQ dimensions module must import and expose the 4 valid dimensions."""
    from bcbs239_lakehouse.quality import dimensions

    assert set(dimensions.VALID_DIMENSIONS) == {
        "completeness",
        "accuracy",
        "timeliness",
        "integrity",
    }
