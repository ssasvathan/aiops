"""Unit tests for baseline/constants.py.

Story 1.1: Baseline Constants & Time Bucket Derivation
AC 1: constants.py exposes 5 SCREAMING_SNAKE_CASE constants at module level.
"""

from aiops_triage_pipeline.baseline import constants

# ---------------------------------------------------------------------------
# AC 1: Module-level constants are importable and have exact expected values
# ---------------------------------------------------------------------------


def test_mad_consistency_constant_value() -> None:
    """[P1] Given baseline constants module, MAD_CONSISTENCY_CONSTANT == 0.6745."""
    assert constants.MAD_CONSISTENCY_CONSTANT == 0.6745


def test_mad_threshold_value() -> None:
    """[P1] Given baseline constants module, MAD_THRESHOLD == 4.0."""
    assert constants.MAD_THRESHOLD == 4.0


def test_min_correlated_deviations_value() -> None:
    """[P1] Given baseline constants module, MIN_CORRELATED_DEVIATIONS == 2 (int)."""
    assert constants.MIN_CORRELATED_DEVIATIONS == 2
    assert isinstance(constants.MIN_CORRELATED_DEVIATIONS, int)


def test_min_bucket_samples_value() -> None:
    """[P1] Given baseline constants module, MIN_BUCKET_SAMPLES == 3 (int)."""
    assert constants.MIN_BUCKET_SAMPLES == 3
    assert isinstance(constants.MIN_BUCKET_SAMPLES, int)


def test_max_bucket_values_value() -> None:
    """[P1] Given baseline constants module, MAX_BUCKET_VALUES == 12 (int)."""
    assert constants.MAX_BUCKET_VALUES == 12
    assert isinstance(constants.MAX_BUCKET_VALUES, int)


# ---------------------------------------------------------------------------
# AC 1 (P2): Constants are module-level (not nested in functions or classes)
# ---------------------------------------------------------------------------


def test_constants_are_module_level_attributes() -> None:
    """[P1] All 5 constants are module-level SCREAMING_SNAKE_CASE attributes."""
    expected_constants = {
        "MAD_CONSISTENCY_CONSTANT",
        "MAD_THRESHOLD",
        "MIN_CORRELATED_DEVIATIONS",
        "MIN_BUCKET_SAMPLES",
        "MAX_BUCKET_VALUES",
    }
    module_attrs = set(dir(constants))
    assert expected_constants.issubset(module_attrs), (
        f"Missing constants: {expected_constants - module_attrs}"
    )


def test_constants_direct_import() -> None:
    """[P1] Constants are importable directly via 'from ... import' syntax."""
    from aiops_triage_pipeline.baseline.constants import (
        MAD_CONSISTENCY_CONSTANT,
        MAD_THRESHOLD,
        MAX_BUCKET_VALUES,
        MIN_BUCKET_SAMPLES,
        MIN_CORRELATED_DEVIATIONS,
    )

    assert MAD_CONSISTENCY_CONSTANT == 0.6745
    assert MAD_THRESHOLD == 4.0
    assert MIN_CORRELATED_DEVIATIONS == 2
    assert MIN_BUCKET_SAMPLES == 3
    assert MAX_BUCKET_VALUES == 12
