"""Unit tests for configuration and policy YAML loading."""

import pytest
from pydantic import ValidationError

from slopgate.config import PolicyConfig, get_settings, load_policy


def test_settings_load_env():
    settings = get_settings()
    assert settings.bedrock_model_id == "amazon.nova-micro-v1:0"
    assert settings.decider_threads == 4
    assert settings.dry_run is True


def test_load_default_policy():
    policy = load_policy()
    assert isinstance(policy, PolicyConfig)
    assert policy.version == 1
    assert policy.bands.choice.high_at_least == 0.80
    assert policy.bands.noul.true_at_least == 0.85
    assert policy.state.max_tokens == 250
    assert policy.state.include_author_history is False
    assert "real_bug_report" in policy.routing
    assert "close_item" in policy.tools_gated


def test_policy_forbids_unknown_keys(tmp_path):
    invalid_yaml = tmp_path / "invalid_policy.yaml"
    invalid_yaml.write_text(
        """
version: 1
repo: "pallets/flask"
unknown_rogue_key: "malicious_or_accidental_value"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        load_policy(invalid_yaml)


def test_policy_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_policy("non_existent_policy_file_xyz.yaml")
