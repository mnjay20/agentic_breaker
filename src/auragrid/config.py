import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Security config
    agent_token: str = "secure_agent_token_123"

    # Watchdog config
    watchdog_interval_s: int = 10
    watchdog_timeout_s: int = 30

    # Decision config
    cascade_risk_threshold: float = 0.65
    max_shed_fraction: float = 0.30
    shed_penalty: float = 1e5
    switch_penalty: float = 1e2
    horizon_steps: int = 4  # e.g., 4 steps matching peak window
    system_inertia: float = 5.0  # inertia constant H_sys

    # Paths
    data_dir: str = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "data"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# Singleton settings instance
settings = Settings()
