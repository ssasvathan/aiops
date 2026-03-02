"""Prometheus Gauge definitions for the aiOps traffic harness.

All metric names are EXACT canonical names from prometheus-metrics-contract-v1.yaml (FROZEN).
DO NOT rename these metrics without updating the contract and bumping its version.
"""
from prometheus_client import Gauge

TOPIC_LABELS = ["env", "cluster_name", "topic"]
LAG_LABELS = ["env", "cluster_name", "group", "topic"]

messages_in = Gauge(
    "kafka_server_brokertopicmetrics_messagesinpersec",
    "Harness: messages in per second (canonical: primary ingress rate signal)",
    TOPIC_LABELS,
)
bytes_in = Gauge(
    "kafka_server_brokertopicmetrics_bytesinpersec",
    "Harness: bytes in per second",
    TOPIC_LABELS,
)
bytes_out = Gauge(
    "kafka_server_brokertopicmetrics_bytesoutpersec",
    "Harness: bytes out per second",
    TOPIC_LABELS,
)
failed_produce = Gauge(
    "kafka_server_brokertopicmetrics_failedproducerequestspersec",
    "Harness: failed produce requests per second",
    TOPIC_LABELS,
)
failed_fetch = Gauge(
    "kafka_server_brokertopicmetrics_failedfetchrequestspersec",
    "Harness: failed fetch requests per second",
    TOPIC_LABELS,
)
total_produce = Gauge(
    "kafka_server_brokertopicmetrics_totalproducerequestspersec",
    "Harness: total produce requests per second",
    TOPIC_LABELS,
)
total_fetch = Gauge(
    "kafka_server_brokertopicmetrics_totalfetchrequestspersec",
    "Harness: total fetch requests per second",
    TOPIC_LABELS,
)
group_lag = Gauge(
    "kafka_consumergroup_group_lag",
    "Harness: consumer group lag",
    LAG_LABELS,
)
group_offset = Gauge(
    "kafka_consumergroup_group_offset",
    "Harness: consumer group offset",
    LAG_LABELS,
)
