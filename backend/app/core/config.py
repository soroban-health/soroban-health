"""App configuration, loaded from environment variables / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Soroban RPC
    SOROBAN_RPC_URL: str = "https://soroban-testnet.stellar.org"
    SOROBAN_NETWORK_PASSPHRASE: str = "Test SDF Network ; September 2015"

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]


settings = Settings()
