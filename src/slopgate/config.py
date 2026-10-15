"""Configuration loader for SlopGate (.env and policy.yaml)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
    # Strip empty string env vars so boto3 doesn't treat empty tokens as active bearer auth
    for _k in ["AWS_BEARER_TOKEN_BEDROCK", "AWS_SESSION_TOKEN", "GITHUB_WRITE_TOKEN", "GITHUB_SANDBOX_REPO"]:
        if _k in os.environ and not os.environ[_k].strip():
            del os.environ[_k]
except ImportError:
    pass

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore


@dataclass(frozen=True)
class Settings:
    """Application-wide settings loaded from environment / .env."""
    aws_region: str = os.getenv("AWS_REGION", "us-east-1")
    bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
    aws_access_key_id: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY")
    aws_session_token: Optional[str] = os.getenv("AWS_SESSION_TOKEN")
    aws_bearer_token_bedrock: Optional[str] = os.getenv("AWS_BEARER_TOKEN_BEDROCK")

    github_token: Optional[str] = os.getenv("GITHUB_TOKEN")
    github_write_token: Optional[str] = os.getenv("GITHUB_WRITE_TOKEN")
    github_sandbox_repo: Optional[str] = os.getenv("GITHUB_SANDBOX_REPO")

    dry_run: bool = os.getenv("SLOPGATE_DRY_RUN", "1") in ("1", "true", "True")
    max_bedrock_calls: int = int(os.getenv("SLOPGATE_MAX_BEDROCK_CALLS", "50"))
    max_output_tokens: int = int(os.getenv("SLOPGATE_MAX_OUTPUT_TOKENS", "150"))
    decider_threads: int = int(os.getenv("SLOPGATE_DECIDER_THREADS", "4"))
    decider_model: str = os.getenv(
        "SLOPGATE_DECIDER_MODEL", "StrandsAgents/strands-decider-2B-hobson-v21"
    )
    decider_device: str = os.getenv("SLOPGATE_DECIDER_DEVICE", "cpu")

    def doctor_summary(self) -> dict[str, str]:
        """Return safe display of set/unset variables with zero secret leakage."""
        return {
            "AWS_REGION": self.aws_region,
            "BEDROCK_MODEL_ID": self.bedrock_model_id,
            "AWS_CREDENTIALS": "SET" if (self.aws_access_key_id or self.aws_bearer_token_bedrock) else "UNSET",
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
