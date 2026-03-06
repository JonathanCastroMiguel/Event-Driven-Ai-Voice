from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://voiceai:voiceai@localhost:5432/voiceai"
    redis_url: str = "redis://localhost:6379/0"
    sentry_dsn: str | None = None
    otel_endpoint: str | None = None
    otel_service_name: str = "voice-ai-runtime"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # asyncpg pool
    db_pool_min: int = 5
    db_pool_max: int = 20

    # Redis pool
    redis_pool_max: int = 20

    # Embedding thread pool
    embedding_thread_pool_size: int = 4

    # LLM fallback
    llm_fallback_url: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_model: str = "gpt-4o-mini"
    llm_fallback_timeout_s: float = 2.0
    llm_fallback_max_connections: int = 10

    # Conversation history
    max_history_turns: int = 10
    max_history_chars: int = 2000

    # Context-aware routing
    routing_context_window: int = 1
    routing_short_text_chars: int = 20
    llm_context_window: int = 3

    # Router registry
    router_registry_path: str = "router_registry/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
