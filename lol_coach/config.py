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


def has_credentials() -> bool:
    return any(os.getenv(v) for v in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"))


def save_setting(name: str, value: str, env_file: Path = ENV_FILE) -> None:
    """Guarda (o reemplaza) una variable en el archivo .env."""
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    lines = [line for line in lines if not line.startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value


def first_run_setup() -> bool:
    """Pide la API key la primera vez y la guarda en .env. Devuelve True si hay credenciales."""
    if has_credentials():
        return True
    if not sys.stdin or not sys.stdin.isatty():
        return False
    print("=" * 60)
    print(" Configuración inicial del Coach de LoL")
    print("=" * 60)
    print("Necesitas una API key de Anthropic para que la IA te dé consejos.")
    print("Consíguela en: https://console.anthropic.com/settings/keys\n")
    key = input("Pega tu API key (empieza con sk-ant-) y pulsa Enter: ").strip()
    if not key:
        return False
    save_setting("ANTHROPIC_API_KEY", key)
    print(f"Guardada en {ENV_FILE}\n")
    return True


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
