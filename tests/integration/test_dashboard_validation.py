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


class TestHeroBannerPanels:
    """Config-validation tests for story 2-1: hero banner and P&L stat panels.

    TDD RED PHASE: these tests fail until aiops-main.json panels are populated.
    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)

    # ── Hero banner (id=1) ────────────────────────────────────────────────────

    def test_hero_banner_panel_exists(self):
        """AC1: Hero banner panel (id=1) must exist and be a stat panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found in aiops-main.json"
        assert panel["type"] == "stat", f"Expected type 'stat', got '{panel['type']}'"

    def test_hero_banner_grid_position(self):
        """AC1: Hero banner must occupy full width, rows 0-4 (h=5, w=24, y=0)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        assert panel["gridPos"]["y"] == 0, "Hero banner must start at row y=0"
        assert panel["gridPos"]["w"] == 24, "Hero banner must span full width w=24"
        assert panel["gridPos"]["h"] == 5, "Hero banner must have height h=5"

    def test_hero_banner_no_sparkline(self):
        """AC1 (UX-DR7): Hero banner must suppress sparkline for a clean signal."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        assert panel["options"]["graphMode"] == "none", (
            "Hero banner must have graphMode='none' (sparkline disabled)"
        )

    def test_hero_banner_background_color_mode(self):
        """AC1: Hero banner must use background colorMode so entire panel turns green/amber/red."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        assert panel["options"]["colorMode"] == "background", (
            "Hero banner must have colorMode='background'"
        )

    def test_hero_banner_thresholds(self):
        """AC1+AC3: Hero banner threshold steps must use approved palette only."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        thresholds = panel["fieldConfig"]["defaults"]["thresholds"]
        assert thresholds["mode"] == "absolute", "Threshold mode must be 'absolute'"
        steps = thresholds["steps"]
        colors = [s["color"] for s in steps]
        assert "#6BAD64" in colors, "semantic-green #6BAD64 must be in threshold steps"
        assert "#E8913A" in colors, "semantic-amber #E8913A must be in threshold steps"
        assert "#D94452" in colors, "semantic-red #D94452 must be in threshold steps"

    def test_hero_banner_color_field_config(self):
        """AC1: color.mode must be 'thresholds' to activate threshold-driven background color."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        color_mode = panel["fieldConfig"]["defaults"]["color"]["mode"]
        assert color_mode == "thresholds", (
            f"fieldConfig.defaults.color.mode must be 'thresholds', got '{color_mode}'"
        )

    def test_hero_banner_has_description(self):
        """AC3 (UX-DR12): Hero banner must have a non-empty description field."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        assert panel.get("description", "").strip() != "", (
            "Hero banner must have a non-empty description (UX-DR12)"
        )

    def test_hero_banner_reduce_calc_last_not_null(self):
        """AC1: Hero banner reduceOptions must use lastNotNull to show current health state."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        calcs = panel["options"]["reduceOptions"]["calcs"]
        assert "lastNotNull" in calcs, (
            "Hero banner reduceOptions.calcs must include 'lastNotNull'"
        )

    # ── P&L stat panel (id=2) ────────────────────────────────────────────────

    def test_pl_stat_panel_exists(self):
        """AC2: P&L stat panel (id=2) must exist and be a stat panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 2)
        assert panel is not None, "P&L stat panel (id=2) not found in aiops-main.json"
        assert panel["type"] == "stat", f"Expected type 'stat', got '{panel['type']}'"

    def test_pl_stat_panel_grid_position(self):
        """AC2: P&L stat must occupy full width starting at row 5 (y=5, w=24, h=3)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 2)
        assert panel is not None, "P&L stat panel (id=2) not found"
        assert panel["gridPos"]["y"] == 5, "P&L stat panel must start at row y=5"
        assert panel["gridPos"]["w"] == 24, "P&L stat panel must span full width w=24"
        assert panel["gridPos"]["h"] == 3, "P&L stat panel must have height h=3"

    def test_pl_stat_panel_sparkline_enabled(self):
        """AC2: P&L stat must show sparkline trend (graphMode=area)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 2)
        assert panel is not None, "P&L stat panel (id=2) not found"
        assert panel["options"]["graphMode"] == "area", (
            "P&L stat must have graphMode='area' (sparkline enabled)"
        )

    def test_pl_stat_query_uses_increase_range(self):
        """AC2: P&L query must use increase(aiops_findings_total[$__range]) — not rate()."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 2)
        assert panel is not None, "P&L stat panel (id=2) not found"
        expr = panel["targets"][0]["expr"]
        assert "increase(aiops_findings_total" in expr, (
            "P&L query must use increase(aiops_findings_total...)"
        )
        assert "$__range" in expr, "P&L query must use $__range (not $__rate_interval)"

    def test_pl_stat_has_description(self):
        """AC3 (UX-DR12): P&L stat must have a non-empty description field."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 2)
        assert panel is not None, "P&L stat panel (id=2) not found"
        assert panel.get("description", "").strip() != "", (
            "P&L stat panel must have a non-empty description (UX-DR12)"
        )

    def test_pl_stat_reduce_calc_sum(self):
        """AC2: P&L stat reduceOptions must use sum to accumulate total anomalies."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 2)
        assert panel is not None, "P&L stat panel (id=2) not found"
        calcs = panel["options"]["reduceOptions"]["calcs"]
        assert "sum" in calcs, "P&L stat reduceOptions.calcs must include 'sum'"

    def test_pl_stat_celebrated_zero_color(self):
        """AC3 (UX-DR5): P&L stat must display zero in semantic-green (celebrated zero)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 2)
        assert panel is not None, "P&L stat panel (id=2) not found"
        color_cfg = panel["fieldConfig"]["defaults"]["color"]
        assert color_cfg.get("fixedColor") == "#6BAD64", (
            "P&L stat fixedColor must be semantic-green #6BAD64 (UX-DR5 celebrated zeros)"
        )
        assert color_cfg.get("mode") == "fixed", (
            "P&L stat color.mode must be 'fixed' to apply fixedColor"
        )

    # ── Cross-panel palette enforcement ───────────────────────────────────────

    def test_no_grafana_default_palette_colors_in_new_panels(self):
        """AC3 (UX-DR1): No forbidden Grafana default palette colors may appear in panels 1 or 2."""
        forbidden = {
            "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
            "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
        }
        dashboard = self._load_main_dashboard()
        # Normalize to uppercase so case-variant hex values (e.g. from Grafana export) are caught.
        panel_json = json.dumps(
            [p for p in dashboard.get("panels", []) if p.get("id") in {1, 2}]
        ).upper()
        for color in forbidden:
            assert color not in panel_json, (
                f"Forbidden Grafana default color {color} found in panel config (UX-DR1)"
            )

    def test_both_panels_have_no_data_message(self):
        """AC4 (NFR5): Both panels must set noValue in fieldConfig to prevent blank error states."""
        for panel_id in (1, 2):
            dashboard = self._load_main_dashboard()
            panel = self._get_panel_by_id(dashboard, panel_id)
            assert panel is not None, f"Panel id={panel_id} not found"
            no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue", "")
            assert no_value.strip() != "", (
                f"Panel id={panel_id} must have a non-empty fieldConfig.defaults.noValue (NFR5)"
            )

    def test_hero_banner_has_value_mappings_for_wcag(self):
        """AC5 (UX-DR14): Hero banner must map 0->HEALTHY, 1->DEGRADED, 2->UNAVAILABLE."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 1)
        assert panel is not None, "Hero banner panel (id=1) not found"
        mappings = panel.get("fieldConfig", {}).get("defaults", {}).get("mappings", [])
        assert len(mappings) > 0, (
            "Hero banner must have value mappings for WCAG AA text labels (UX-DR14)"
        )
        # Flatten all mapping option texts for inspection.
        all_texts = []
        for m in mappings:
            for v in m.get("options", {}).values():
                if isinstance(v, dict):
                    all_texts.append(v.get("text", ""))
        assert "HEALTHY" in all_texts, "Mapping for value 0 must display 'HEALTHY' (UX-DR14)"
        assert "DEGRADED" in all_texts, "Mapping for value 1 must display 'DEGRADED' (UX-DR14)"
        assert "UNAVAILABLE" in all_texts, (
            "Mapping for value 2 must display 'UNAVAILABLE' (UX-DR14)"
        )

    def test_dashboard_version_is_2(self):
        """Dashboard version must be incremented to 2 after story 2-1 panel additions (NFR12)."""
        dashboard = self._load_main_dashboard()
        assert dashboard.get("version") == 2, (
            f"Dashboard version must be 2 after story 2-1, got {dashboard.get('version')}"
        )
