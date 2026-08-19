"""
Configuration management for TU5G platform backend.
Uses Pydantic Settings to load and validate environment variables.
"""

from functools import lru_cache
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings class. Loaded from environment variables and/or .env file.
    """
    # JWT & Auth
    JWT_SECRET: str = Field(default="supersecret_tu5g_jwt_token_key_change_me_in_prod", description="Secret key for JWT generation")
    ALGORITHM: str = Field(default="HS256", description="Algorithm used for signing JWT tokens")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, description="Access token expiration in minutes")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/tu5g",
        description="Async PostgreSQL database connection URL"
    )

    # LLM Providers
    LLM_PROVIDER: str = Field(default="openai", description="Default LLM provider (openai, azure, anthropic)")
    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API key")
    AZURE_OPENAI_API_KEY: str | None = Field(default=None, description="Azure OpenAI API key")
    AZURE_OPENAI_ENDPOINT: str | None = Field(default=None, description="Azure OpenAI endpoint URL")
    ANTHROPIC_API_KEY: str | None = Field(default=None, description="Anthropic API key")

    # Object Storage (MinIO / S3)
    MINIO_ENDPOINT: str = Field(default="localhost:9000", description="MinIO storage service endpoint")
    MINIO_ACCESS_KEY: str | None = Field(default=None, description="MinIO Access Key")
    MINIO_SECRET_KEY: str | None = Field(default=None, description="MinIO Secret Key")
    MINIO_SECURE: bool = Field(default=False, description="Use HTTPS/SSL for MinIO connection")

    # Email (SMTP & IMAP)
    SMTP_HOST: str = Field(default="localhost", description="SMTP mail server host")
    SMTP_PORT: int = Field(default=587, description="SMTP mail server port")
    SMTP_USER: str | None = Field(default=None, description="SMTP user name")
    SMTP_PASSWORD: str | None = Field(default=None, description="SMTP password")
    IMAP_HOST: str = Field(default="localhost", description="IMAP server host")
    IMAP_PORT: int = Field(default=993, description="IMAP server port")

    # IoT / Telemetry (MQTT)
    MQTT_HOST: str = Field(default="localhost", description="MQTT Broker host")
    MQTT_PORT: int = Field(default=1883, description="MQTT Broker port")
    MQTT_TOPIC: str = Field(default="tu5g/#", description="Default subscription topic for MQTT")

    # CORS and Security
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000,http://localhost:8000",
        description="Comma-separated list of allowed origins for CORS"
    )

    # Cache and Rate Limiting
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")
    RATE_LIMIT: str = Field(default="100/minute", description="Default rate limit rule")

    # Telecom / Sim Defaults
    DEFAULT_MCC: str = Field(default="234", description="Default Mobile Country Code")
    DEFAULT_MNC: str = Field(default="15", description="Default Mobile Network Code")

    @property
    def allowed_origins_list(self) -> List[str]:
        """Parses the comma-separated ALLOWED_ORIGINS string into a list of origins."""
        if not self.ALLOWED_ORIGINS:
            return []
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    # Pydantic Configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached instance of the Settings object to avoid reloading
    and parsing configuration on every request.
    """
    return Settings()
