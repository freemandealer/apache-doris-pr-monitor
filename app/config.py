from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

DEFAULT_CONFIG_PATHS = (
    os.environ.get("PR_MONITOR_CONFIG"),
    "config.yaml",
    "config.example.yaml",
)


class GitHubConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    api_base: str = Field(default="https://api.github.com")
    web_base: str = Field(default="https://github.com")


class TargetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    user: str
    repos: List[str] = Field(default_factory=list)


class PollingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interval_seconds: int = Field(default=300, ge=15)


class ServerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1)


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: Optional[str] = None


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    github: GitHubConfig
    targets: List[TargetConfig]
    polling: PollingConfig = Field(default_factory=PollingConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, value: List[TargetConfig]) -> List[TargetConfig]:
        if not value:
            raise ValueError("At least one target must be configured.")
        return value


def _resolve_config_path(path: Optional[str]) -> Path:
    if path:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Config file not found: {resolved}")
        return resolved
    for candidate in DEFAULT_CONFIG_PATHS:
        if not candidate:
            continue
        candidate_path = Path(candidate)
        if candidate_path.exists():
            return candidate_path
    raise FileNotFoundError("No config.yaml or config.example.yaml found.")


def _apply_env_overrides(data: dict) -> None:
    token_override = os.environ.get("GITHUB_TOKEN")
    if token_override:
        data.setdefault("github", {})
        data["github"]["token"] = token_override
    api_key_override = os.environ.get("PR_MONITOR_API_KEY")
    if api_key_override:
        data.setdefault("auth", {})
        data["auth"]["api_key"] = api_key_override


def load_config(path: Optional[str] = None) -> AppConfig:
    config_path = _resolve_config_path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    _apply_env_overrides(data)
    try:
        return AppConfig.model_validate(data)
    except ValidationError as err:
        raise RuntimeError(f"Invalid configuration: {err}") from err
