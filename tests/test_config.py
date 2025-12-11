from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.config import AppConfig, load_config


def write_config(tmp_path: Path) -> Path:
    payload = {
        "github": {
            "token": "dummy",
            "api_base": "https://api.github.com",
            "web_base": "https://github.com",
        },
        "targets": [
            {"label": "demo", "user": "alice", "repos": ["org/repo"]},
        ],
    }
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return config_file


def test_load_config_from_path(tmp_path: Path) -> None:
    config_file = write_config(tmp_path)
    config = load_config(str(config_file))
    assert isinstance(config, AppConfig)
    assert config.targets[0].user == "alice"


def test_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config_file = write_config(tmp_path)
    monkeypatch.setenv("GITHUB_TOKEN", "override")
    monkeypatch.setenv("PR_MONITOR_API_KEY", "secret")
    config = load_config(str(config_file))
    assert config.github.token == "override"
    assert config.auth.api_key == "secret"
