from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_fly_production_config_targets_pipeline_app() -> None:
    fly_config = tomllib.loads((ROOT / "pipeline" / "fly.toml").read_text())

    assert fly_config["app"] == "sorigamis"
    assert fly_config["primary_region"] == "nrt"
    assert fly_config["http_service"]["internal_port"] == 8080
    assert fly_config["http_service"]["min_machines_running"] == 1


def test_fly_preview_config_is_distinct_from_production() -> None:
    preview_config = tomllib.loads((ROOT / "pipeline" / "fly.preview.toml").read_text())

    assert preview_config["app"] == "sorigamis-pr-template"
    assert preview_config["primary_region"] == "nrt"
    assert preview_config["http_service"]["internal_port"] == 8080
    assert preview_config["http_service"]["min_machines_running"] == 0
    assert preview_config["env"]["APP_ENV"] == "preview"


def test_github_actions_deploy_production_and_preview_apps() -> None:
    production_workflow = (ROOT / ".github" / "workflows" / "fly-production.yml").read_text()
    preview_workflow = (ROOT / ".github" / "workflows" / "fly-preview.yml").read_text()
    runbook = (ROOT / "RUNBOOK.md").read_text()

    assert "branches:" in production_workflow
    assert "- release" in production_workflow
    assert "flyctl deploy --config fly.toml --remote-only" in production_workflow
    assert "FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}" in production_workflow
    assert "working-directory: pipeline" in production_workflow

    assert "branches-ignore:" in preview_workflow
    assert "- release" in preview_workflow
    assert "superfly/fly-pr-review-apps" in preview_workflow
    assert "path: pipeline" in preview_workflow
    assert "config: fly.preview.toml" in preview_workflow
    assert "name: sorigamis-pr-${{ github.event.number }}" in preview_workflow

    assert "fly tokens create org" in runbook
    assert "not an app-scoped deploy token" in runbook
