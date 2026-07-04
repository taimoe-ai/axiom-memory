"""Runtime configuration, loaded from environment variables with the AXIOM_ prefix."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AXIOM_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://axiom:axiom@localhost:5432/axiom"

    # Google OAuth for interactive clients (ChatGPT and claude.ai connectors
    # require a full OAuth flow). All three must be set together; base_url is
    # the public origin OAuth endpoints are served from, e.g.
    # https://axiom.example.com (or http://localhost:8080 when testing the
    # flow locally — both must be registered as redirect URIs on the Google
    # OAuth app, with the /auth/callback path).
    google_client_id: str = ""
    google_client_secret: str = ""
    base_url: str = ""

    # Comma-separated emails allowed through Google login. This server holds
    # one person's memory: anyone else who authenticates is rejected.
    allowed_emails: str = ""

    # Static bearer token for headless callers (curl, CI, cron), checked
    # alongside OAuth. Empty disables it. Clients send
    # `Authorization: Bearer <token>`.
    service_token: str = ""

    # HTTP transport.
    host: str = "127.0.0.1"
    port: int = 8080

    # Markdown export target (a local checkout; commit/push is left to the caller).
    export_dir: Path = Path("exports")

    # Semantic recall (Gemini embeddings). Empty key disables the semantic
    # layer entirely — recall degrades to lexical-only, nothing breaks.
    gemini_api_key: str = ""
    embedding_model: str = "gemini-embedding-2"
    # Must match the vector(N) column in migration 0005.
    embedding_dims: int = 768
    # Cosine similarity below this counts as zero relevance; above it, it is
    # rescaled to 0..1. Calibrated on real memories: related pairs ~0.65,
    # unrelated ~0.50.
    semantic_floor: float = 0.55

    # Minimum trigram similarity for a new memory to be flagged as a
    # suspected duplicate of an existing one.
    dedup_threshold: float = 0.35

    # Minimum combined score (FTS rank or trigram word similarity) for a
    # memory to appear in recall results.
    recall_threshold: float = 0.1

    # Retrieval-based forgetting: recall relevance is multiplied by a recency
    # factor that halves every N days since a memory was last used (or created,
    # if never recalled). This only reorders results — it never filters them
    # (the recall_threshold above still runs on raw relevance). `state` memories
    # are meant to go stale, so they decay faster than everything else.
    recall_half_life_days: float = 180.0
    state_half_life_days: float = 30.0
    # Procedural memories (how-to workflows, behavioural rules) are the most
    # decay-resistant kind — a workflow stays valid even when unused for
    # months — so they outlast everything else in the ranking.
    procedural_half_life_days: float = 540.0

    # Retrieval strengthening (ACT-R): recall score is multiplied by
    # 1 + ln(1 + use_count) / use_count_dampening, so frequently used memories
    # win ties without ever outranking a clearly better lexical/semantic match.
    # Higher dampening = weaker frequency effect. At 4.0: 10 uses ≈ x1.6,
    # 50 ≈ x2.0, 500 ≈ x2.6.
    use_count_dampening: float = 4.0

    # `axiom review` consolidation report thresholds.
    stale_state_days: int = 90  # state memories untouched this long are flagged
    zombie_days: int = 60  # never-recalled memories older than this are flagged

    # Episodic events (log_event): weak ambient signals, never part of recall.
    # Trigram similarity for two events to count as the same pattern.
    event_similarity: float = 0.3
    # Events older than this are deleted on the next write — the episodic
    # layer forgets outright, unlike memories which only sink in ranking.
    event_retention_days: int = 180
    # `axiom review` looks for patterns within this window...
    event_window_days: int = 30
    # ...and reports clusters of at least this many similar events.
    event_min_count: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
