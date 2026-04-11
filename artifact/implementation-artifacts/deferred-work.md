# Deferred Work

## Deferred from: code review of 1-3-evidence-diagnosis-otlp-instruments (2026-04-11)

- `_current_evidence_status` dict in `health/metrics.py` grows unbounded with topic churn — no pruning mechanism exists. Acceptable at current scale but should be addressed if topic cardinality grows significantly (hundreds of distinct topics cycling in/out). Consider LRU eviction or TTL-based cleanup in a future story.
