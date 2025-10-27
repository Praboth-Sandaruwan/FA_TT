from __future__ import annotations

from projects.02-intermediate.app.core.config import Settings


def test_environment_profiles_apply_defaults() -> None:
    dev = Settings(environment="development")
    assert dev.environment == "development"
    assert dev.log_level == "DEBUG"
    assert dev.reload is True
    assert dev.cache_enabled is True

    test_profile = Settings(environment="test")
    assert test_profile.environment == "test"
    assert test_profile.log_level == "WARNING"
    assert test_profile.reload is False
    assert test_profile.cache_enabled is False

    ci_profile = Settings(environment="ci")
    assert ci_profile.environment == "ci"
    assert ci_profile.log_level == "INFO"
    assert ci_profile.reload is False
    assert ci_profile.cache_enabled is True


def test_environment_aliases_are_normalised() -> None:
    alias = Settings(environment="DEV")
    assert alias.environment == "development"


def test_environment_profile_respects_explicit_overrides(monkeypatch) -> None:
    monkeypatch.setenv("INTERMEDIATE_LOG_LEVEL", "error")
    overridden = Settings(environment="test")
    assert overridden.log_level == "ERROR"

    monkeypatch.delenv("INTERMEDIATE_LOG_LEVEL", raising=False)
    monkeypatch.setenv("INTERMEDIATE_CACHE_ENABLED", "true")
    cache_enabled = Settings(environment="test")
    assert cache_enabled.cache_enabled is True
