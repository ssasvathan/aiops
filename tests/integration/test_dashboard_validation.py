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

    def test_dashboard_version_is_at_least_2(self):
        """Dashboard version must be >= 2 after story 2-1 panel additions (NFR12)."""
        dashboard = self._load_main_dashboard()
        assert dashboard.get("version", 0) >= 2, (
            f"Dashboard version must be >= 2 after story 2-1, got {dashboard.get('version')}"
        )


class TestTopicHealthHeatmap:
    """Config-validation tests for story 2-2: topic health heatmap panel.

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)

    # ── Panel existence and type ──────────────────────────────────────────────

    def test_heatmap_panel_exists(self):
        """AC1: Topic health heatmap panel (id=3) must exist and be a stat panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found in aiops-main.json"
        assert panel["type"] == "stat", f"Expected type 'stat', got '{panel['type']}'"

    # ── Grid position ─────────────────────────────────────────────────────────

    def test_heatmap_grid_position(self):
        """AC1: Heatmap must occupy rows 8-13 (y=8, h=6, w=24) per UX-DR3 layout."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        assert panel["gridPos"]["y"] == 8, "Heatmap must start at row y=8"
        assert panel["gridPos"]["w"] == 24, "Heatmap must span full width w=24"
        assert panel["gridPos"]["h"] == 6, "Heatmap must have height h=6"

    # ── Display options ───────────────────────────────────────────────────────

    def test_heatmap_background_color_mode(self):
        """AC1: Tiles must use background colorMode for per-tile semantic color fills."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        assert panel["options"]["colorMode"] == "background", (
            "Heatmap must have colorMode='background' for per-tile color fills"
        )

    def test_heatmap_no_sparkline(self):
        """AC1: No sparkline on heatmap tiles — clean tile display only (no time-series line)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        assert panel["options"]["graphMode"] == "none", (
            "Heatmap must have graphMode='none' (sparkline disabled for clean tile view)"
        )

    def test_heatmap_values_mode_for_per_topic_tiles(self):
        """AC1: values=true + limit=10 required to render one tile per topic label value."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        reduce_opts = panel["options"]["reduceOptions"]
        assert reduce_opts.get("values") is True, (
            "reduceOptions.values must be true for per-topic tile rendering"
        )
        assert reduce_opts.get("limit") == 10, (
            "reduceOptions.limit must be 10 to accommodate up to 10 topics"
        )

    def test_heatmap_tile_font_size_meets_readability_minimum(self):
        """AC4 (UX-DR2): Tile label font size must be 14px+ for projector readability."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        text_opts = panel.get("options", {}).get("text", {})
        title_size = text_opts.get("titleSize", 0)
        value_size = text_opts.get("valueSize", 0)
        assert title_size >= 14, (
            f"Tile title font size must be >= 14px (UX-DR2), got {title_size}"
        )
        assert value_size >= 14, (
            f"Tile value font size must be >= 14px (UX-DR2), got {value_size}"
        )

    # ── Color configuration ───────────────────────────────────────────────────

    def test_heatmap_thresholds_use_approved_palette(self):
        """AC1 (UX-DR9): Tile thresholds must use semantic palette tokens only."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        steps = panel["fieldConfig"]["defaults"]["thresholds"]["steps"]
        colors = [s["color"] for s in steps]
        assert "#6BAD64" in colors, "semantic-green #6BAD64 must be in thresholds (HEALTHY)"
        assert "#E8913A" in colors, "semantic-amber #E8913A must be in thresholds (WARNING)"
        assert "#D94452" in colors, "semantic-red #D94452 must be in thresholds (CRITICAL)"

    def test_heatmap_color_field_config_mode_is_thresholds(self):
        """AC1: fieldConfig.defaults.color.mode must be 'thresholds' to drive tile background."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        color_mode = panel["fieldConfig"]["defaults"]["color"]["mode"]
        assert color_mode == "thresholds", (
            f"fieldConfig.defaults.color.mode must be 'thresholds', got '{color_mode}'"
        )

    def test_no_grafana_default_palette_colors_in_heatmap(self):
        """AC4 (UX-DR1): No forbidden Grafana default palette colors in panel id=3."""
        forbidden = {
            "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
            "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
        }
        dashboard = self._load_main_dashboard()
        # Normalize to uppercase so case-variant hex values are caught.
        panel_json = json.dumps(
            [p for p in dashboard.get("panels", []) if p.get("id") == 3]
        ).upper()
        for color in forbidden:
            assert color not in panel_json, (
                f"Forbidden Grafana default color {color} found in heatmap panel (UX-DR1)"
            )

    # ── Description ───────────────────────────────────────────────────────────

    def test_heatmap_has_description(self):
        """AC4 (UX-DR12): Heatmap must have a non-empty description field."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        assert panel.get("description", "").strip() != "", (
            "Heatmap must have a non-empty description (UX-DR12)"
        )

    # ── Data links ────────────────────────────────────────────────────────────

    def test_heatmap_has_data_link_to_drilldown(self):
        """AC3: Each tile must link to drill-down dashboard with topic pre-selected."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        links = panel.get("fieldConfig", {}).get("defaults", {}).get("links", [])
        assert len(links) >= 1, "Heatmap must have at least one data link in fieldConfig.defaults"
        link_url = links[0].get("url", "")
        assert "aiops-drilldown" in link_url, (
            "Data link must target stable drill-down UID 'aiops-drilldown'"
        )
        assert "var-topic" in link_url, (
            "Data link must pass topic variable (var-topic) for pre-selection"
        )

    def test_heatmap_data_link_preserves_time_range(self):
        """AC3: Data link must preserve the Grafana time range via ${__url_time_range}."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        links = panel.get("fieldConfig", {}).get("defaults", {}).get("links", [])
        assert len(links) >= 1, "Heatmap must have at least one data link"
        link_url = links[0].get("url", "")
        assert "__url_time_range" in link_url, (
            "Data link must include ${__url_time_range} to preserve time range across navigation"
        )

    # ── Value mappings (WCAG AA) ──────────────────────────────────────────────

    def test_heatmap_has_value_mappings(self):
        """AC1 (UX-DR14): Tiles must show HEALTHY/WARNING/CRITICAL text labels alongside color."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        mappings = panel.get("fieldConfig", {}).get("defaults", {}).get("mappings", [])
        assert len(mappings) > 0, (
            "Heatmap tiles must have value mappings for WCAG AA text labels (UX-DR14)"
        )
        all_texts = []
        for m in mappings:
            for v in m.get("options", {}).values():
                if isinstance(v, dict):
                    all_texts.append(v.get("text", ""))
        assert "HEALTHY" in all_texts, "Mapping for value 0 must display 'HEALTHY' (UX-DR14)"
        assert "WARNING" in all_texts, "Mapping for value 1 must display 'WARNING' (UX-DR14)"
        assert "CRITICAL" in all_texts, "Mapping for value 2 must display 'CRITICAL' (UX-DR14)"

    # ── noValue guard (NFR5) ──────────────────────────────────────────────────

    def test_heatmap_has_no_value_message(self):
        """AC4 (NFR5): Heatmap must set noValue in fieldConfig to prevent blank tile states."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 3)
        assert panel is not None, "Topic health heatmap panel (id=3) not found"
        no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue", "")
        assert no_value.strip() != "", (
            "Heatmap panel must have a non-empty fieldConfig.defaults.noValue (NFR5)"
        )

    # ── Dashboard version ─────────────────────────────────────────────────────

    def test_dashboard_version_is_3(self):
        """Dashboard version must be >= 3 after story 2-2 panel addition (NFR12)."""
        dashboard = self._load_main_dashboard()
        assert dashboard.get("version", 0) >= 3, (
            f"Dashboard version must be >= 3 after story 2-2, got {dashboard.get('version')}"
        )


class TestBaselineDeviationOverlay:
    """Config-validation tests for story 2-3: fold separator and baseline deviation overlay.

    TDD RED PHASE: these tests fail until aiops-main.json panels id=4 and id=5 are populated.
    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)

    # ── Fold separator (id=4) ─────────────────────────────────────────────────

    def test_fold_separator_panel_exists(self):
        """AC1: Fold separator panel (id=4) must exist at y=14 as the above/below-fold boundary."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 4)
        assert panel is not None, "Fold separator panel (id=4) not found in aiops-main.json"
        assert panel["gridPos"]["y"] == 14, "Fold separator must be at row y=14 (FR29)"
        assert panel["gridPos"]["h"] == 1, "Fold separator must have height h=1 (thin spacer row)"
        assert panel["gridPos"]["w"] == 24, "Fold separator must span full width w=24"
        assert panel["gridPos"]["x"] == 0, "Fold separator must start at column x=0 (full-width)"

    def test_fold_separator_panel_type(self):
        """AC1 (FR29): Fold separator must be a text or row panel type (visual spacer only)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 4)
        assert panel is not None, "Fold separator panel (id=4) not found"
        assert panel.get("type") in {"text", "row"}, (
            f"Fold separator must be type 'text' or 'row', got '{panel.get('type')}'"
        )

    # ── Baseline overlay panel (id=5) existence and type ─────────────────────

    def test_baseline_overlay_panel_exists(self):
        """AC2: Baseline deviation overlay panel (id=5) must exist as a timeseries panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        assert panel["type"] == "timeseries", (
            f"Expected type 'timeseries', got '{panel.get('type')}'"
        )

    def test_baseline_overlay_grid_position(self):
        """AC2: Overlay must occupy rows 15-22 (y=15, h=8, w=24, x=0) per UX-DR3 layout."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        assert panel["gridPos"]["y"] == 15, "Overlay must start at row y=15"
        assert panel["gridPos"]["h"] == 8, "Overlay must have height h=8"
        assert panel["gridPos"]["w"] == 24, "Overlay must span full width w=24"
        assert panel["gridPos"]["x"] == 0, "Overlay must start at column x=0 (full-width)"

    def test_baseline_overlay_is_transparent(self):
        """AC4 (UX-DR4): Overlay panel must use transparent background (no borders/cards)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        assert panel.get("transparent") is True, (
            "Baseline overlay must have transparent=true per UX-DR4 (no borders/card backgrounds)"
        )

    # ── Multi-query / targets ─────────────────────────────────────────────────

    def test_baseline_overlay_has_multi_query(self):
        """AC2: Panel must have at least 2 targets (actual line + bound lines for band-fill)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        targets = panel.get("targets", [])
        assert len(targets) >= 2, (
            f"Baseline overlay must have >= 2 query targets, got {len(targets)}"
        )

    def test_baseline_overlay_primary_query_uses_rate(self):
        """AC4: Primary PromQL query must use rate() with $__rate_interval (time-series panel)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        target_a = next((t for t in panel.get("targets", []) if t.get("refId") == "A"), None)
        assert target_a is not None, "Target refId='A' (primary series) not found"
        expr = target_a.get("expr", "")
        assert "rate(" in expr, "Primary query must use rate() for time-series panel (AC4)"
        assert "$__rate_interval" in expr, (
            "Primary query must use $__rate_interval range vector (not $__range)"
        )

    # ── Description ──────────────────────────────────────────────────────────

    def test_baseline_overlay_has_description(self):
        """AC4 (UX-DR12): Overlay must have a non-empty description field."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        assert panel.get("description", "").strip() != "", (
            "Baseline overlay must have a non-empty description (UX-DR12)"
        )

    # ── Color palette ─────────────────────────────────────────────────────────

    def test_baseline_overlay_uses_accent_blue(self):
        """AC2 (UX-DR8): accent-blue #4F87DB must be used for the actual-value line/band."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        panel_json = json.dumps(panel).upper()
        assert "#4F87DB" in panel_json, (
            "accent-blue #4F87DB must appear in overlay panel JSON (UX-DR8)"
        )

    def test_detection_annotations_use_semantic_amber(self):
        """AC3 (UX-DR8): Detection event markers must use semantic-amber #E8913A."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        panel_json = json.dumps(panel).upper() if panel else ""
        annotations_json = json.dumps(dashboard.get("annotations", {})).upper()
        assert "#E8913A" in panel_json or "#E8913A" in annotations_json, (
            "semantic-amber #E8913A must appear in panel id=5 or dashboard annotations (UX-DR8)"
        )

    def test_no_grafana_default_palette_colors_in_overlay(self):
        """AC4 (UX-DR1): No forbidden Grafana default palette colors in panel id=5."""
        forbidden = {
            "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
            "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
        }
        dashboard = self._load_main_dashboard()
        panel_json = json.dumps(
            [p for p in dashboard.get("panels", []) if p.get("id") == 5]
        ).upper()
        for color in forbidden:
            assert color not in panel_json, (
                f"Forbidden Grafana default color {color} found in overlay panel (UX-DR1)"
            )

    # ── noValue (NFR5 / UX-DR5) ──────────────────────────────────────────────

    def test_baseline_overlay_has_no_value_message(self):
        """AC5 (NFR5 / UX-DR5): Overlay must set noValue to prevent blank error states."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 5)
        assert panel is not None, "Baseline deviation overlay panel (id=5) not found"
        no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue", "")
        assert no_value.strip() != "", (
            "Baseline overlay must have a non-empty fieldConfig.defaults.noValue (NFR5)"
        )

    # ── Annotation query ─────────────────────────────────────────────────────

    def test_dashboard_annotations_list_is_non_empty(self):
        """AC3 (FR9): Dashboard annotations list must be non-empty for detection event markers."""
        dashboard = self._load_main_dashboard()
        annotations_list = dashboard.get("annotations", {}).get("list", [])
        assert len(annotations_list) >= 1, (
            "Dashboard annotations list must contain at least one entry for detection markers (FR9)"
        )

    # ── Dashboard version ─────────────────────────────────────────────────────

    def test_dashboard_version_is_4(self):
        """Dashboard version must be >= 4 after story 2-3 panel additions (NFR12)."""
        dashboard = self._load_main_dashboard()
        assert dashboard.get("version", 0) >= 4, (
            f"Dashboard version must be >= 4 after story 2-3, got {dashboard.get('version')}"
        )


class TestGatingIntelligenceFunnel:
    """Config-validation tests for story 3-1: section separator (id=6) and gating intelligence
    funnel bargauge panel (id=7).

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)

    # ── Section separator (id=6) ──────────────────────────────────────────────

    def test_section_separator_panel_exists(self):
        """AC1 (Task 3.2): Section separator panel (id=6) must exist at y=23 as a text/row
        panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 6)
        assert panel is not None, "Section separator panel (id=6) not found in aiops-main.json"
        assert panel.get("type") in {"text", "row"}, (
            f"Section separator must be type 'text' or 'row', got '{panel.get('type')}'"
        )

    def test_section_separator_grid_position(self):
        """AC1 (Task 3.2): Section separator must occupy row 23 (y=23, h=1, w=24, x=0)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 6)
        assert panel is not None, "Section separator panel (id=6) not found"
        assert panel["gridPos"]["y"] == 23, (
            "Section separator must start at row y=23 (credibility zone boundary)"
        )
        assert panel["gridPos"]["h"] == 1, "Section separator must have height h=1 (thin spacer)"
        assert panel["gridPos"]["w"] == 24, "Section separator must span full width w=24"
        assert panel["gridPos"]["x"] == 0, (
            "Section separator must start at column x=0 (full-width)"
        )

    # ── Gating intelligence funnel (id=7): existence and type ────────────────

    def test_funnel_panel_exists(self):
        """AC2 (Task 3.3): Gating intelligence funnel panel (id=7) must exist and be a
        bargauge."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, (
            "Gating intelligence funnel panel (id=7) not found in aiops-main.json"
        )
        assert panel["type"] == "bargauge", (
            f"Funnel panel must be type 'bargauge', got '{panel.get('type')}'"
        )

    # ── Grid position ─────────────────────────────────────────────────────────

    def test_funnel_panel_grid_position(self):
        """AC2 (Task 3.4): Funnel panel must occupy rows 24-29 (y=24, h=6, w=24, x=0)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        assert panel["gridPos"]["y"] == 24, "Funnel panel must start at row y=24"
        assert panel["gridPos"]["h"] == 6, "Funnel panel must have height h=6"
        assert panel["gridPos"]["w"] == 24, "Funnel panel must span full width w=24"
        assert panel["gridPos"]["x"] == 0, "Funnel panel must start at column x=0 (full-width)"

    # ── Transparent background ────────────────────────────────────────────────

    def test_funnel_panel_is_transparent(self):
        """AC5 / UX-DR4 (Task 3.5): Funnel panel must use transparent=true (bargauge panels
        require explicit transparent flag — H1 finding from story 2-3 review)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        assert panel.get("transparent") is True, (
            "Funnel panel must have transparent=true (UX-DR4 — explicit transparent required for "
            "bargauge panels)"
        )

    # ── Orientation ───────────────────────────────────────────────────────────

    def test_funnel_panel_orientation_is_horizontal(self):
        """AC2 / UX-DR10 (Task 3.6): Funnel bargauge must use horizontal orientation so
        funnel stages read top-to-bottom as a natural reading flow."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        orientation = panel.get("options", {}).get("orientation")
        assert orientation == "horizontal", (
            f"Funnel panel options.orientation must be 'horizontal' (UX-DR10), got '{orientation}'"
        )

    def test_funnel_panel_display_mode_is_gradient(self):
        """AC2 / UX-DR10: Funnel bargauge must use displayMode='gradient' for the colour
        progression from detected (accent-blue) through suppressed (grey) to dispatched (green).
        'lcd' or 'basic' would lose the funnel visual intent."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        display_mode = panel.get("options", {}).get("displayMode")
        assert display_mode == "gradient", (
            f"Funnel panel options.displayMode must be 'gradient' (UX-DR10), got '{display_mode}'"
        )

    # ── PromQL query: increase + $__range ────────────────────────────────────

    def test_funnel_target_uses_increase_and_range(self):
        """AC2 (Task 3.7): Funnel target refId='A' PromQL must use increase( and $__range —
        bargauge/stat panel convention (NOT rate() or $__rate_interval)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Funnel panel must have a target with refId='A'"
        expr = target_a.get("expr", "")
        assert "increase(" in expr, (
            "Funnel panel refId='A' PromQL must use increase( (stat/bargauge panel convention)"
        )
        assert "$__range" in expr, (
            "Funnel panel refId='A' PromQL must use $__range (NOT $__rate_interval)"
        )

    # ── PromQL query: correct metric ──────────────────────────────────────────

    def test_funnel_target_uses_gating_evaluations_metric(self):
        """AC2 (Task 3.8): Funnel target refId='A' PromQL must query
        aiops_gating_evaluations_total — the counter emitted by the gating pipeline."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Funnel panel must have a target with refId='A'"
        expr = target_a.get("expr", "")
        assert "aiops_gating_evaluations_total" in expr, (
            "Funnel panel PromQL must query aiops_gating_evaluations_total metric"
        )

    # ── PromQL aggregation style ──────────────────────────────────────────────

    def test_funnel_target_uses_sum_by_aggregation_style(self):
        """AC2 (Task 3.9): Funnel PromQL must use 'sum by(' aggregation style — NOT
        'sum(...)by(' which is a different (non-preferred) style."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Funnel panel must have a target with refId='A'"
        expr = target_a.get("expr", "")
        assert "sum by(" in expr, (
            "Funnel panel PromQL must use 'sum by(' aggregation style (not 'sum(...) by(')"
        )

    # ── PromQL legendFormat: gate_id visible ──────────────────────────────────

    def test_funnel_target_legend_format_shows_gate_id(self):
        """AC3 (FR13): Funnel target legendFormat must include {{gate_id}} so each bar label
        shows the named gate rule (AG0-AG6) visible in the bargauge panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Funnel panel must have a target with refId='A'"
        legend_format = target_a.get("legendFormat", "")
        assert "{{gate_id}}" in legend_format, (
            "Funnel panel legendFormat must include '{{gate_id}}' so gate rule name is visible "
            "in bar labels (AC3 / FR13)"
        )

    # ── Color palette: accent-blue (detected) ────────────────────────────────

    def test_funnel_panel_has_accent_blue(self):
        """AC2 / UX-DR10 (Task 3.10): accent-blue #4F87DB must appear in funnel panel JSON
        as the gradient start color for detected findings."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        panel_json = json.dumps(panel).upper()
        assert "#4F87DB" in panel_json, (
            "accent-blue #4F87DB must appear in funnel panel JSON (gradient start — detected)"
        )

    # ── Color palette: semantic-green (dispatched) ────────────────────────────

    def test_funnel_panel_has_semantic_green(self):
        """AC2 / UX-DR10 (Task 3.11): semantic-green #6BAD64 must appear in funnel panel JSON
        as the dispatched gradient end color."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        panel_json = json.dumps(panel).upper()
        assert "#6BAD64" in panel_json, (
            "semantic-green #6BAD64 must appear in funnel panel JSON (dispatched gradient end)"
        )

    # ── Color palette: semantic-grey (suppressed) ────────────────────────────

    def test_funnel_panel_has_semantic_grey(self):
        """AC2 / UX-DR10 (Task 3.12): semantic-grey #7A7A7A must appear in funnel panel JSON
        as the suppressed mid-gradient color."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        panel_json = json.dumps(panel).upper()
        assert "#7A7A7A" in panel_json, (
            "semantic-grey #7A7A7A must appear in funnel panel JSON (suppressed mid-gradient)"
        )

    # ── Forbidden Grafana default palette colors ──────────────────────────────

    def test_no_grafana_default_palette_colors_in_funnel_panel(self):
        """AC5 / UX-DR1 (Task 3.13): No forbidden Grafana default palette colors may appear
        in funnel panel id=7 JSON (case-insensitive check)."""
        forbidden = {
            "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
            "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
        }
        dashboard = self._load_main_dashboard()
        panel_json = json.dumps(
            [p for p in dashboard.get("panels", []) if p.get("id") == 7]
        ).upper()
        for color in forbidden:
            assert color not in panel_json, (
                f"Forbidden Grafana default color {color} found in funnel panel (UX-DR1)"
            )

    # ── Description ───────────────────────────────────────────────────────────

    def test_funnel_panel_has_description(self):
        """AC5 / UX-DR12 (Task 3.14): Funnel panel must have a non-empty one-sentence
        description field."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        assert panel.get("description", "").strip() != "", (
            "Funnel panel must have a non-empty description (UX-DR12)"
        )

    # ── noValue (NFR5 / UX-DR5) ──────────────────────────────────────────────

    def test_funnel_panel_has_no_value_field(self):
        """AC4 / NFR5 / UX-DR5 (Task 3.15): Funnel panel must set noValue in fieldConfig to
        display celebrated zeros in semantic-green when no data exists for a bar segment."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue", None)
        assert no_value is not None, (
            "Funnel panel must have fieldConfig.defaults.noValue set (NFR5 / UX-DR5 celebrated "
            "zeros)"
        )

    # ── Label font size ───────────────────────────────────────────────────────

    def test_funnel_panel_text_title_size_meets_readability_minimum(self):
        """AC2 / UX-DR2 (Task 3.16): Funnel bargauge options.text.titleSize must be >= 14
        for projector readability."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 7)
        assert panel is not None, "Gating intelligence funnel panel (id=7) not found"
        title_size = panel.get("options", {}).get("text", {}).get("titleSize", 0)
        assert title_size >= 14, (
            f"Funnel panel options.text.titleSize must be >= 14px (UX-DR2), got {title_size}"
        )

    # ── Dashboard version ─────────────────────────────────────────────────────

    def test_dashboard_version_is_at_least_5(self):
        """Dashboard version must be >= 5 after story 3-1 panel additions (Task 3.17 / NFR12).
        Version must be bumped from 4 to 5 to reflect the new panels."""
        dashboard = self._load_main_dashboard()
        assert dashboard.get("version", 0) >= 5, (
            f"Dashboard version must be >= 5 after story 3-1, got {dashboard.get('version')}"
        )


class TestActionDistributionAnomalyBreakdown:
    """Config-validation tests for story 3-2: action distribution timeseries (id=8)
    and anomaly family breakdown barchart (id=9).

    No live docker-compose stack required — all assertions are pure JSON parsing.
    """

    def _load_main_dashboard(self):
        path = REPO_ROOT / "grafana/dashboards/aiops-main.json"
        return json.loads(path.read_text())

    def _get_panel_by_id(self, dashboard, panel_id):
        panels = dashboard.get("panels", [])
        return next((p for p in panels if p.get("id") == panel_id), None)

    # ── Action distribution panel (id=8): existence and type ─────────────────

    def test_action_distribution_panel_exists(self):
        """AC1 (Task 4.2): Action distribution panel (id=8) must exist and be a timeseries
        panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, (
            "Action distribution panel (id=8) not found in aiops-main.json"
        )
        assert panel["type"] == "timeseries", (
            f"Action distribution panel must be type 'timeseries', got '{panel.get('type')}'"
        )

    # ── Grid position ─────────────────────────────────────────────────────────

    def test_action_distribution_panel_grid_position(self):
        """AC1 (Task 4.3): Action distribution panel must occupy rows 30-34, left half
        (y=30, h=5, w=12, x=0) per UX-DR3 layout."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        assert panel["gridPos"]["y"] == 30, "Action distribution panel must start at row y=30"
        assert panel["gridPos"]["h"] == 5, "Action distribution panel must have height h=5"
        assert panel["gridPos"]["w"] == 12, "Action distribution panel must have width w=12"
        assert panel["gridPos"]["x"] == 0, (
            "Action distribution panel must start at column x=0 (left half)"
        )

    # ── Transparent background ────────────────────────────────────────────────

    def test_action_distribution_panel_is_transparent(self):
        """AC4 / UX-DR4 (Task 4.4): Action distribution timeseries panel must have
        transparent=true — timeseries panels require explicit transparent flag."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        assert panel.get("transparent") is True, (
            "Action distribution panel must have transparent=true (UX-DR4 — explicit "
            "transparent required for timeseries panels)"
        )

    # ── PromQL query: rate + $__rate_interval ─────────────────────────────────

    def test_action_distribution_target_uses_rate_and_rate_interval(self):
        """AC1 (Task 4.5): Action distribution target refId='A' PromQL must use rate( and
        $__rate_interval — timeseries panel convention (NOT increase() or $__range)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Action distribution panel must have a target with refId='A'"
        expr = target_a.get("expr", "")
        assert "rate(" in expr, (
            "Action distribution refId='A' PromQL must use rate( (timeseries panel convention)"
        )
        assert "$__rate_interval" in expr, (
            "Action distribution refId='A' PromQL must use $__rate_interval (NOT $__range)"
        )

    # ── PromQL query: correct metric ──────────────────────────────────────────

    def test_action_distribution_target_uses_aiops_findings_total(self):
        """AC1 (Task 4.6): Action distribution target refId='A' PromQL must query
        aiops_findings_total — the counter emitted by the findings pipeline."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Action distribution panel must have a target with refId='A'"
        expr = target_a.get("expr", "")
        assert "aiops_findings_total" in expr, (
            "Action distribution panel PromQL must query aiops_findings_total metric"
        )

    # ── PromQL aggregation style ──────────────────────────────────────────────

    def test_action_distribution_target_uses_sum_by_aggregation_style(self):
        """AC1 (Task 4.7): Action distribution PromQL must use 'sum by(' aggregation style —
        NOT 'sum(...)by(' which is a different non-preferred style."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Action distribution panel must have a target with refId='A'"
        expr = target_a.get("expr", "")
        assert "sum by(" in expr, (
            "Action distribution PromQL must use 'sum by(' aggregation style "
            "(not 'sum(...) by(')"
        )

    # ── PromQL label: final_action ────────────────────────────────────────────

    def test_action_distribution_target_uses_final_action_label(self):
        """AC1 (Task 4.8): Action distribution PromQL must use 'sum by(final_action)' label
        so each action type (OBSERVE, NOTIFY, TICKET, PAGE) appears as a distinct series."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Action distribution panel must have a target with refId='A'"
        expr = target_a.get("expr", "")
        assert "final_action" in expr, (
            "Action distribution PromQL must aggregate by 'final_action' label"
        )

    # ── legendFormat: final_action visible ───────────────────────────────────

    def test_action_distribution_target_legend_format_shows_final_action(self):
        """AC1 (Task 4.9): Action distribution target legendFormat must include
        {{final_action}} so each series label renders OBSERVE, NOTIFY, TICKET, PAGE."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, "Action distribution panel must have a target with refId='A'"
        legend_format = target_a.get("legendFormat", "")
        assert "final_action" in legend_format, (
            "Action distribution legendFormat must include 'final_action' so series labels "
            "render (AC1)"
        )

    # ── Description ───────────────────────────────────────────────────────────

    def test_action_distribution_panel_has_description(self):
        """AC4 / UX-DR12 (Task 4.10): Action distribution panel must have a non-empty
        one-sentence description field."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        assert panel.get("description", "").strip() != "", (
            "Action distribution panel must have a non-empty description (UX-DR12)"
        )

    # ── noValue guard (NFR9 / UX-DR5) ────────────────────────────────────────

    def test_action_distribution_panel_has_no_value_field(self):
        """AC2 / NFR9 / UX-DR5 (Task 4.11): Action distribution panel must set noValue in
        fieldConfig so the PAGE series renders as zero (celebrated zero) — not missing."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue", None)
        assert no_value is not None, (
            "Action distribution panel must have fieldConfig.defaults.noValue set "
            "(NFR9 / UX-DR5 — PAGE celebrated zero)"
        )

    # ── Forbidden Grafana default palette colors ──────────────────────────────

    def test_no_grafana_default_palette_colors_in_action_distribution_panel(self):
        """AC4 / UX-DR1 (Task 4.12): No forbidden Grafana default palette colors may appear
        in action distribution panel id=8 JSON (case-insensitive check)."""
        forbidden = {
            "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
            "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
        }
        dashboard = self._load_main_dashboard()
        panel_json = json.dumps(
            [p for p in dashboard.get("panels", []) if p.get("id") == 8]
        ).upper()
        for color in forbidden:
            assert color not in panel_json, (
                f"Forbidden Grafana default color {color} found in action distribution "
                f"panel id=8 (UX-DR1)"
            )

    # ── Stacking mode (AC1 — stacked display) ────────────────────────────────

    def test_action_distribution_panel_uses_stacking_normal(self):
        """AC1 (Task 1.6): Action distribution timeseries panel must have
        fieldConfig.defaults.custom.stacking.mode='normal' for stacked series display."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 8)
        assert panel is not None, "Action distribution panel (id=8) not found"
        stacking = (
            panel.get("fieldConfig", {})
            .get("defaults", {})
            .get("custom", {})
            .get("stacking", {})
        )
        assert stacking.get("mode") == "normal", (
            "Action distribution panel must have stacking.mode='normal' for stacked "
            "time-series display (AC1 / FR12)"
        )

    # ── Anomaly family breakdown panel (id=9): existence and type ────────────

    def test_anomaly_family_breakdown_panel_exists(self):
        """AC3 (Task 4.13): Anomaly family breakdown panel (id=9) must exist and be a
        barchart panel."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, (
            "Anomaly family breakdown panel (id=9) not found in aiops-main.json"
        )
        assert panel["type"] == "barchart", (
            f"Anomaly family breakdown panel must be type 'barchart', got '{panel.get('type')}'"
        )

    # ── Grid position ─────────────────────────────────────────────────────────

    def test_anomaly_family_breakdown_panel_grid_position(self):
        """AC3 (Task 4.14): Anomaly family breakdown panel must occupy rows 30-34, right half
        (y=30, h=5, w=12, x=12) per UX-DR3 layout."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        assert panel["gridPos"]["y"] == 30, (
            "Anomaly family breakdown panel must start at row y=30"
        )
        assert panel["gridPos"]["h"] == 5, (
            "Anomaly family breakdown panel must have height h=5"
        )
        assert panel["gridPos"]["w"] == 12, (
            "Anomaly family breakdown panel must have width w=12"
        )
        assert panel["gridPos"]["x"] == 12, (
            "Anomaly family breakdown panel must start at column x=12 (right half)"
        )

    # ── Transparent background ────────────────────────────────────────────────

    def test_anomaly_family_breakdown_panel_is_transparent(self):
        """AC4 / UX-DR4 (Task 4.15): Anomaly family breakdown barchart panel must have
        transparent=true — barchart panels require explicit transparent flag."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        assert panel.get("transparent") is True, (
            "Anomaly family breakdown panel must have transparent=true (UX-DR4 — explicit "
            "transparent required for barchart panels)"
        )

    # ── Horizontal orientation (AC3 — horizontal bars) ───────────────────────

    def test_anomaly_family_breakdown_panel_uses_horizontal_orientation(self):
        """AC3 / UX-DR3 (Task 2.4): Anomaly family breakdown barchart must use
        options.orientation='horizontal' for horizontal bars per FR10 layout requirement."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        orientation = panel.get("options", {}).get("orientation")
        assert orientation == "horizontal", (
            f"Anomaly family breakdown panel must have options.orientation='horizontal' "
            f"(AC3 / UX-DR3), got '{orientation}'"
        )

    # ── Sort by value (AC3 — sorted by value) ────────────────────────────────

    def test_anomaly_family_breakdown_panel_is_sorted_desc(self):
        """AC3 (Task 2.4): Anomaly family breakdown barchart bars must be sorted by value
        (desc) — AC3 explicitly requires 'sorted by value' horizontal bars."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        sort = panel.get("options", {}).get("sort")
        assert sort == "desc", (
            f"Anomaly family breakdown panel must have options.sort='desc' for value-sorted "
            f"bars (AC3), got '{sort}'"
        )

    # ── PromQL query: increase + $__range ─────────────────────────────────────

    def test_anomaly_family_breakdown_target_uses_increase_and_range(self):
        """AC3 (Task 4.16): Anomaly family breakdown target refId='A' PromQL must use
        increase( and $__range — stat/bargauge/barchart panel convention (NOT rate() or
        $__rate_interval)."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, (
            "Anomaly family breakdown panel must have a target with refId='A'"
        )
        expr = target_a.get("expr", "")
        assert "increase(" in expr, (
            "Anomaly family breakdown refId='A' PromQL must use increase( "
            "(stat/barchart panel convention)"
        )
        assert "$__range" in expr, (
            "Anomaly family breakdown refId='A' PromQL must use $__range (NOT $__rate_interval)"
        )

    # ── PromQL query: correct metric ──────────────────────────────────────────

    def test_anomaly_family_breakdown_target_uses_aiops_findings_total(self):
        """AC3 (Task 4.17): Anomaly family breakdown target refId='A' PromQL must query
        aiops_findings_total — the counter emitted by the findings pipeline."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, (
            "Anomaly family breakdown panel must have a target with refId='A'"
        )
        expr = target_a.get("expr", "")
        assert "aiops_findings_total" in expr, (
            "Anomaly family breakdown panel PromQL must query aiops_findings_total metric"
        )

    # ── PromQL label: anomaly_family ──────────────────────────────────────────

    def test_anomaly_family_breakdown_target_uses_anomaly_family_label(self):
        """AC3 (Task 4.18): Anomaly family breakdown PromQL must use
        'sum by(anomaly_family)' label so each anomaly family appears as a distinct bar."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, (
            "Anomaly family breakdown panel must have a target with refId='A'"
        )
        expr = target_a.get("expr", "")
        assert "anomaly_family" in expr, (
            "Anomaly family breakdown PromQL must aggregate by 'anomaly_family' label"
        )

    # ── legendFormat: anomaly_family visible ──────────────────────────────────

    def test_anomaly_family_breakdown_target_legend_format_shows_anomaly_family(self):
        """AC3 (Task 4.19): Anomaly family breakdown target legendFormat must include
        {{anomaly_family}} so bar labels render correctly."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        targets = panel.get("targets", [])
        target_a = next((t for t in targets if t.get("refId") == "A"), None)
        assert target_a is not None, (
            "Anomaly family breakdown panel must have a target with refId='A'"
        )
        legend_format = target_a.get("legendFormat", "")
        assert "anomaly_family" in legend_format, (
            "Anomaly family breakdown legendFormat must include 'anomaly_family' so bar "
            "labels render (AC3)"
        )

    # ── Description ───────────────────────────────────────────────────────────

    def test_anomaly_family_breakdown_panel_has_description(self):
        """AC4 / UX-DR12 (Task 4.20): Anomaly family breakdown panel must have a non-empty
        one-sentence description field."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        assert panel.get("description", "").strip() != "", (
            "Anomaly family breakdown panel must have a non-empty description (UX-DR12)"
        )

    # ── noValue guard (NFR9 / UX-DR5) ────────────────────────────────────────

    def test_anomaly_family_breakdown_panel_has_no_value_field(self):
        """AC3 / NFR9 / UX-DR5 (Task 4.21): Anomaly family breakdown panel must set noValue
        in fieldConfig so anomaly families with no occurrences show 0 — not blank."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        no_value = panel.get("fieldConfig", {}).get("defaults", {}).get("noValue", None)
        assert no_value is not None, (
            "Anomaly family breakdown panel must have fieldConfig.defaults.noValue set "
            "(NFR9 / UX-DR5 — zero-state anomaly families)"
        )

    # ── Forbidden Grafana default palette colors ──────────────────────────────

    def test_no_grafana_default_palette_colors_in_anomaly_family_breakdown_panel(self):
        """AC4 / UX-DR1 (Task 4.22): No forbidden Grafana default palette colors may appear
        in anomaly family breakdown panel id=9 JSON (case-insensitive check)."""
        forbidden = {
            "#73BF69", "#F2495C", "#FF9830", "#FADE2A",
            "#5794F2", "#B877D9", "#37872D", "#C4162A", "#1F60C4", "#8F3BB8",
        }
        dashboard = self._load_main_dashboard()
        panel_json = json.dumps(
            [p for p in dashboard.get("panels", []) if p.get("id") == 9]
        ).upper()
        for color in forbidden:
            assert color not in panel_json, (
                f"Forbidden Grafana default color {color} found in anomaly family breakdown "
                f"panel id=9 (UX-DR1)"
            )

    # ── Label font size (UX-DR2) ──────────────────────────────────────────────

    def test_anomaly_family_breakdown_panel_text_title_size_meets_readability_minimum(self):
        """AC3 / UX-DR2 (Task 4.23): Anomaly family breakdown barchart
        options.text.titleSize must be >= 14 for projector readability."""
        dashboard = self._load_main_dashboard()
        panel = self._get_panel_by_id(dashboard, 9)
        assert panel is not None, "Anomaly family breakdown panel (id=9) not found"
        title_size = panel.get("options", {}).get("text", {}).get("titleSize", 0)
        assert title_size >= 14, (
            f"Anomaly family breakdown panel options.text.titleSize must be >= 14px (UX-DR2), "
            f"got {title_size}"
        )

    # ── Dashboard version ─────────────────────────────────────────────────────

    def test_dashboard_version_is_at_least_6(self):
        """Dashboard version must be >= 6 after story 3-2 panel additions (Task 4.24 / NFR12).
        Version must be bumped from 5 to 6 to reflect the new panels."""
        dashboard = self._load_main_dashboard()
        assert dashboard.get("version", 0) >= 6, (
            f"Dashboard version must be >= 6 after story 3-2, got {dashboard.get('version')}"
        )
