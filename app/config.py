"""Central configuration for local and database-backed deployments."""

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = ""
    REDIS_URL: str = ""
    JWT_SECRET: str = ""
    JWT_ACCESS_HOURS: int = 24
    JWT_REFRESH_DAYS: int = 30
    AI_PROVIDER: str = "arvan"
    LMAPI_BASE_URL: str = "https://lmapi.rafiei.co/v1"
    LMAPI_API_KEY: str = ""
    LMAPI_API_KEY_FILE: str = ".lmapi_key"
    MOTION_API_KEY_FILE: str = ".motion_key"
    MOTION_ENABLED: bool = False
    MOTION_PROXY_URL: str = "https://editorgpt-motion-relay.vercel.app/api/motion"
    AI_ADMIN_EMAILS: str = ""
    AI_ADMIN_USER_IDS: str = ""
    AI_PROVIDER_TIMEOUT_SECONDS: int = 300
    AI_TIMEOUT_SECONDS: int = 60
    AI_CORRECTION_TIMEOUT_SECONDS: int = 45
    LLM_PROVIDER: str = "arvan"
    LLM_MODEL: str = "GPT-5.6-Sol"
    # Content Creator can use a dedicated text provider without changing the
    # upload/edit planner used elsewhere in the application.
    CONTENT_LLM_PROVIDER: str = ""
    CORRECTION_PROVIDER: str = ""
    CORRECTION_MODEL: str = ""
    VISION_PROVIDER: str = ""
    VISION_MODEL: str = "GPT-5.6-Sol"
    ARVAN_VISION_MODEL: str = "Gemini-3-Flash-Preview"
    ARVAN_IMAGE_MODEL: str = "Gemini-3.1-Flash-Image-Preview"
    CONTENT_VOICE_PROVIDER: str = "elevenlabs"
    # Per-call Content Creator narration provider. When empty, the legacy
    # CONTENT_VOICE_PROVIDER/TTS_PROVIDER compatibility rules remain active.
    CONTENT_TTS_PROVIDER: str = ""
    TTS_VOICE_ID: str = ""
    # TTS_PROVIDER is deliberately independent of optional image/text providers.
    # Edge TTS works without an API key and is the default in restricted networks.
    TTS_PROVIDER: str = "elevenlabs"
    TTS_VOICE: str = "en-US-GuyNeural"
    TTS_RATE: str = "+0%"
    AZURE_SPEECH_KEY: str = ""
    AZURE_SPEECH_REGION: str = ""
    ARVAN_AI_API_KEY: str = ""
    ARVAN_AI_API_BASE: str = "https://aiapi.rafiei.co/v1"
    ARVAN_AI_MODEL: str = "GPT-5.6-Sol"
    GEMINI_API_KEY: str = ""
    GEMINI_API_BASE: str = "https://generativelanguage.googleapis.com"
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_RELAY_SECRET: str = ""
    VERCEL_AUTOMATION_BYPASS_SECRET: str = ""
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = ""
    OPENAI_BASE_URL: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ELEVENLABS_API_KEY: str = ""
    ELEVENLABS_VOICE_ID: str = ""
    WHISPER_ENABLED: bool = True
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_TIMEOUT_SECONDS: int = 120
    # Media artifacts only: uploads, rendered outputs and editable exports.
    # Job metadata/status is persisted in PostgreSQL.
    JOBS_DIR: str = "/app/job_data"
    # Hosts a Composio download link may point at (suffix match). Anything else is refused.
    CLOUD_DOWNLOAD_HOSTS: str = ".amazonaws.com,.composio.dev"
    # Localization (Persian voice-over) projects; defaults to a "localize_jobs"
    # folder next to JOBS_DIR.
    LOCALIZE_DIR: str = ""
    ASSETS_DIR: str = "assets"
    HEALTH_MIN_DISK_FREE_GB: float = 2.0
    PRESETS_DIR: str = "presets"
    APP_ENV: str = "development"
    CORS_ORIGINS: str = ""
    ALLOWED_HOSTS: str = ""
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    # Visual Composer v2: FFmpeg rough cut + deterministic HyperFrames motion.
    TALKING_HYPERFRAMES_ENABLED: bool = False

    @model_validator(mode="after")
    def enforce_provider_policy(self):
        # Old environment values and saved projects cannot re-enable retired services.
        self.AI_PROVIDER = self.LLM_PROVIDER = self.CONTENT_LLM_PROVIDER = "arvan"
        self.CORRECTION_PROVIDER = self.VISION_PROVIDER = "arvan"
        self.LLM_MODEL = self.CORRECTION_MODEL = self.ARVAN_AI_MODEL
        self.VISION_MODEL = self.ARVAN_VISION_MODEL
        self.TTS_PROVIDER = self.CONTENT_TTS_PROVIDER = self.CONTENT_VOICE_PROVIDER = "elevenlabs"
        return self

    @model_validator(mode="after")
    def validate_production_hosts(self):
        if self.APP_ENV.strip().lower() == "production":
            hosts = [host.strip() for host in self.ALLOWED_HOSTS.split(",") if host.strip()]
            if not hosts:
                raise ValueError("ALLOWED_HOSTS must contain at least one hostname in production")
            for host in hosts:
                # TrustedHostMiddleware expects hostnames, without URL or port syntax.
                if (
                    host == "*"
                    or "*" in host
                    or ":" in host
                    or "/" in host
                    or "@" in host
                    or host.startswith(".")
                    or host.endswith(".")
                ):
                    raise ValueError("ALLOWED_HOSTS must contain exact hostnames without ports in production")
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
