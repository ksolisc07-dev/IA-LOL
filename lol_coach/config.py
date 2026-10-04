"""Configuración leída de variables de entorno (o de un archivo .env)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def app_dir() -> Path:
    """Carpeta del programa: junto al .exe si está empaquetado, si no la carpeta actual."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


ENV_FILE = app_dir() / ".env"

try:
    from dotenv import load_dotenv

    load_dotenv(ENV_FILE)
except ImportError:  # python-dotenv es opcional
    pass


def save_setting(name: str, value: str, env_file: Path = ENV_FILE) -> None:
    """Guarda (o reemplaza) una variable en el archivo .env."""
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


@dataclass
class Config:
    # auto: usa la IA si está disponible (API key o Claude Code), si no, el modo gratuito.
    # gratis: nunca usa IA. suscripcion: solo Claude Code. api: solo API key.
    mode: str = os.getenv("COACH_MODO", "auto")
    # Modelo al usar tu suscripción vía Claude Code: "sonnet" (rápido) u "opus".
    subscription_model: str = os.getenv("COACH_MODELO_SUSCRIPCION", "sonnet")
    # Modelo al usar una API key de pago.
    model: str = os.getenv("COACH_MODEL", "claude-opus-5-5")
    # Esfuerzo de razonamiento: "low" en partida para que responda rápido.
    live_effort: str = os.getenv("COACH_LIVE_EFFORT", "low")
    review_effort: str = os.getenv("COACH_REVIEW_EFFORT", "high")
    # Que la IA vea capturas de tu pantalla durante la partida (solo con IA activada).
    vision: bool = _bool("COACH_VISION", True)
    # Monitor a capturar (1 = principal).
    monitor: int = int(os.getenv("COACH_MONITOR", "1"))
    voice_enabled: bool = _bool("COACH_VOICE", True)
    voice_rate: int = int(os.getenv("COACH_VOICE_RATE", "185"))
    # Cada cuántos segundos de partida pedir una revisión general a la IA.
    review_interval: int = int(os.getenv("COACH_REVIEW_INTERVAL", "240"))
    poll_seconds: float = float(os.getenv("COACH_POLL_SECONDS", "2"))
    riot_api_key: str | None = os.getenv("RIOT_API_KEY")
    riot_platform: str = os.getenv("RIOT_PLATFORM", "la1")
    riot_id: str | None = os.getenv("RIOT_ID")
