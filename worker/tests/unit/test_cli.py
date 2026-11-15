import pytest
from typer.testing import CliRunner

from content_engine.config import get_settings
from content_engine.main import app

runner = CliRunner()


def test_hello_runs_when_settings_are_present(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")

    result = runner.invoke(app, ["hello"])

    assert result.exit_code == 0
    assert "claude" in result.output


def test_hello_fails_when_a_key_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "test-key")

    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 1
    assert "Missing or empty setting: ANTHROPIC_API_KEY" in result.output
