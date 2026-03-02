"""Consumer lag buildup pattern: group_lag grows while group_offset stays fixed."""
import time

from metrics import group_lag, group_offset, messages_in


def run(duration: int, intensity: float) -> None:
    """Simulate consumer lag buildup over `duration` seconds."""
    for tick in range(duration):
        progress = tick / max(duration - 1, 1)
        group_lag.labels(
            env="harness",
            cluster_name="harness-cluster",
            group="harness-consumer",
            topic="harness-lag-topic",
        ).set(10_000 * intensity * progress)
        group_offset.labels(
            env="harness",
            cluster_name="harness-cluster",
            group="harness-consumer",
            topic="harness-lag-topic",
        ).set(1000.0)
        messages_in.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-lag-topic",
        ).set(500 * intensity)
        time.sleep(1)
