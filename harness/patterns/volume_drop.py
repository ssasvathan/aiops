"""Volume drop pattern: messages_in drops from normal to near-zero."""
import time

from metrics import bytes_in, messages_in


def run(duration: int, intensity: float) -> None:
    """Simulate a volume drop over `duration` seconds.

    First 30% of duration: normal rate. Remaining 70%: near-zero rate.
    """
    threshold = int(duration * 0.3)
    for tick in range(duration):
        if tick < threshold:
            rate = 500 * intensity  # normal baseline
        else:
            rate = 2.0  # near-zero (not exactly 0 — missing series → UNKNOWN rule applies)
        messages_in.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-vol-topic",
        ).set(rate)
        bytes_in.labels(
            env="harness",
            cluster_name="harness-cluster",
            topic="harness-vol-topic",
        ).set(rate * 200)  # ~200 bytes/msg
        time.sleep(1)
