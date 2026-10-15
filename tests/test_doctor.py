"""Unit test for slopgate doctor and configuration loading."""

from slopgate.cli import run_doctor
from slopgate.config import get_settings


def test_settings_loaded():
    settings = get_settings()
    assert settings.bedrock_model_id == "amazon.nova-micro-v1:0"
    assert settings.decider_threads == 4
    assert settings.dry_run is True


def test_doctor_runs_cleanly(capsys):
    exit_code = run_doctor()
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "SlopGate Doctor" in captured.out
    assert "Python Version" in captured.out
    assert "AWS_REGION" in captured.out
