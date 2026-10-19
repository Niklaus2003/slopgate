"""Configuration loader for SlopGate (.env and policy.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

try:
    from dotenv import load_dotenv

    load_dotenv()
    # Strip empty string env vars so boto3 doesn't treat empty tokens as active bearer auth
    for _k in [
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_SESSION_TOKEN",
        "GITHUB_WRITE_TOKEN",
        "GITHUB_SANDBOX_REPO",
    ]:
        if _k in os.environ and not os.environ[_k].strip():
            del os.environ[_k]
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Policy YAML Models (Strict: unknown keys raise validation errors)
# ---------------------------------------------------------------------------


class StatePolicyConfig(BaseModel):
    """Constraints for compact state generation."""

    model_config = ConfigDict(extra="forbid")

    max_tokens: int = 450
    body_chars: int = 1200
    include_author_history: bool = False


class ChoiceBandConfig(BaseModel):
    """Thresholds for normalized choice confidence."""

    model_config = ConfigDict(extra="forbid")

    high_at_least: float = 0.80
    medium_at_least: float = 0.50


class NoulBandConfig(BaseModel):
    """Probability thresholds for yes/no questions."""

    model_config = ConfigDict(extra="forbid")

    true_at_least: float = 0.85
    false_at_most: float = 0.15


class BandsPolicyConfig(BaseModel):
    """Collection of confidence band thresholds."""

    model_config = ConfigDict(extra="forbid")

    choice: ChoiceBandConfig = Field(default_factory=ChoiceBandConfig)
    noul: NoulBandConfig = Field(default_factory=NoulBandConfig)


class DuplicatePolicyConfig(BaseModel):
    """Lexical duplicate detection thresholds."""

    model_config = ConfigDict(extra="forbid")

    similarity_min: float = 0.55


class RoutingEntryConfig(BaseModel):
    """Action mappings for a specific item classification."""

    model_config = ConfigDict(extra="forbid")

    high: str = "proceed"
    medium: str = "confirm"
    low: str = "guide"


class ToolGateEntryConfig(BaseModel):
    """Gating requirements for a specific tool."""

    model_config = ConfigDict(extra="forbid")

    requires: list[str] = Field(default_factory=list)
    always: str | None = None


class PolicyConfig(BaseModel):
    """Full policy specification from policy.yaml."""

    model_config = ConfigDict(extra="forbid")

    version: int = 1
    repo: str = "owner/name"
    state: StatePolicyConfig = Field(default_factory=StatePolicyConfig)
    bands: BandsPolicyConfig = Field(default_factory=BandsPolicyConfig)
    duplicate: DuplicatePolicyConfig = Field(default_factory=DuplicatePolicyConfig)
    routing: dict[str, RoutingEntryConfig] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    templates: dict[str, str] = Field(default_factory=dict)
    tools_gated: dict[str, ToolGateEntryConfig] = Field(default_factory=dict)


def load_policy(path: str | Path | None = None) -> PolicyConfig:
    """Load and validate policy configuration from YAML file.

    Raises:
        FileNotFoundError: If explicitly provided path does not exist.
        pydantic.ValidationError: If YAML format is invalid or contains unknown keys.
    """
    if path is not None:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Policy file not found: {p}")
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return PolicyConfig.model_validate(raw)

    # Search default locations
    for candidate in [Path("policy.yaml"), Path("policy.example.yaml")]:
        if candidate.is_file():
            raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            return PolicyConfig.model_validate(raw)

    return PolicyConfig()


# ---------------------------------------------------------------------------
# Environment Settings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Settings:
    """Application-wide settings loaded from environment / .env."""

    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    aws_access_key_id: str | None = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_session_token: str | None = os.getenv("AWS_SESSION_TOKEN")
    aws_bearer_token_bedrock: str | None = os.getenv("AWS_BEARER_TOKEN_BEDROCK")

    github_token: str | None = os.getenv("GITHUB_TOKEN")
    github_write_token: str | None = os.getenv("GITHUB_WRITE_TOKEN")
    github_sandbox_repo: str | None = os.getenv("GITHUB_SANDBOX_REPO")

    dry_run: bool = os.getenv("SLOPGATE_DRY_RUN", "1") in ("1", "true", "True")
    max_bedrock_calls: int = int(os.getenv("SLOPGATE_MAX_BEDROCK_CALLS", "50"))
    max_output_tokens: int = int(os.getenv("SLOPGATE_MAX_OUTPUT_TOKENS", "150"))
    decider_threads: int = int(os.getenv("SLOPGATE_DECIDER_THREADS", "4"))
    decider_model: str = os.getenv(
        "SLOPGATE_DECIDER_MODEL", "StrandsAgents/strands-decider-2B-hobson-v21"
    )
    decider_device: str = os.getenv("SLOPGATE_DECIDER_DEVICE", "cpu")

    # Groq configuration (active OSS engine while Bedrock credits undergo 2-3 mo verification)
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

    def doctor_summary(self) -> dict[str, str]:
        """Return safe display of set/unset variables with zero secret leakage."""
        return {
            "AWS_REGION": self.aws_region,
            "BEDROCK_MODEL_ID": self.bedrock_model_id,
            "AWS_CREDENTIALS": "SET"
            if (self.aws_access_key_id or self.aws_bearer_token_bedrock)
            else "UNSET",
            "GROQ_API_KEY": "SET" if self.groq_api_key else "UNSET",
            "GROQ_MODEL": self.groq_model,
            "GITHUB_TOKEN": "SET" if self.github_token else "UNSET",
            "GITHUB_WRITE_TOKEN": "SET" if self.github_write_token else "UNSET",
            "GITHUB_SANDBOX_REPO": self.github_sandbox_repo or "UNSET",
            "SLOPGATE_DRY_RUN": "ENABLED" if self.dry_run else "DISABLED",
            "SLOPGATE_MAX_BEDROCK_CALLS": str(self.max_bedrock_calls),
            "SLOPGATE_MAX_OUTPUT_TOKENS": str(self.max_output_tokens),
            "SLOPGATE_DECIDER_THREADS": str(self.decider_threads),
            "SLOPGATE_DECIDER_MODEL": self.decider_model,
            "SLOPGATE_DECIDER_DEVICE": self.decider_device,
        }


def get_settings() -> Settings:
    """Retrieve global settings instance."""
    return Settings()
