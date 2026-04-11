"""ATDD acceptance tests for Story 1.1: Grafana & Prometheus Observability Infrastructure.

These tests validate static configuration correctness — no live docker-compose stack needed.
Tests were written in TDD red phase and are now green (implementation complete).

Tests cover:
  AC1: Grafana service definition in docker-compose.yml (image, env vars, volumes)
  AC2: Prometheus datasource provisioning file (url, isDefault, access:proxy)
  AC3: Dashboard provisioning config + empty JSON shells with hardcoded UIDs
  AC4: Prometheus scrape job 'aiops-pipeline' targeting app:8080 with 15s interval
  AC5: Grafana healthcheck and depends_on prometheus present (startup readiness)

Story: 1.1
File: tests/integration/test_infra_story_1_1_grafana_prometheus_red_phase.py
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# AC1 — docker-compose.yml: Grafana service definition
# ---------------------------------------------------------------------------


class TestAC1GrafanaServiceInDockerCompose:
    """AC1: Grafana OSS 12.4.2 running with anonymous auth and correct volume mounts."""

    def _load_compose(self) -> dict:
        path = REPO_ROOT / "docker-compose.yml"
        assert path.exists(), "docker-compose.yml not found at repo root"
        return yaml.safe_load(path.read_text())

    def test_p0_grafana_service_is_defined(self) -> None:
        """AC1 P0: docker-compose must define a 'grafana' service."""
        compose = self._load_compose()
        assert "grafana" in compose.get("services", {}), (
            "Story 1.1 RED phase: 'grafana' service not found in docker-compose.yml. "
            "Add grafana service block per dev notes."
        )

    def test_p0_grafana_image_pinned_to_oss_12_4_2(self) -> None:
        """AC1 P0: Grafana image must be exactly grafana/grafana-oss:12.4.2 (not latest)."""
        compose = self._load_compose()
        services = compose.get("services", {})
        grafana = services.get("grafana", {})
        assert grafana.get("image") == "grafana/grafana-oss:12.4.2", (
            "Story 1.1 RED phase: grafana image must be pinned to "
            "'grafana/grafana-oss:12.4.2'. "
            f"Found: {grafana.get('image')!r}"
        )

    def test_p0_grafana_anonymous_auth_enabled_via_gf_env_vars(self) -> None:
        """AC1 P0: GF_AUTH_ANONYMOUS_ENABLED must be 'true' via environment variable."""
        compose = self._load_compose()
        env = compose.get("services", {}).get("grafana", {}).get("environment", {})
        # environment can be a dict or a list in compose; normalise.
        if isinstance(env, list):
            env = dict(item.split("=", 1) for item in env if "=" in item)
        assert env.get("GF_AUTH_ANONYMOUS_ENABLED") == "true", (
            "Story 1.1 RED phase: GF_AUTH_ANONYMOUS_ENABLED env var must be 'true'. "
            f"Found: {env.get('GF_AUTH_ANONYMOUS_ENABLED')!r}"
        )

    def test_p0_grafana_anonymous_org_role_is_admin(self) -> None:
        """AC1 P0: GF_AUTH_ANONYMOUS_ORG_ROLE must be 'Admin' for anonymous access."""
        compose = self._load_compose()
        env = compose.get("services", {}).get("grafana", {}).get("environment", {})
        if isinstance(env, list):
            env = dict(item.split("=", 1) for item in env if "=" in item)
        assert env.get("GF_AUTH_ANONYMOUS_ORG_ROLE") == "Admin", (
            "Story 1.1 RED phase: GF_AUTH_ANONYMOUS_ORG_ROLE must be 'Admin'. "
            f"Found: {env.get('GF_AUTH_ANONYMOUS_ORG_ROLE')!r}"
        )

    def test_p0_grafana_volume_mount_provisioning_path(self) -> None:
        """AC1 P0: Volume must map ./grafana/provisioning:/etc/grafana/provisioning."""
        compose = self._load_compose()
        volumes = compose.get("services", {}).get("grafana", {}).get("volumes", [])
        provisioning_mount = "./grafana/provisioning:/etc/grafana/provisioning"
        assert any(
            str(v).startswith(provisioning_mount) or str(v) == provisioning_mount
            for v in volumes
        ), (
            f"Story 1.1 RED phase: grafana volumes must contain '{provisioning_mount}'. "
            f"Found volumes: {volumes!r}"
        )

    def test_p0_grafana_volume_mount_dashboards_path(self) -> None:
        """AC1 P0: Volume must map ./grafana/dashboards:/var/lib/grafana/dashboards."""
        compose = self._load_compose()
        volumes = compose.get("services", {}).get("grafana", {}).get("volumes", [])
        dashboard_mount = "./grafana/dashboards:/var/lib/grafana/dashboards"
        assert any(
            str(v).startswith(dashboard_mount) or str(v) == dashboard_mount
            for v in volumes
        ), (
            f"Story 1.1 RED phase: grafana volumes must contain '{dashboard_mount}'. "
            f"Found volumes: {volumes!r}"
        )

    def test_p1_grafana_data_volume_declared_in_top_level_volumes(self) -> None:
        """AC1 P1: grafana-data volume must be declared in top-level volumes section."""
        compose = self._load_compose()
        top_level_volumes = compose.get("volumes", {})
        assert "grafana-data" in top_level_volumes, (
            "Story 1.1 RED phase: 'grafana-data' volume not found in top-level volumes section. "
            f"Found volumes: {list(top_level_volumes.keys())!r}"
        )


# ---------------------------------------------------------------------------
# AC2 — Prometheus datasource provisioning
# ---------------------------------------------------------------------------


class TestAC2PrometheusDatasourceProvisioning:
    """AC2: Prometheus is auto-configured as default datasource pointing to http://prometheus:9090."""

    def test_p0_datasource_provisioning_file_exists(self) -> None:
        """AC2 P0: grafana/provisioning/datasources/prometheus.yaml must exist."""
        path = REPO_ROOT / "grafana/provisioning/datasources/prometheus.yaml"
        assert path.exists(), (
            "Story 1.1 RED phase: datasource provisioning file not found at "
            f"{path.relative_to(REPO_ROOT)}. Create the file per dev notes."
        )

    def test_p0_datasource_type_is_prometheus(self) -> None:
        """AC2 P0: datasource type must be 'prometheus'."""
        path = REPO_ROOT / "grafana/provisioning/datasources/prometheus.yaml"
        assert path.exists(), f"File missing: {path}"
        config = yaml.safe_load(path.read_text())
        datasources = config.get("datasources", [])
        assert len(datasources) >= 1, "datasources list is empty"
        ds = datasources[0]
        assert ds.get("type") == "prometheus", (
            f"Story 1.1 RED phase: datasource type must be 'prometheus'. Found: {ds.get('type')!r}"
        )

    def test_p0_datasource_url_points_to_internal_prometheus(self) -> None:
        """AC2 P0: datasource url must be http://prometheus:9090 (internal docker network)."""
        path = REPO_ROOT / "grafana/provisioning/datasources/prometheus.yaml"
        assert path.exists(), f"File missing: {path}"
        config = yaml.safe_load(path.read_text())
        ds = config["datasources"][0]
        assert ds.get("url") == "http://prometheus:9090", (
            "Story 1.1 RED phase: datasource url must be 'http://prometheus:9090'. "
            f"Found: {ds.get('url')!r}. Must use internal docker network name."
        )

    def test_p0_datasource_is_set_as_default(self) -> None:
        """AC2 P0: Prometheus datasource must be the default (isDefault: true)."""
        path = REPO_ROOT / "grafana/provisioning/datasources/prometheus.yaml"
        assert path.exists(), f"File missing: {path}"
        config = yaml.safe_load(path.read_text())
        ds = config["datasources"][0]
        assert ds.get("isDefault") is True, (
            f"Story 1.1 RED phase: isDefault must be true. Found: {ds.get('isDefault')!r}"
        )

    def test_p0_datasource_access_is_proxy(self) -> None:
        """AC2 P0: access must be 'proxy' — Grafana fetches from Prometheus server-side."""
        path = REPO_ROOT / "grafana/provisioning/datasources/prometheus.yaml"
        assert path.exists(), f"File missing: {path}"
        config = yaml.safe_load(path.read_text())
        ds = config["datasources"][0]
        assert ds.get("access") == "proxy", (
            "Story 1.1 RED phase: access must be 'proxy' (not 'direct'). "
            f"Found: {ds.get('access')!r}"
        )

    def test_p1_datasource_time_interval_matches_scrape_interval(self) -> None:
        """AC2 P1: jsonData.timeInterval must be '15s' to match Prometheus scrape_interval."""
        path = REPO_ROOT / "grafana/provisioning/datasources/prometheus.yaml"
        assert path.exists(), f"File missing: {path}"
        config = yaml.safe_load(path.read_text())
        ds = config["datasources"][0]
        time_interval = ds.get("jsonData", {}).get("timeInterval")
        assert time_interval == "15s", (
            f"Story 1.1 RED phase: jsonData.timeInterval must be '15s' (NFR11). "
            f"Found: {time_interval!r}"
        )


# ---------------------------------------------------------------------------
# AC3 — Dashboard provisioning + empty JSON shells
# ---------------------------------------------------------------------------


class TestAC3DashboardProvisioningAndJsonShells:
    """AC3: Empty dashboard shells auto-loaded with hardcoded UIDs that survive re-provisioning."""

    def test_p0_dashboard_provisioning_config_exists(self) -> None:
        """AC3 P0: grafana/provisioning/dashboards/dashboards.yaml must exist."""
        path = REPO_ROOT / "grafana/provisioning/dashboards/dashboards.yaml"
        assert path.exists(), (
            "Story 1.1 RED phase: dashboard provisioning config not found at "
            f"{path.relative_to(REPO_ROOT)}."
        )

    def test_p0_dashboard_provisioning_has_at_least_one_provider(self) -> None:
        """AC3 P0: dashboards.yaml must have at least one provider entry."""
        path = REPO_ROOT / "grafana/provisioning/dashboards/dashboards.yaml"
        assert path.exists(), f"File missing: {path}"
        config = yaml.safe_load(path.read_text())
        providers = config.get("providers", [])
        assert len(providers) >= 1, (
            f"Story 1.1 RED phase: providers list must have at least 1 entry. Found: {providers!r}"
        )

    def test_p0_dashboard_provider_allow_ui_updates_is_true(self) -> None:
        """AC3 P0: allowUiUpdates must be true (required for hybrid UI-first design workflow)."""
        path = REPO_ROOT / "grafana/provisioning/dashboards/dashboards.yaml"
        assert path.exists(), f"File missing: {path}"
        config = yaml.safe_load(path.read_text())
        provider = config["providers"][0]
        assert provider.get("allowUiUpdates") is True, (
            "Story 1.1 RED phase: allowUiUpdates must be true in dashboard provider. "
            f"Found: {provider.get('allowUiUpdates')!r}"
        )

    def test_p0_main_dashboard_json_exists(self) -> None:
        """AC3 P0: grafana/dashboards/aiops-main.json must exist."""
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        assert path.exists(), (
            "Story 1.1 RED phase: dashboard shell not found at "
            f"{path.relative_to(REPO_ROOT)}."
        )

    def test_p0_main_dashboard_uid_is_aiops_main(self) -> None:
        """AC3 P0: aiops-main.json uid must be exactly 'aiops-main' (hardcoded constant)."""
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        assert path.exists(), f"File missing: {path}"
        dashboard = json.loads(path.read_text())
        assert dashboard.get("uid") == "aiops-main", (
            "Story 1.1 RED phase: main dashboard uid must be 'aiops-main'. "
            f"Found: {dashboard.get('uid')!r}. "
            "UID is a hardcoded constant referenced by inter-dashboard links."
        )

    def test_p0_drilldown_dashboard_json_exists(self) -> None:
        """AC3 P0: grafana/dashboards/aiops-drilldown.json must exist."""
        path = REPO_ROOT / "grafana/dashboards/aiops-drilldown.json"
        assert path.exists(), (
            "Story 1.1 RED phase: drilldown dashboard shell not found at "
            f"{path.relative_to(REPO_ROOT)}."
        )

    def test_p0_drilldown_dashboard_uid_is_aiops_drilldown(self) -> None:
        """AC3 P0: aiops-drilldown.json uid must be 'aiops-drilldown' (hardcoded constant)."""
        path = REPO_ROOT / "grafana/dashboards/aiops-drilldown.json"
        assert path.exists(), f"File missing: {path}"
        dashboard = json.loads(path.read_text())
        assert dashboard.get("uid") == "aiops-drilldown", (
            "Story 1.1 RED phase: drilldown dashboard uid must be 'aiops-drilldown'. "
            f"Found: {dashboard.get('uid')!r}. "
            "UID is a hardcoded constant referenced by inter-dashboard links."
        )

    def test_p1_main_dashboard_panels_is_empty_list(self) -> None:
        """AC3 P1: aiops-main.json panels must be an empty list (shell — no panels yet)."""
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        assert path.exists(), f"File missing: {path}"
        dashboard = json.loads(path.read_text())
        panels = dashboard.get("panels", None)
        assert isinstance(panels, list), (
            f"Story 1.1 RED phase: panels must be a list. Found type: {type(panels)}"
        )
        assert panels == [], (
            f"Story 1.1 RED phase: panels must be empty list (shell). Found: {panels!r}"
        )

    def test_p1_drilldown_dashboard_panels_is_empty_list(self) -> None:
        """AC3 P1: aiops-drilldown.json panels must be an empty list (shell — no panels yet)."""
        path = REPO_ROOT / "grafana/dashboards/aiops-drilldown.json"
        assert path.exists(), f"File missing: {path}"
        dashboard = json.loads(path.read_text())
        panels = dashboard.get("panels", None)
        assert isinstance(panels, list), (
            f"Story 1.1 RED phase: panels must be a list. Found type: {type(panels)}"
        )
        assert panels == [], (
            f"Story 1.1 RED phase: panels must be empty list (shell). Found: {panels!r}"
        )

    def test_p1_main_dashboard_schema_version_is_39(self) -> None:
        """AC3 P1: schemaVersion must be 39 (Grafana 12.x standard)."""
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        assert path.exists(), f"File missing: {path}"
        dashboard = json.loads(path.read_text())
        assert dashboard.get("schemaVersion") == 39, (
            "Story 1.1 RED phase: schemaVersion must be 39 for Grafana 12.x. "
            f"Found: {dashboard.get('schemaVersion')!r}"
        )

    def test_p1_drilldown_dashboard_schema_version_is_39(self) -> None:
        """AC3 P1: aiops-drilldown.json schemaVersion must be 39."""
        path = REPO_ROOT / "grafana/dashboards/aiops-drilldown.json"
        assert path.exists(), f"File missing: {path}"
        dashboard = json.loads(path.read_text())
        assert dashboard.get("schemaVersion") == 39, (
            "Story 1.1 RED phase: schemaVersion must be 39 for Grafana 12.x. "
            f"Found: {dashboard.get('schemaVersion')!r}"
        )


# ---------------------------------------------------------------------------
# AC4 — Prometheus scrape job for aiops-pipeline
# ---------------------------------------------------------------------------


class TestAC4PrometheusScrapeJob:
    """AC4: Scrape job 'aiops-pipeline' targets app:8080 at 15s interval; retention=15d."""

    def _load_prometheus_config(self) -> dict:
        path = REPO_ROOT / "config/prometheus.yml"
        assert path.exists(), "config/prometheus.yml not found"
        return yaml.safe_load(path.read_text())

    def test_p0_aiops_pipeline_scrape_job_exists(self) -> None:
        """AC4 P0: prometheus.yml must contain a scrape job named 'aiops-pipeline'."""
        config = self._load_prometheus_config()
        job_names = {job["job_name"] for job in config.get("scrape_configs", [])}
        assert "aiops-pipeline" in job_names, (
            "Story 1.1 RED phase: 'aiops-pipeline' scrape job not found in config/prometheus.yml. "
            f"Existing jobs: {sorted(job_names)!r}"
        )

    def test_p0_aiops_pipeline_targets_app_8080(self) -> None:
        """AC4 P0: aiops-pipeline job must target 'app:8080'."""
        config = self._load_prometheus_config()
        job = next(
            (j for j in config.get("scrape_configs", []) if j["job_name"] == "aiops-pipeline"),
            None,
        )
        assert job is not None, "aiops-pipeline job missing"
        targets = job.get("static_configs", [{}])[0].get("targets", [])
        assert "app:8080" in targets, (
            "Story 1.1 RED phase: aiops-pipeline job must target 'app:8080'. "
            f"Found targets: {targets!r}"
        )

    def test_p0_aiops_pipeline_scrape_interval_is_15s(self) -> None:
        """AC4 P0: aiops-pipeline scrape_interval must be '15s' (NFR11 compliance)."""
        config = self._load_prometheus_config()
        job = next(
            (j for j in config.get("scrape_configs", []) if j["job_name"] == "aiops-pipeline"),
            None,
        )
        assert job is not None, "aiops-pipeline job missing"
        assert job.get("scrape_interval") == "15s", (
            "Story 1.1 RED phase: aiops-pipeline scrape_interval must be '15s' (NFR11). "
            f"Found: {job.get('scrape_interval')!r}"
        )

    def test_p0_prometheus_retention_flag_in_docker_compose(self) -> None:
        """AC4 P0: Prometheus command in docker-compose must include retention.time=15d (NFR7)."""
        compose_path = REPO_ROOT / "docker-compose.yml"
        assert compose_path.exists(), "docker-compose.yml not found"
        compose = yaml.safe_load(compose_path.read_text())
        prometheus = compose.get("services", {}).get("prometheus", {})
        command = prometheus.get("command", [])
        retention_flag = "--storage.tsdb.retention.time=15d"
        assert any(
            retention_flag in str(c) for c in command
        ), (
            f"Story 1.1 RED phase: prometheus command must include '{retention_flag}' (NFR7). "
            f"Found command: {command!r}"
        )


# ---------------------------------------------------------------------------
# AC5 — Stack startup readiness: healthcheck and depends_on
# ---------------------------------------------------------------------------


class TestAC5GrafanaHealthcheckAndDependency:
    """AC5: Stack reaches healthy state — grafana healthcheck present and depends on prometheus."""

    def _load_compose(self) -> dict:
        path = REPO_ROOT / "docker-compose.yml"
        assert path.exists(), "docker-compose.yml not found"
        return yaml.safe_load(path.read_text())

    def test_p0_grafana_has_healthcheck_defined(self) -> None:
        """AC5 P0: grafana service must have a healthcheck (required for depends_on condition)."""
        compose = self._load_compose()
        grafana = compose.get("services", {}).get("grafana", {})
        assert "healthcheck" in grafana, (
            "Story 1.1 RED phase: grafana service must define a healthcheck. "
            "Required for depends_on: condition: service_healthy in dependent services."
        )

    def test_p0_grafana_healthcheck_uses_api_health_endpoint(self) -> None:
        """AC5 P0: grafana healthcheck must verify /api/health endpoint."""
        compose = self._load_compose()
        grafana = compose.get("services", {}).get("grafana", {})
        healthcheck = grafana.get("healthcheck", {})
        test_cmd = healthcheck.get("test", [])
        test_str = " ".join(str(t) for t in test_cmd)
        assert "api/health" in test_str, (
            "Story 1.1 RED phase: grafana healthcheck test must include 'api/health'. "
            f"Found: {test_cmd!r}"
        )

    def test_p0_grafana_depends_on_prometheus_with_service_healthy(self) -> None:
        """AC5 P0: grafana must depend on prometheus with condition: service_healthy."""
        compose = self._load_compose()
        grafana = compose.get("services", {}).get("grafana", {})
        depends_on = grafana.get("depends_on", {})
        # depends_on can be a list or dict in compose
        if isinstance(depends_on, list):
            assert "prometheus" in depends_on, (
                "Story 1.1 RED phase: grafana depends_on must include 'prometheus'."
            )
        else:
            assert "prometheus" in depends_on, (
                "Story 1.1 RED phase: grafana depends_on must include 'prometheus' with "
                "condition: service_healthy. "
                f"Found depends_on keys: {list(depends_on.keys())!r}"
            )
            condition = depends_on.get("prometheus", {}).get("condition")
            assert condition == "service_healthy", (
                "Story 1.1 RED phase: grafana depends_on prometheus must use "
                f"condition: service_healthy. Found: {condition!r}"
            )

    def test_p1_grafana_port_3000_is_exposed(self) -> None:
        """AC5 P1: grafana service must expose port 3000 for browser access."""
        compose = self._load_compose()
        grafana = compose.get("services", {}).get("grafana", {})
        ports = grafana.get("ports", [])
        assert any("3000" in str(p) for p in ports), (
            "Story 1.1 RED phase: grafana service must expose port 3000. "
            f"Found ports: {ports!r}"
        )

    def test_p1_prometheus_has_healthcheck_defined(self) -> None:
        """AC5 P1: prometheus service must have a healthcheck (required for grafana depends_on)."""
        compose = self._load_compose()
        prometheus = compose.get("services", {}).get("prometheus", {})
        assert "healthcheck" in prometheus, (
            "Story 1.1 RED phase: prometheus service must define a healthcheck. "
            "Required so grafana depends_on: condition: service_healthy works."
        )
