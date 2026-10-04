"""Cliente para la Live Client Data API que expone el juego en localhost:2999.

Riot la ofrece oficialmente mientras hay una partida en curso; no requiere API key
y es la misma fuente que usan las apps de overlay. Solo lee datos que el jugador
ya ve en pantalla (marcador, objetos, eventos), por lo que no automatiza nada.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LIVE_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"


class GameNotRunning(Exception):
    """No hay partida en curso (o todavía está en la pantalla de carga)."""


class LiveClient:
    def __init__(self, url: str = LIVE_URL, timeout: float = 2.0):
        self.url = url
        self.timeout = timeout
        self.session = requests.Session()

    def fetch(self) -> dict:
        try:
            # El juego usa un certificado autofirmado de Riot.
            resp = self.session.get(self.url, timeout=self.timeout, verify=False)
        except requests.RequestException as exc:
            raise GameNotRunning(str(exc)) from exc
        if resp.status_code != 200:
            raise GameNotRunning(f"HTTP {resp.status_code}")
        data = resp.json()
        if "activePlayer" not in data or "error" in data.get("activePlayer", {}):
            # Pantalla de carga o modo espectador.
            raise GameNotRunning("datos de partida incompletos")
        return data


class FileClient:
    """Devuelve un JSON guardado; útil para la demo y las pruebas."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))
