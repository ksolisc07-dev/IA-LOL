"""Configuración leída de variables de entorno (o de un archivo .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv es opcional
    pass


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


@dataclass
class Config:
    model: str = os.getenv("COACH_MODEL", "claude-opus-5-5")
    # Esfuerzo de razonamiento: "low" en partida para que responda rápido.
    live_effort: str = os.getenv("COACH_LIVE_EFFORT", "low")
    review_effort: str = os.getenv("COACH_REVIEW_EFFORT", "high")
    voice_enabled: bool = _bool("COACH_VOICE", True)
    voice_rate: int = int(os.getenv("COACH_VOICE_RATE", "185"))
    # Cada cuántos segundos de partida pedir una revisión general a la IA.
    review_interval: int = int(os.getenv("COACH_REVIEW_INTERVAL", "240"))
    poll_seconds: float = float(os.getenv("COACH_POLL_SECONDS", "2"))
    riot_api_key: str | None = os.getenv("RIOT_API_KEY")
    riot_platform: str = os.getenv("RIOT_PLATFORM", "la1")
    riot_id: str | None = os.getenv("RIOT_ID")
