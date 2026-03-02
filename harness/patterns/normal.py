"""Normal baseline pattern: all metrics at stable, non-anomalous values."""
import time

from metrics import (
    bytes_in,
    bytes_out,
    failed_fetch,
    failed_produce,
    group_lag,
    group_offset,
    messages_in,
    total_fetch,
    total_produce,
)


def run(duration: int, intensity: float) -> None:
    """Emit stable baseline metrics for `duration` seconds.

    Emits all 9 canonical metrics for harness-normal-topic so the evidence pipeline
    sees a complete, non-anomalous baseline (no UNKNOWN series during normal state).
    """
    for _ in range(duration):
        messages_in.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-normal-topic",
        ).set(500 * intensity)
        bytes_in.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-normal-topic",
        ).set(100_000 * intensity)
        bytes_out.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-normal-topic",
        ).set(80_000 * intensity)
        total_produce.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-normal-topic",
        ).set(500 * intensity)
        total_fetch.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-normal-topic",
        ).set(500 * intensity)
        failed_produce.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-normal-topic",
        ).set(0.0)
        failed_fetch.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-normal-topic",
        ).set(0.0)
        group_lag.labels(
            env="harness",
            cluster_name="harness-cluster",
            group="harness-consumer",
            topic="harness-normal-topic",
        ).set(10.0)
        group_offset.labels(
            env="harness",
            cluster_name="harness-cluster",
            group="harness-consumer",
            topic="harness-normal-topic",
        ).set(50_000 * intensity)
        time.sleep(1)
