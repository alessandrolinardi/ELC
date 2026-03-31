"""Environment variable configuration using Pydantic Settings."""
import os
from functools import lru_cache
from pydantic import ConfigDict
from pydantic_settings import BaseSettings

APP_VERSION = "3.0.0"


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env")

    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""

    # External APIs
    anthropic_api_key: str = ""
    google_address_validation_api_key: str = ""
    zapier_webhook_url: str = ""
    pickup_webhook_url: str = ""
    pickup_webhook_secret: str = ""
    rates_webhook_url: str = ""
    rates_webhook_secret: str = ""

    # Support (Crisp → Zapier → Trello)
    support_zapier_url: str = ""

    # App
    bypass_pin: str = ""
    frontend_url: str = "http://localhost:5173"

    # Job store
    job_ttl_seconds: int = 3600  # 1 hour
    job_cleanup_interval_seconds: int = 600  # 10 minutes
    max_concurrent_jobs: int = 50

    # File limits
    max_file_size_mb: int = 50
    max_pdf_pages: int = 500
    max_excel_rows: int = 1000


@lru_cache
def get_settings() -> Settings:
    return Settings()
