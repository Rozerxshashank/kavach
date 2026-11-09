"""Runtime configuration. Reads .env from the project or its parent folder."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]          # saakshi/
BACKEND = ROOT / "backend"
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


@dataclass(frozen=True)
class Settings:
    gnani_api_key: str
    tts_endpoint: str
    asr_endpoint: str
    tts_model: str
    groq_api_key: str
    agent_model: str
    fast_model: str
    signing_key: str
    twilio_sid: str
    twilio_token: str
    twilio_from: str
    public_base_url: str
    data_dir: Path
    web_dist: Path
    env: str
    admin_key: str
    harness_key: str
    shield_url: str
    shield_key: str
    shield_live: bool                    # real calls go through Kavach Shield (when it's configured)

    @property
    def production(self) -> bool:
        return self.env == "production"

    @property
    def telephony(self) -> bool:
        """Real phone calls need a Twilio account and a public URL Twilio can reach."""
        return bool(self.twilio_sid and self.twilio_token and self.twilio_from and self.public_base_url)

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "saakshi.db"


settings = Settings(
    gnani_api_key=_env("GNANI_API_KEY"),
    tts_endpoint=_env("GNANI_TTS_ENDPOINT", "https://api.vachana.ai/api/v1/tts/inference"),
    asr_endpoint=_env("GNANI_ASR_ENDPOINT", "https://api.vachana.ai/stt/v3"),
    tts_model=_env("GNANI_TTS_MODEL", "timbre-v2.5"),
    groq_api_key=_env("GROQ_API_KEY"),
    agent_model=_env("SAAKSHI_AGENT_MODEL", "openai/gpt-oss-120b"),
    fast_model=_env("SAAKSHI_FAST_MODEL", "openai/gpt-oss-20b"),
    signing_key=_env("SAAKSHI_SIGNING_KEY", "saakshi-dev-signing-key-change-me"),
    twilio_sid=_env("TWILIO_ACCOUNT_SID"),
    twilio_token=_env("TWILIO_AUTH_TOKEN"),
    twilio_from=_env("TWILIO_FROM_NUMBER"),
    public_base_url=_env("SAAKSHI_PUBLIC_URL").rstrip("/"),
    data_dir=Path(_env("SAAKSHI_DATA_DIR", str(BACKEND / "data"))),
    web_dist=Path(_env("SAAKSHI_WEB_DIST", str(ROOT / "web" / "dist"))),
    env=_env("SAAKSHI_ENV", "development").lower(),
    admin_key=_env("SAAKSHI_ADMIN_KEY"),
    harness_key=_env("SAAKSHI_HARNESS_KEY"),
    shield_url=_env("KAVACH_SHIELD_URL").rstrip("/"),
    shield_key=_env("KAVACH_SHIELD_KEY"),
    shield_live=_env("SAAKSHI_SHIELD", "on").lower() in ("on", "1", "true", "yes"),
)

DEV_SIGNING_KEY = "saakshi-dev-signing-key-change-me"


def production_problems(s: Settings = settings) -> list[str]:
    """What would make a public deployment unsafe. In production the server refuses to start until this is empty."""
    out = []
    if len(s.signing_key) < 32 or s.signing_key == DEV_SIGNING_KEY:
        out.append("SAAKSHI_SIGNING_KEY must be a random secret of 32+ characters (python -c 'import secrets;print(secrets.token_urlsafe(48))')")
    if len(s.admin_key) < 16:
        out.append("SAAKSHI_ADMIN_KEY must be a random secret of 16+ characters")
    if not s.public_base_url.startswith("https://"):
        out.append("SAAKSHI_PUBLIC_URL must be the public https:// address (WhatsApp links and the microphone need it)")
    if s.harness_key and len(s.harness_key) < 24:
        out.append("SAAKSHI_HARNESS_KEY must be 24+ random characters (or empty to turn the Kavach harness off)")
    if not s.gnani_api_key or not s.groq_api_key:
        out.append("GNANI_API_KEY and GROQ_API_KEY must be set")
    return out


if settings.production and production_problems():
    raise SystemExit("Saakshi will not start in production until these are fixed:\n  - " + "\n  - ".join(production_problems()))
settings.audio_dir.mkdir(parents=True, exist_ok=True)
