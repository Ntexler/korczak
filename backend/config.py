"""Korczak AI — Configuration."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Korczak AI"
    debug: bool = False

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""  # anon/public key
    supabase_service_key: str = ""  # service role key (backend only)
    database_url: str = ""  # Direct PostgreSQL connection

    # LLM
    anthropic_api_key: str = ""
    analysis_model: str = "claude-sonnet-4-20250514"
    navigator_model: str = "claude-sonnet-4-20250514"
    haiku_model: str = "claude-haiku-4-5-20251001"
    sonnet_model: str = "claude-sonnet-4-20250514"

    # Embeddings
    openai_api_key: str = ""  # For text-embedding-3-small
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536

    # Perplexity
    perplexity_api_key: str = ""
    perplexity_model: str = "sonar-pro"

    # OpenAlex
    openalex_email: str = ""  # Polite pool (faster rate limits)

    # CORS — frontend_url plus optional comma-separated extra origins
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = ""  # e.g. "https://korczak.vercel.app"

    @property
    def allowed_origins(self) -> list[str]:
        origins = [self.frontend_url]
        if self.cors_origins:
            origins.extend(o.strip() for o in self.cors_origins.split(",") if o.strip())
        return list(dict.fromkeys(origins))

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
