"""Cliente mínimo de la API de Riot para analizar partidas ya jugadas."""

from __future__ import annotations

import time

import requests

PLATFORM_TO_REGION = {
    "na1": "americas", "br1": "americas", "la1": "americas", "la2": "americas",
    "euw1": "europe", "eun1": "europe", "tr1": "europe", "ru": "europe", "me1": "europe",
    "kr": "asia", "jp1": "asia",
    "oc1": "sea", "ph2": "sea", "sg2": "sea", "th2": "sea", "tw2": "sea", "vn2": "sea",
}
# Nombres comunes que la gente escribe -> código de plataforma de Riot.
PLATFORM_ALIASES = {
    "lan": "la1", "las": "la2", "na": "na1", "br": "br1", "euw": "euw1", "eune": "eun1",
    "tr": "tr1", "me": "me1", "jp": "jp1", "oce": "oc1", "oc": "oc1", "ph": "ph2", "sg": "sg2",
    "th": "th2", "tw": "tw2", "vn": "vn2",
}
RANKED_SOLO_QUEUE = 420


def normalize_platform(platform: str) -> str:
    platform = platform.strip().lower()
    return PLATFORM_ALIASES.get(platform, platform)


class RiotAPIError(Exception):
    pass


class RiotClient:
    def __init__(self, api_key: str, platform: str = "la1"):
        platform = normalize_platform(platform)
        if platform not in PLATFORM_TO_REGION:
            raise RiotAPIError(f"Servidor desconocido '{platform}'. Usa por ejemplo: lan, las, na, euw, br, kr.")
        self.region = PLATFORM_TO_REGION[platform]
        # La API de cuentas no está en "sea"; cualquier región de cuentas sirve para cualquier jugador.
        self.account_region = "asia" if self.region == "sea" else self.region
        self.session = requests.Session()
        self.session.headers["X-Riot-Token"] = api_key

    def _get(self, url: str, params: dict | None = None, retries: int = 3):
        for _ in range(retries):
            try:
                resp = self.session.get(url, params=params, timeout=15)
            except requests.RequestException as exc:
                raise RiotAPIError(f"No se pudo conectar con Riot: {exc}") from exc
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", "5")))
                continue
            if resp.status_code in (401, 403):
                raise RiotAPIError("API key de Riot inválida o expirada (las de desarrollo caducan cada 24 h).")
            if resp.status_code == 404:
                raise RiotAPIError(f"No encontrado: {url}")
            resp.raise_for_status()
            return resp.json()
        raise RiotAPIError("Límite de peticiones de Riot superado; inténtalo en un momento.")

    def puuid(self, riot_id: str) -> str:
        if "#" not in riot_id:
            raise RiotAPIError("El Riot ID debe tener el formato Nombre#TAG")
        name, tag = (part.strip() for part in riot_id.rsplit("#", 1))
        url = (f"https://{self.account_region}.api.riotgames.com/riot/account/v1/accounts/"
               f"by-riot-id/{requests.utils.quote(name)}/{requests.utils.quote(tag)}")
        try:
            return self._get(url)["puuid"]
        except RiotAPIError as exc:
            if "No encontrado" in str(exc):
                raise RiotAPIError(f"No existe el jugador {name}#{tag}. Revisa nombre y TAG.") from None
            raise

    def match_ids(self, puuid: str, count: int = 10, queue: int = RANKED_SOLO_QUEUE) -> list[str]:
        url = f"https://{self.region}.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return self._get(url, params={"queue": queue, "count": count})

    def match(self, match_id: str) -> dict:
        return self._get(f"https://{self.region}.api.riotgames.com/lol/match/v5/matches/{match_id}")


def item_names(language: str = "es_MX") -> dict[int, str]:
    """Nombres de objetos desde Data Dragon (sin API key). Vacío si falla."""
    try:
        version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=10).json()[0]
        data = requests.get(
            f"https://ddragon.leagueoflegends.com/cdn/{version}/data/{language}/item.json", timeout=10
        ).json()["data"]
        return {int(k): v["name"] for k, v in data.items()}
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return {}
