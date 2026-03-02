"""Throughput-constrained proxy pattern: high messages_in with elevated failed_produce."""
import time

from metrics import bytes_in, failed_produce, messages_in, total_produce


def run(duration: int, intensity: float) -> None:
    """Simulate throughput-constrained broker proxy over `duration` seconds."""
    for _ in range(duration):
        messages_in.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-proxy-topic",
        ).set(5000 * intensity)
        bytes_in.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-proxy-topic",
        ).set(1_000_000 * intensity)
        total_produce.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-proxy-topic",
        ).set(1000 * intensity)
        failed_produce.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-proxy-topic",
        ).set(50 * intensity)  # 5% error rate
        time.sleep(1)
