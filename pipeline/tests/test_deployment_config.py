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
    assert fly_config["env"]["APP_ENV"] == "production"


def test_github_actions_deploy_production_app() -> None:
    production_workflow = (ROOT / ".github" / "workflows" / "fly-production.yml").read_text()
    runbook = (ROOT / "RUNBOOK.md").read_text()

    assert "branches:" in production_workflow
    assert "- release" in production_workflow
    assert "flyctl deploy --config fly.toml --remote-only" in production_workflow
    assert "FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}" in production_workflow
    assert "working-directory: pipeline" in production_workflow

    assert "Production uses `pipeline/fly.toml`" in runbook
    assert "PR preview" not in runbook
