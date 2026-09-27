"""Central configuration loaded from environment variables / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o"))
    llm_temperature: float = field(default_factory=lambda: _env_float("LLM_TEMPERATURE", 0.2))
    llm_max_output_tokens: int = field(default_factory=lambda: _env_int("LLM_MAX_OUTPUT_TOKENS", 8000))
    use_native_structured_outputs: bool = field(
        default_factory=lambda: _env_bool("USE_NATIVE_STRUCTURED_OUTPUTS", True)
    )

    checkpoint_dir: str = field(default_factory=lambda: os.getenv("CHECKPOINT_DIR", "output/.checkpoints"))
    dedup_similarity_threshold: float = field(
        default_factory=lambda: _env_float("DEDUP_SIMILARITY_THRESHOLD", 0.88)
    )

    jira_base_url: str = field(default_factory=lambda: os.getenv("JIRA_BASE_URL", ""))
    jira_email: str = field(default_factory=lambda: os.getenv("JIRA_EMAIL", ""))
    jira_api_token: str = field(default_factory=lambda: os.getenv("JIRA_API_TOKEN", ""))

    existing_test_cases_csv: str = field(
        default_factory=lambda: os.getenv("EXISTING_TEST_CASES_CSV", "data/sample_existing_test_cases.csv")
    )
    existing_defects_csv: str = field(
        default_factory=lambda: os.getenv("EXISTING_DEFECTS_CSV", "data/sample_defects.csv")
    )

    @property
    def jira_configured(self) -> bool:
        return bool(self.jira_base_url and self.jira_email and self.jira_api_token)

    @property
    def llm_configured(self) -> bool:
        return bool(self.openai_api_key)


settings = Settings()
