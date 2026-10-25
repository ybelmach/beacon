import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_ENV_FILE_VAR = "BEACON_ENV_FILE"

_VALID_LOG_LEVELS = frozenset(logging.getLevelNamesMapping())

_INSECURE_KEY_ENVIRONMENTS = frozenset({"local", "test"})
_MIN_SECRET_KEY_LENGTH = 32
_PLACEHOLDER_SECRET_KEYS = frozenset({"change-me", "changeme", "secret", "test-secret-key"})

Environment = Literal["local", "test", "dev", "staging", "production"]


def _env_file() -> Path:
    """Which dotenv to read. Overridable so tests never pick up a developer's real .env."""
    override = os.getenv(_ENV_FILE_VAR)
    return Path(override) if override else _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "beacon-backend"
    service_name: str = "backend"
    environment: Environment = "local"
    base_url: str = "http://localhost:8000"
    # Verbose local mode: SQL echo and a per-request "started" line. Never affects
    # what a client sees – error bodies are the same shape in every environment.
    debug_mode: bool = False

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "console"] = "json"

    # HTTP
    cors_allow_origins: str = ""
    cors_allow_credentials: bool = False
    readiness_timeout_seconds: float = 2.0
    enable_docs: bool = False

    # Security
    secret_key: SecretStr
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    # Postgres
    postgres_dsn: str
    postgres_pool_size: int = 10
    postgres_max_overflow: int = 10
    postgres_pool_recycle_seconds: int = 1800

    # Redis
    redis_dsn: str
    redis_socket_timeout_seconds: float = 1.0

    # S3 (RustFS locally)
    s3_endpoint_url: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str

    # ClickHouse
    clickhouse_host: str
    clickhouse_port: int = 8123
    clickhouse_user: str
    clickhouse_password: str
    clickhouse_db: str

    # Kafka
    kafka_bootstrap_servers: str
    kafka_topic_events: str = "telemetry.events"
    kafka_topic_dlq: str = "telemetry.dlq"
    kafka_consumer_group: str = "storage"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def kafka_servers(self) -> list[str]:
        return [server.strip() for server in self.kafka_bootstrap_servers.split(",") if server.strip()]

    @field_validator("log_level", mode="after")
    @classmethod
    def _normalise_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in _VALID_LOG_LEVELS:
            raise ValueError(f"log_level must be one of {sorted(_VALID_LOG_LEVELS)}, got {value!r}")
        return level

    @model_validator(mode="after")
    def _validate_cors(self) -> Self:
        if self.cors_allow_credentials and "*" in self.cors_origins:
            raise ValueError("cors_allow_credentials=true requires an explicit origin list, not '*'")
        return self

    @model_validator(mode="after")
    def _validate_secret_key(self) -> Self:
        if self.environment in _INSECURE_KEY_ENVIRONMENTS:
            return self
        key = self.secret_key.get_secret_value()
        if key.lower() in _PLACEHOLDER_SECRET_KEYS or len(key) < _MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                f"secret_key must be a random value of at least {_MIN_SECRET_KEY_LENGTH} characters "
                f"outside {sorted(_INSECURE_KEY_ENVIRONMENTS)} (environment={self.environment!r}); "
                "generate one with: openssl rand -hex 32"
            )
        return self

    @model_validator(mode="after")
    def _validate_probe_timeouts(self) -> Self:
        if self.redis_socket_timeout_seconds >= self.readiness_timeout_seconds:
            raise ValueError(
                "redis_socket_timeout_seconds must be strictly below readiness_timeout_seconds "
                f"(got {self.redis_socket_timeout_seconds} >= {self.readiness_timeout_seconds})"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    # Required fields are supplied by the environment, not by this call site.
    return Settings(_env_file=_env_file())  # pyright: ignore[reportCallIssue]
