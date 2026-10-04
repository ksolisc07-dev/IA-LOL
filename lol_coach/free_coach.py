"""Coach gratuito basado en reglas: consejos de build y de errores sin usar IA."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from lol_coach.champions import profile
from lol_coach.game_state import GameSnapshot, PlayerState

# id de objeto -> nombre en español (se actualiza con Data Dragon si hay internet).
ITEM_NAMES = {
    3111: "Botas de mercurio", 3047: "Botas de acero reforzado", 3156: "Fauces de Malmortius",
    3102: "Velo de la Banshee", 3157: "Reloj de arena de Zhonya", 4401: "Fuerza de la naturaleza",
    3065: "Semblante espiritual", 3075: "Cota de espinas", 3076: "Chaleco de zarzas",
    3033: "Recordatorio mortal", 3165: "Morellonomicón", 3916: "Orbe del olvido",
    3123: "Llamado del verdugo", 3036: "Saludos de Lord Dominik", 3135: "Bastón del vacío",
    3026: "Ángel de la guarda", 3143: "Presagio de Randuin", 3110: "Corazón de hielo",
    3053: "Gaje de Sterak", 3071: "Cuchilla negra", 6333: "Danza de la muerte", 3814: "Filo de la noche",
    3139: "Cimitarra mercurial", 2504: "Rookern de Kaenic", 8020: "Máscara abisal",
    3222: "Bendición de Mikael", 6609: "Motosierra quimpunk",
}
_items_loaded = False

BUILD_WORDS = ("arm", "build", "objeto", "item", "compr", "build", "botas")


def item_name(item_id: int) -> str:
    global _items_loaded
    if not _items_loaded:
        _items_loaded = True
        try:
            version = requests.get("https://ddragon.leagueoflegends.com/api/versions.json", timeout=5).json()[0]
            data = requests.get(
                f"https://ddragon.leagueoflegends.com/cdn/{version}/data/es_MX/item.json", timeout=5
            ).json()["data"]
            for key in ITEM_NAMES:
                if str(key) in data:
                    ITEM_NAMES[key] = data[str(key)]["name"]
        except (requests.RequestException, ValueError, KeyError, IndexError):
            pass
    return ITEM_NAMES.get(item_id, str(item_id))


def _champ_profile(p: PlayerState):
    return profile(p.champion_id, p.champion)


@dataclass
class EnemyComp:
    ap_share: float
    healers: list[str]
    tanks: list[str]
    assassins: list[str]

    @property
    def heavy_ap(self) -> bool:
        return self.ap_share >= 0.6

    @property
    def heavy_ad(self) -> bool:
        return self.ap_share <= 0.35

    def describe(self, enemies: list[PlayerState]) -> str:
        parts = []
        if self.heavy_ap:
            aps = [e.champion for e in enemies if _champ_profile(e).damage == "ap"]
            parts.append(f"mucho daño mágico ({', '.join(aps)})")
        elif self.heavy_ad:
            ads = [e.champion for e in enemies if _champ_profile(e).damage == "ad"]
            parts.append(f"mucho daño físico ({', '.join(ads)})")
        else:
            parts.append("daño mixto")
        if self.healers:
            parts.append(f"curación ({', '.join(self.healers)})")
        if len(self.tanks) >= 2:
            parts.append(f"tanques ({', '.join(self.tanks)})")
        if len(self.assassins) >= 2:
            parts.append(f"asesinos ({', '.join(self.assassins)})")
        return ", ".join(parts)


def analyze_enemies(enemies: list[PlayerState]) -> EnemyComp:
    profiles = [(e, _champ_profile(e)) for e in enemies]
    ap = sum(p.ap_share for _, p in profiles) / max(len(profiles), 1)
    return EnemyComp(
        ap_share=ap,
        healers=[e.champion for e, p in profiles if p.heal],
        tanks=[e.champion for e, p in profiles if p.tank],
        assassins=[e.champion for e, p in profiles if p.assassin],
    )


def my_kind(snap: GameSnapshot) -> str:
    prof = _champ_profile(snap.me)
    if prof.tank:
        return "tank"
    if snap.me.position == "UTILITY" and prof.damage == "ap":
        return "support"
    if snap.me.position == "BOTTOM" and prof.damage != "ap":
        return "adc"
    return "ap" if prof.damage == "ap" else "ad"


# (tipo de mi campeón) -> amenaza -> [(id objeto, motivo)]
RECOMMENDATIONS = {
    "antiheal": {"adc": 3033, "ad": 3123, "ap": 3165, "tank": 3075, "support": 3916},
    "tanks": {"adc": 3036, "ad": 3071, "ap": 3135},
    "ap": {"adc": 3156, "ad": 3156, "ap": 3102, "tank": 4401, "support": 3222},
    "ad": {"adc": 3026, "ad": 6333, "ap": 3157, "tank": 3143, "support": 3222},
    "assassins": {"adc": 3026, "ad": 3814, "ap": 3157, "tank": 3110},
}


def build_recommendations(snap: GameSnapshot, limit: int = 3) -> tuple[EnemyComp, list[tuple[str, str]]]:
    comp = analyze_enemies(snap.enemies)
    kind = my_kind(snap)
    owned = {name.lower() for name in snap.me.items}
    picks: list[tuple[int, str]] = []

    has_boots = any("bota" in n or "grebas" in n or "boots" in n for n in owned)
    if not has_boots or snap.minutes < 2:
        if comp.heavy_ap and kind != "adc":
            picks.append((3111, "por su daño mágico y control"))
        elif comp.heavy_ad and kind in ("ad", "tank", "support"):
            picks.append((3047, "por su daño físico de ataques básicos"))

    threats = []
    if comp.healers:
        threats.append(("antiheal", f"porque {' y '.join(comp.healers[:2])} se curan"))
    if len(comp.tanks) >= 2 and kind in ("adc", "ad", "ap"):
        threats.append(("tanks", f"para atravesar a {' y '.join(comp.tanks[:2])}"))
    if comp.heavy_ap:
        threats.append(("ap", "para sobrevivir al daño mágico"))
    elif comp.heavy_ad:
        threats.append(("ad", "para sobrevivir al daño físico"))
    if len(comp.assassins) >= 2:
        threats.append(("assassins", f"contra los asesinos {' y '.join(comp.assassins[:2])}"))

    for threat, reason in threats:
        item_id = RECOMMENDATIONS[threat].get(kind)
        if item_id and all(item_id != i for i, _ in picks):
            picks.append((item_id, reason))

    result = [(item_name(i), reason) for i, reason in picks if item_name(i).lower() not in owned]
    return comp, result[:limit]


def build_advice(snap: GameSnapshot) -> str:
    comp, recs = build_recommendations(snap)
    text = f"El equipo enemigo tiene {comp.describe(snap.enemies)}."
    if recs:
        text += " Te conviene armar: " + "; ".join(f"{name}, {reason}" for name, reason in recs) + "."
    else:
        text += " Tu build actual ya cubre lo principal; sigue con tus objetos de daño."
    return text


def game_plan(snap: GameSnapshot) -> str:
    opp = snap.lane_opponent
    text = ""
    if opp:
        prof = _champ_profile(opp)
        style = {"ap": "daño mágico", "ad": "daño físico"}.get(prof.damage, "daño mixto")
        text = f"Tu rival de línea es {opp.champion}, hace {style}. "
        if prof.assassin:
            text += "Es un asesino: respeta su nivel 6 y no te quedes con poca vida. "
    return text + build_advice(snap)


def death_advice(snap: GameSnapshot) -> str:
    death = next(
        (e for e in reversed(snap.events)
         if e.get("EventName") == "ChampionKill" and e.get("VictimName") in snap.me.aliases),
        None,
    )
    tips = []
    if death:
        killer = snap.player_by_alias(death.get("KillerName", ""))
        helpers = len(death.get("Assisters", []))
        opp = snap.lane_opponent
        if killer is None:
            tips.append("Te mató una torre o un súbdito: no te quedes bajo torre enemiga con poca vida.")
        elif helpers >= 2:
            tips.append(f"Te atraparon entre {helpers + 1}. No avances sin visión ni lejos de tu equipo.")
        elif killer.position == "JUNGLE" and snap.me.position != "JUNGLE":
            tips.append(f"Te emboscó el jungla {killer.champion}. Coloca un guardián en el río y, "
                        "si no lo ves en el mapa, juega pegado a tu torre.")
        elif opp is not None and killer is opp:
            if opp.level > snap.me.level or opp.cs > snap.me.cs + 15:
                tips.append(f"{opp.champion} va por delante de ti. Deja de pelear con él, "
                            "farmea seguro y pide ayuda a tu jungla.")
            else:
                tips.append(f"Perdiste el duelo contra {opp.champion}. Pelea cuando él haya gastado "
                            "sus habilidades principales, no antes.")
        else:
            tips.append(f"Te mató {killer.champion}. Mira el minimapa antes de avanzar.")
    if snap.current_gold >= 900:
        _, recs = build_recommendations(snap, limit=1)
        if recs:
            tips.append(f"Con tu oro, avanza hacia {recs[0][0]}, {recs[0][1]}.")
    return " ".join(tips)


def answer(snap: GameSnapshot | None, question: str) -> str:
    q = question.lower()
    if snap is not None and any(w in q for w in BUILD_WORDS):
        return build_advice(snap)
    return ("En el modo gratuito solo puedo responder qué armarte. Para preguntas libres activa la IA "
            "con tu suscripción de Claude; mira el archivo README.")


def advice(snap: GameSnapshot, reason: str) -> str:
    if reason == "inicio":
        return game_plan(snap)
    if reason == "muerte":
        return death_advice(snap)
    return ""  # Las revisiones periódicas ya las cubren las alertas automáticas.
