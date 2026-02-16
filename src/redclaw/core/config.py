"""
ConfigManager — Loads YAML engagement configs defining targets, tools, safety, and LLM settings.

Engagement config structure:
  engagement:
    name: "Test Engagement"
    targets:
      include: ["10.10.10.0/24", "example.com"]
      exclude: ["10.10.10.1"]
    phases:
      reconnaissance: { enabled: true, tools: ["nmap", "masscan"] }
      scanning: { enabled: true, tools: ["nmap", "nuclei"] }
      ...
    safety:
      rate_limit: 100          # max commands/min
      max_concurrent: 5
      require_approval: ["exploitation", "post_exploitation"]
      blocked_commands: ["rm -rf /", "mkfs", "dd if=", "shutdown", "reboot"]
    llm:
      provider: "kaggle_phi4"
      endpoint: "http://localhost:5000/v1"
      model: "phi-4"
      max_tokens: 4096
      temperature: 0.1
"""

from __future__ import annotations

import os
import copy
import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("redclaw.core.config")


# ── Pydantic models for validated configuration ──────────────────────────────

class TargetScope(BaseModel):
    """Defines in-scope and out-of-scope targets."""
    include: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)

    @field_validator("include")
    @classmethod
    def must_have_targets(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one target must be specified in 'include'")
        return v


class PhaseConfig(BaseModel):
    """Configuration for a single pipeline phase."""
    enabled: bool = True
    tools: list[str] = Field(default_factory=list)
    timeout: int = 3600  # seconds
    max_retries: int = 3


class SafetyConfig(BaseModel):
    """Safety constraints for the engagement."""
    rate_limit: int = 100  # commands per minute
    max_concurrent: int = 5
    require_approval: list[str] = Field(
        default_factory=lambda: ["exploitation", "post_exploitation"]
    )
    blocked_commands: list[str] = Field(
        default_factory=lambda: [
            "rm -rf /", "rm -rf /*", "mkfs", "dd if=",
            "shutdown", "reboot", "halt", "init 0", "init 6",
            ":(){:|:&};:", "chmod -R 777 /", "chown -R",
        ]
    )
    time_window: Optional[dict[str, str]] = None  # {"start": "22:00", "end": "06:00"}


class LLMConfig(BaseModel):
    """LLM provider configuration."""
    provider: str = "kaggle_phi4"
    endpoint: str = "http://localhost:5000/v1"
    model: str = "phi-4"
    max_tokens: int = 4096
    temperature: float = 0.1
    timeout: int = 120
    retry_count: int = 3
    fallback_provider: Optional[str] = "ollama"
    fallback_endpoint: Optional[str] = "http://localhost:11434/v1"


class OpenClawConfig(BaseModel):
    """OpenClaw integration settings."""
    enabled: bool = True
    openclaw_path: str = "./openclaw"
    skills_dir: str = "./src/redclaw/skills"
    sandbox_enabled: bool = True
    memory_enabled: bool = True


class SessionConfig(BaseModel):
    """Dual-session multiplexer settings."""
    local_shell: str = "/bin/bash"
    ssh_timeout: int = 30
    ssh_retries: int = 3
    heartbeat_interval: int = 15
    command_timeout: int = 300


class EngagementConfig(BaseModel):
    """Top-level engagement configuration."""
    name: str = "Unnamed Engagement"
    targets: TargetScope = Field(default_factory=TargetScope)
    phases: dict[str, PhaseConfig] = Field(default_factory=dict)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    openclaw: OpenClawConfig = Field(default_factory=OpenClawConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    output_dir: str = "./output"


# ── ConfigManager ─────────────────────────────────────────────────────────────

class ConfigManager:
    """
    Loads, validates, and provides engagement configuration.

    Usage:
        config = ConfigManager.from_file("engagement.yaml")
        targets = config.targets.include
        llm = config.llm
    """

    def __init__(self, config: EngagementConfig):
        self._config = config
        self._overrides: dict[str, Any] = {}
        logger.info(f"ConfigManager initialized: engagement='{config.name}'")

    @classmethod
    def from_file(cls, path: str | Path) -> "ConfigManager":
        """Load config from a YAML file."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        engagement_data = raw.get("engagement", raw)
        config = EngagementConfig(**engagement_data)
        logger.info(f"Loaded config from {path}")
        return cls(config)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConfigManager":
        """Create from a dictionary (useful for testing)."""
        engagement_data = data.get("engagement", data)
        config = EngagementConfig(**engagement_data)
        return cls(config)

    @classmethod
    def default(cls) -> "ConfigManager":
        """Create with default configuration."""
        config = EngagementConfig(
            name="Default Engagement",
            targets=TargetScope(include=["127.0.0.1"]),
        )
        return cls(config)

    # ── Property accessors ────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self._config.name

    @property
    def targets(self) -> TargetScope:
        return self._config.targets

    @property
    def phases(self) -> dict[str, PhaseConfig]:
        return self._config.phases

    @property
    def safety(self) -> SafetyConfig:
        return self._config.safety

    @property
    def llm(self) -> LLMConfig:
        return self._config.llm

    @property
    def openclaw(self) -> OpenClawConfig:
        return self._config.openclaw

    @property
    def session(self) -> SessionConfig:
        return self._config.session

    @property
    def output_dir(self) -> Path:
        return Path(self._config.output_dir)

    # ── Runtime overrides ─────────────────────────────────────────────────

    def override(self, key: str, value: Any) -> None:
        """Apply a runtime override (does not persist)."""
        self._overrides[key] = value
        logger.debug(f"Config override: {key}={value}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value with override support."""
        if key in self._overrides:
            return self._overrides[key]
        parts = key.split(".")
        obj = self._config
        for part in parts:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                return default
        return obj

    def to_dict(self) -> dict[str, Any]:
        """Serialize current config to dict."""
        return self._config.model_dump()

    def is_phase_enabled(self, phase_name: str) -> bool:
        """Check if a specific phase is enabled."""
        phase = self._config.phases.get(phase_name)
        return phase.enabled if phase else True  # default enabled

    def requires_approval(self, phase_name: str) -> bool:
        """Check if a phase requires human approval."""
        return phase_name in self._config.safety.require_approval

    def __repr__(self) -> str:
        return (
            f"ConfigManager(name='{self.name}', "
            f"targets={len(self.targets.include)}, "
            f"llm='{self.llm.provider}')"
        )
