"""All settings come from environment variables (or a local .env file)."""

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    ai_provider: str
    gemini_api_key: str
    gemini_model: str
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    ai_timeout_seconds: float
    admin_password: str
    database_path: str
    clinic_name: str
    clinic_timezone: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_tls: bool

    @property
    def active_provider(self) -> str:
        """Which AI provider will actually be used: gemini, openai or offline."""
        choice = self.ai_provider.lower()
        if choice == "gemini" and self.gemini_api_key:
            return "gemini"
        if choice == "openai" and self.openai_api_key:
            return "openai"
        if choice == "auto":
            if self.gemini_api_key:
                return "gemini"
            if self.openai_api_key:
                return "openai"
        return "offline"


@lru_cache
def get_settings() -> Settings:
    return Settings(
        ai_provider=os.getenv("AI_PROVIDER", "auto"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
        ai_timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "20")),
        admin_password=os.getenv("ADMIN_PASSWORD", "admin123"),
        database_path=os.getenv("DATABASE_PATH", "data/clinicflow.db"),
        clinic_name=os.getenv("CLINIC_NAME", "Robina 7 Day Doctors"),
        clinic_timezone=os.getenv("CLINIC_TIMEZONE", "Australia/Brisbane"),
        smtp_host=os.getenv("SMTP_HOST", ""),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        smtp_from=os.getenv("SMTP_FROM", ""),
        smtp_tls=os.getenv("SMTP_TLS", "true").lower() != "false",
    )
