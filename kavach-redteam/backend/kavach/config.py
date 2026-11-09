"""Runtime configuration, loaded once from the project-level .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
# .env can live next to this project or one level up (shared with sibling projects)
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")


@dataclass(frozen=True)
class Settings:
    gnani_api_key: str
    tts_endpoint: str
    asr_endpoint: str
    tts_model: str
    groq_api_key: str
    attacker_model: str
    bot_model: str
    judge_model: str
    shield_model: str
    data_dir: Path
    web_dist: Path
    env: str
    admin_key: str
    signing_key: str
    public_url: str
    saakshi_url: str
    saakshi_harness_key: str
    daily_attacks: int

    @property
    def production(self) -> bool:
        return self.env == "production"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "kavach.db"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


settings = Settings(
    gnani_api_key=_env("GNANI_API_KEY"),
    tts_endpoint=_env("GNANI_TTS_ENDPOINT", "https://api.vachana.ai/api/v1/tts/inference"),
    asr_endpoint=_env("GNANI_ASR_ENDPOINT", "https://api.vachana.ai/stt/v3"),
    tts_model=_env("GNANI_TTS_MODEL", "timbre-v2.5"),
    groq_api_key=_env("GROQ_API_KEY"),
    attacker_model=_env("KAVACH_ATTACKER_MODEL", "openai/gpt-oss-120b"),
    bot_model=_env("KAVACH_BOT_MODEL", "openai/gpt-oss-20b"),
    judge_model=_env("KAVACH_JUDGE_MODEL", "openai/gpt-oss-120b"),
    shield_model=_env("KAVACH_SHIELD_MODEL", "openai/gpt-oss-20b"),
    data_dir=Path(_env("KAVACH_DATA_DIR", str(BACKEND / "data"))),
    web_dist=Path(_env("KAVACH_WEB_DIST", str(ROOT / "web" / "dist"))),
    env=_env("KAVACH_ENV", "development").lower(),
    admin_key=_env("KAVACH_ADMIN_KEY"),
    signing_key=_env("KAVACH_SIGNING_KEY", "kavach-dev-signing-key-change-me"),
    public_url=_env("KAVACH_PUBLIC_URL").rstrip("/"),
    saakshi_url=_env("KAVACH_SAAKSHI_URL", "http://127.0.0.1:8100").rstrip("/"),
    saakshi_harness_key=_env("SAAKSHI_HARNESS_KEY"),
    daily_attacks=int(_env("KAVACH_DAILY_ATTACKS", "40")),
)

DEV_SIGNING_KEY = "kavach-dev-signing-key-change-me"


def production_problems(s: Settings = settings) -> list[str]:
    """What would make a public deployment unsafe. In production the server refuses to start until this is empty."""
    out = []
    if len(s.signing_key) < 32 or s.signing_key == DEV_SIGNING_KEY:
        out.append("KAVACH_SIGNING_KEY must be a random secret of 32+ characters")
    if len(s.admin_key) < 16:
        out.append("KAVACH_ADMIN_KEY must be a random secret of 16+ characters")
    if not s.public_url.startswith("https://"):
        out.append("KAVACH_PUBLIC_URL must be the public https:// address")
    if not s.gnani_api_key or not s.groq_api_key:
        out.append("GNANI_API_KEY and GROQ_API_KEY must be set")
    return out


if settings.production and production_problems():
    raise SystemExit("Kavach will not start in production until these are fixed:\n  - " + "\n  - ".join(production_problems()))
settings.audio_dir.mkdir(parents=True, exist_ok=True)
