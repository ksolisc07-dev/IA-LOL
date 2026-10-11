"""Nombres oficiales de los objetos en español de Latinoamérica (Data Dragon, es_MX).

El juego entrega los nombres en el idioma de tu cliente y la IA a veces los dice en
inglés o en español de España; con esta lista ambos usan los nombres oficiales de LAN/LAS.
Se descarga una vez y se guarda en caché para funcionar también sin internet.
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

LANGUAGE = "es_MX"
SUMMONERS_RIFT = "11"

_items: dict[int, dict] = {}
_loaded = False


def _cache_file() -> Path:
    from lol_coach.config import app_dir

    return app_dir() / "cache" / f"items_{LANGUAGE}.json"


def _load() -> None:
    global _loaded, _items
    _loaded = True
    cache = _cache_file()
    data = None
    try:
        version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=5).json()[0]
        cached = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        if cached.get("version") == version:
            data = cached["data"]
        else:
            data = requests.get(
                f"https://ddragon.leagueoflegends.com/cdn/{version}/data/{LANGUAGE}/item.json", timeout=10
            ).json()["data"]
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"version": version, "data": data}, ensure_ascii=False), encoding="utf-8")
    except (requests.RequestException, ValueError, KeyError, IndexError, OSError):
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))["data"]
        except (OSError, ValueError, KeyError):
            data = None
    if data:
        _items = {int(k): v for k, v in data.items() if k.isdigit()}


def name(item_id: int | None, fallback: str = "") -> str:
    """Nombre oficial en español latino; si no hay datos, el nombre que dio el juego."""
    if not _loaded:
        _load()
    item = _items.get(int(item_id)) if item_id is not None else None
    return item["name"] if item else (fallback or str(item_id))


def catalog() -> list[str]:
    """Objetos completos y botas disponibles en la Grieta, para que la IA use sus nombres exactos."""
    if not _loaded:
        _load()
    names = set()
    for item in _items.values():
        gold = item.get("gold", {})
        if not gold.get("purchasable") or not item.get("maps", {}).get(SUMMONERS_RIFT):
            continue
        tags = item.get("tags", [])
        final = not item.get("into") and gold.get("total", 0) >= 2000
        boots = "Boots" in tags and gold.get("total", 0) >= 900
        if final or boots or "Trinket" in tags:
            names.add(item["name"])
    return sorted(names)
