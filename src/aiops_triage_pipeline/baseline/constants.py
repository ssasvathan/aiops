"""Baseline deviation constants — single source of truth for all baseline components."""

MAD_CONSISTENCY_CONSTANT = 0.6745  # Scaling constant to make MAD consistent estimator of sigma
MAD_THRESHOLD = 4.0  # Modified z-score threshold for deviation classification
MIN_CORRELATED_DEVIATIONS = 2  # Minimum deviating metrics to emit a finding (correlation gate)
MIN_BUCKET_SAMPLES = 3  # Minimum historical samples required to compute MAD
MAX_BUCKET_VALUES = 12  # Maximum values stored per bucket (~12 weeks of weekly samples)
