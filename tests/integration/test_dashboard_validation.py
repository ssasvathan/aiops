"""Integration test: validate Grafana/Prometheus infrastructure config files.

Static config validation — no live docker-compose stack needed.
Tests run as part of the standard pytest suite.
"""
import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestPrometheusConfig:
    def test_aiops_pipeline_scrape_job_exists(self):
        config = yaml.safe_load((REPO_ROOT / "config/prometheus.yml").read_text())
        jobs = {job["job_name"] for job in config["scrape_configs"]}
        assert "aiops-pipeline" in jobs

    def test_aiops_pipeline_scrape_target(self):
        config = yaml.safe_load((REPO_ROOT / "config/prometheus.yml").read_text())
        job = next(j for j in config["scrape_configs"] if j["job_name"] == "aiops-pipeline")
        assert job["static_configs"][0]["targets"] == ["app:8080"]
        assert job["scrape_interval"] == "15s"


class TestGrafanaDatasourceConfig:
    def test_prometheus_datasource_exists(self):
        path = REPO_ROOT / "grafana/provisioning/datasources/prometheus.yaml"
        assert path.exists()
        config = yaml.safe_load(path.read_text())
        ds = config["datasources"][0]
        assert ds["type"] == "prometheus"
        assert ds["url"] == "http://prometheus:9090"
        assert ds["isDefault"] is True


class TestDashboardProvisioningConfig:
    def test_provider_config_exists(self):
        path = REPO_ROOT / "grafana/provisioning/dashboards/dashboards.yaml"
        assert path.exists()
        config = yaml.safe_load(path.read_text())
        assert len(config["providers"]) >= 1


class TestDashboardJsonShells:
    def test_main_dashboard_uid(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        assert path.exists()
        dashboard = json.loads(path.read_text())
        assert dashboard["uid"] == "aiops-main"

    def test_drilldown_dashboard_uid(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-drilldown.json"
        assert path.exists()
        dashboard = json.loads(path.read_text())
        assert dashboard["uid"] == "aiops-drilldown"

    def test_dashboards_have_no_panels_initially(self):
        for name in ("aiops-main.json", "aiops-drilldown.json"):
            path = REPO_ROOT / "grafana/dashboards" / name
            dashboard = json.loads(path.read_text())
            # Empty shells: panels may be empty list (will be populated in later stories)
            assert isinstance(dashboard.get("panels", []), list)
