"""Perfil de cada campeón (tipo de daño, tanque, curación, asesino) para el modo sin IA.

La tabla viene incluida para funcionar sin internet. Los campeones que no estén en ella
(p. ej. nuevos lanzamientos) se completan desde Data Dragon cuando hay conexión.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import requests

# id de Data Dragon -> "daño [tank] [heal] [assassin]"; daño: ad, ap o mix.
_RAW = """
Aatrox:ad heal|Ahri:ap|Akali:ap assassin|Akshan:ad|Alistar:ap tank|Ambessa:ad heal|Amumu:ap tank|
Anivia:ap|Annie:ap|Aphelios:ad|Ashe:ad|AurelionSol:ap|Aurora:ap|Azir:ap|Bard:ap|Belveth:ad heal|
Blitzcrank:ap tank|Brand:ap|Braum:ad tank|Briar:ad heal|Caitlyn:ad|Camille:ad|Cassiopeia:ap|
Chogath:ap tank|Corki:mix|Darius:ad|Diana:ap assassin|DrMundo:ad tank heal|Draven:ad|
Ekko:ap assassin|Elise:ap|Evelynn:ap assassin|Ezreal:ad|Fiddlesticks:ap heal|Fiora:ad heal|
Fizz:ap assassin|Galio:ap tank|Gangplank:ad|Garen:ad|Gnar:ad tank|Gragas:ap tank|Graves:ad|
Gwen:ap heal|Hecarim:ad|Heimerdinger:ap|Hwei:ap|Illaoi:ad heal|Irelia:ad heal|Ivern:ap|Janna:ap|
JarvanIV:ad|Jax:mix|Jayce:ad|Jhin:ad|Jinx:ad|Kaisa:mix|Kalista:ad|Karma:ap|Karthus:ap|
Kassadin:ap assassin|Katarina:ap assassin|Kayle:mix|Kayn:ad assassin heal|Kennen:ap|
Khazix:ad assassin|Kindred:ad|Kled:ad|KogMaw:mix|KSante:ad tank|Leblanc:ap assassin|LeeSin:ad|
Leona:ap tank|Lillia:ap|Lissandra:ap|Lucian:ad|Lulu:ap|Lux:ap|Malphite:ap tank|Malzahar:ap|
Maokai:ap tank heal|MasterYi:ad heal|Mel:ap|Milio:ap heal|MissFortune:ad|MonkeyKing:ad|
Mordekaiser:ap heal|Morgana:ap|Naafiri:ad assassin|Nami:ap heal|Nasus:ad tank heal|
Nautilus:ap tank|Neeko:ap|Nidalee:ap|Nilah:ad heal|Nocturne:ad|Nunu:ap tank heal|Olaf:ad heal|
Orianna:ap|Ornn:ap tank|Pantheon:ad|Poppy:ad tank|Pyke:ad assassin|Qiyana:ad assassin|Quinn:ad|
Rakan:ap|Rammus:ap tank|RekSai:ad|Rell:ap tank|Renata:ap|Renekton:ad heal|Rengar:ad assassin|
Riven:ad|Rumble:ap|Ryze:ap|Samira:ad heal|Sejuani:ap tank|Senna:ad heal|Seraphine:ap heal|
Sett:ad|Shaco:ad assassin|Shen:ap tank|Shyvana:mix|Singed:ap tank|Sion:ad tank|Sivir:ad|
Skarner:ad tank|Smolder:ad|Sona:ap heal|Soraka:ap heal|Swain:ap heal|Sylas:ap heal|Syndra:ap|
TahmKench:ap tank|Taliyah:ap|Talon:ad assassin|Taric:ap tank heal|Teemo:ap|Thresh:ap tank|
Tristana:ad|Trundle:ad heal|Tryndamere:ad heal|TwistedFate:ap|Twitch:ad|Udyr:ad|Urgot:ad|Varus:ad|
Vayne:ad|Veigar:ap|Velkoz:ap|Vex:ap|Vi:ad|Viego:ad heal|Viktor:ap|Vladimir:ap heal|
Volibear:mix tank heal|Warwick:ad heal|Xayah:ad|Xerath:ap|XinZhao:ad|Yasuo:ad|Yone:ad|Yorick:ad|
Yunara:ad|Yuumi:ap heal|Zac:ap tank heal|Zed:ad assassin|Zeri:ad|Ziggs:ap|Zilean:ap|Zoe:ap|Zyra:ap
"""

ALIASES = {"wukong": "monkeyking", "nunuwillump": "nunu", "renataglasc": "renata"}


@dataclass(frozen=True)
class ChampionProfile:
    damage: str  # "ad", "ap" o "mix"
    tank: bool = False
    heal: bool = False
    assassin: bool = False

    @property
    def ap_share(self) -> float:
        return {"ap": 1.0, "ad": 0.0}.get(self.damage, 0.5)


def normalize(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", name.lower())
    return ALIASES.get(key, key)


def _parse(raw: str) -> dict[str, ChampionProfile]:
    table = {}
    for entry in raw.replace("\n", "").split("|"):
        champ, spec = entry.split(":")
        words = spec.split()
        table[normalize(champ)] = ChampionProfile(
            damage=words[0], tank="tank" in words, heal="heal" in words, assassin="assassin" in words
        )
    return table


PROFILES = _parse(_RAW)
_ddragon_loaded = False


def _load_ddragon() -> None:
    """Añade campeones que no estén en la tabla usando Data Dragon (si hay internet)."""
    global _ddragon_loaded
    _ddragon_loaded = True
    try:
        version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=5).json()[0]
        data = requests.get(
            f"https://ddragon.leagueoflegends.com/cdn/{version}/data/es_MX/champion.json", timeout=5
        ).json()["data"]
    except (requests.RequestException, ValueError, KeyError, IndexError):
        return
    for champ_id, champ in data.items():
        key = normalize(champ_id)
        if key in PROFILES:
            continue
        attack, magic = champ["info"]["attack"], champ["info"]["magic"]
        damage = "ap" if magic > attack + 2 else "ad" if attack > magic + 2 else "mix"
        PROFILES[key] = ChampionProfile(damage, tank="Tank" in champ["tags"][:1],
                                        assassin="Assassin" in champ["tags"][:1])
        PROFILES[normalize(champ["name"])] = PROFILES[key]


def profile(*names: str) -> ChampionProfile:
    """Busca por id interno o nombre visible; si no lo encuentra, asume daño mixto."""
    for attempt in range(2):
        for name in names:
            if name and normalize(name) in PROFILES:
                return PROFILES[normalize(name)]
        if attempt == 0 and not _ddragon_loaded:
            _load_ddragon()
        else:
            break
    return ChampionProfile("mix")
