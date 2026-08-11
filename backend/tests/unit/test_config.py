"""PipelineConfig round-trips into results/*.json, so its serialization is load-bearing."""

from __future__ import annotations

import pytest

from app.core.config import PipelineConfig, get_settings, replace_config


def _config(**overrides: object) -> PipelineConfig:
    base = {
        "chunk_size": 800,
        "chunk_overlap": 100,
        "top_k": 5,
        "retriever": "dense",
        "embedding_model": "gemini/gemini-embedding-001",
        "embedding_dimensions": 768,
        "llm_model": "gemini/gemini-3.6-flash",
        "prompt_version": "v1",
    }
    return PipelineConfig(**{**base, **overrides})  # type: ignore[arg-type]


def test_to_dict_contains_every_field() -> None:
    """A field missing from the dict is a field missing from every results file."""
    as_dict = _config().to_dict()
    assert set(as_dict) == set(PipelineConfig.__dataclass_fields__)
    assert as_dict["chunk_size"] == 800
    assert as_dict["embedding_dimensions"] == 768


def test_to_dict_is_json_serializable() -> None:
    import json

    assert json.loads(json.dumps(_config().to_dict()))["retriever"] == "dense"


def test_replace_returns_a_copy_and_leaves_the_original_alone() -> None:
    original = _config()
    modified = replace_config(original, top_k=20)

    assert modified.top_k == 20
    assert original.top_k == 5
    # Only the named field moves; anything else changing would silently mislabel a result.
    assert modified.to_dict() | {"top_k": 5} == original.to_dict()


def test_replace_rejects_an_unknown_field() -> None:
    """A typo'd override that was silently dropped would produce a results file claiming a
    configuration that never actually ran."""
    with pytest.raises(ValueError, match="unknown PipelineConfig fields"):
        replace_config(_config(), tok_k=20)


def test_config_is_frozen() -> None:
    with pytest.raises(AttributeError):
        _config().top_k = 99  # type: ignore[misc]


def test_settings_defaults_match_the_frozen_phase_values() -> None:
    """CLAUDE.md 5.3: these stay put until Phase 6."""
    settings = get_settings()
    assert (settings.chunk_size, settings.chunk_overlap, settings.top_k) == (800, 100, 5)


def test_settings_builds_litellm_model_identifiers() -> None:
    settings = get_settings()
    assert (
        settings.llm_model
        == f"{settings.default_llm_provider.lower()}/{settings.default_llm_model_name}"
    )
    assert "/" in settings.embedding_model


def test_database_url_uses_the_async_driver() -> None:
    """A sync URL would work for alembic and then fail at the first async session (ADR-0002)."""
    assert get_settings().database_url.startswith("postgresql+asyncpg://")


def test_pipeline_config_from_settings_applies_overrides() -> None:
    config = get_settings().pipeline_config(retriever="hybrid")
    assert config.retriever == "hybrid"
    assert config.top_k == 5
