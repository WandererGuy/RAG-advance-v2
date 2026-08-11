"""Configuration. Everything env-derived is read here — no os.getenv() elsewhere."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root: backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> repo
REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Process configuration, read from the repo-root .env.

    The .env path is resolved from __file__ rather than the working directory, because the
    Makefile runs every command from backend/ while docker compose runs from the repo root.
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = Field(
        default="postgresql+asyncpg://rag:rag@localhost:5432/rag",
        description="Must use the postgresql+asyncpg:// scheme — see ADR-0002.",
    )
    log_level: str = "INFO"

    # --- LLM, via LiteLLM. Provider is never hardcoded; see ADR-0002. ---
    default_llm_provider: str = "GEMINI"
    default_llm_model_name: str = "gemini-3.6-flash"
    default_llm_api_key: str = ""
    default_llm_api_base: str = ""
    default_llm_custom_provider: str = ""

    # --- Embedding ---
    embedding_provider: str = "GEMINI"
    embedding_model_name: str = "gemini-embedding-001"
    embedding_api_key: str = ""
    embedding_dimensions: int = 768

    # --- Pipeline defaults, frozen until Phase 6 (CLAUDE.md 5.3) ---
    pipeline_name: str = "naive-v1"
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 5
    prompt_version: str = "v1"

    @property
    def llm_model(self) -> str:
        """LiteLLM model identifier, e.g. "gemini/gemini-3.6-flash"."""
        return f"{self.default_llm_provider.lower()}/{self.default_llm_model_name}"

    @property
    def embedding_model(self) -> str:
        """LiteLLM model identifier for embeddings."""
        return f"{self.embedding_provider.lower()}/{self.embedding_model_name}"

    def pipeline_config(self, **overrides: Any) -> PipelineConfig:
        """Build the default PipelineConfig, with per-pipeline overrides applied."""
        base = PipelineConfig(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            top_k=self.top_k,
            retriever="dense",
            embedding_model=self.embedding_model,
            embedding_dimensions=self.embedding_dimensions,
            llm_model=self.llm_model,
            prompt_version=self.prompt_version,
        )
        return replace_config(base, **overrides)


@dataclass(frozen=True)
class PipelineConfig:
    """The full configuration of one RAG pipeline.

    Embedded verbatim into every results/*.json, so a number can always be traced back to
    the exact configuration that produced it. Frozen: a pipeline's config must not drift
    between the retrieve step and the answer step of the same run.
    """

    chunk_size: int
    chunk_overlap: int
    top_k: int
    retriever: str
    embedding_model: str
    embedding_dimensions: int
    llm_model: str
    prompt_version: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for results/*.json."""
        return asdict(self)


def replace_config(config: PipelineConfig, **overrides: Any) -> PipelineConfig:
    """Return a copy of `config` with the named fields replaced.

    Rejects unknown field names loudly — a typo'd override that was silently dropped would
    mean a results file claiming a configuration that never ran.
    """
    known = set(PipelineConfig.__dataclass_fields__)
    unknown = set(overrides) - known
    if unknown:
        raise ValueError(f"unknown PipelineConfig fields: {sorted(unknown)}")
    return PipelineConfig(**{**config.to_dict(), **overrides})


@lru_cache
def get_settings() -> Settings:
    """Cached singleton. Import this, not the class."""
    return Settings()
