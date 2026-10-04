"""Resúmenes de partidas terminadas para el análisis de la IA."""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.game_state import ROLE_NAMES, GameSnapshot, describe_event


def summarize_match(match: dict, puuid: str, items: dict[int, str] | None = None) -> dict:
    """Extrae las estadísticas relevantes de un jugador en un partido de Match-V5."""
    info = match["info"]
    items = items or {}
    me = next(p for p in info["participants"] if p["puuid"] == puuid)
    minutes = max(info["gameDuration"] / 60, 1)
    team = [p for p in info["participants"] if p["teamId"] == me["teamId"]]
    team_kills = sum(p["kills"] for p in team) or 1
    team_damage = sum(p["totalDamageDealtToChampions"] for p in team) or 1
    cs = me["totalMinionsKilled"] + me["neutralMinionsKilled"]
    opponent = next(
        (p for p in info["participants"]
         if p["teamId"] != me["teamId"] and p.get("teamPosition") and p["teamPosition"] == me.get("teamPosition")),
        None,
    )
    challenges = me.get("challenges", {})
    summary = {
        "campeon": me["championName"],
        "rol": ROLE_NAMES.get(me.get("teamPosition", ""), me.get("teamPosition", "")),
        "resultado": "Victoria" if me["win"] else "Derrota",
        "duracion_min": round(minutes, 1),
        "kda": f"{me['kills']}/{me['deaths']}/{me['assists']}",
        "cs": cs,
        "cs_min": round(cs / minutes, 1),
        "oro_min": round(me["goldEarned"] / minutes),
        "participacion_asesinatos": f"{(me['kills'] + me['assists']) / team_kills:.0%}",
        "porcentaje_dano_equipo": f"{me['totalDamageDealtToChampions'] / team_damage:.0%}",
        "vision": me["visionScore"],
        "vision_min": round(me["visionScore"] / minutes, 2),
        "guardianes_control": me.get("visionWardsBoughtInGame", 0),
        "objetos": [items.get(me[f"item{i}"], str(me[f"item{i}"])) for i in range(6) if me[f"item{i}"]],
        "cs_10min_linea": challenges.get("laneMinionsFirst10Minutes"),
        "max_ventaja_cs_rival": challenges.get("maxCsAdvantageOnLaneOpponent"),
        "asesinatos_en_solitario": challenges.get("soloKills"),
    }
    if opponent:
        summary["rival"] = {
            "campeon": opponent["championName"],
            "kda": f"{opponent['kills']}/{opponent['deaths']}/{opponent['assists']}",
            "cs": opponent["totalMinionsKilled"] + opponent["neutralMinionsKilled"],
            "diferencia_oro": me["goldEarned"] - opponent["goldEarned"],
        }
    enemies = [p["championName"] for p in info["participants"] if p["teamId"] != me["teamId"]]
    summary["equipo_enemigo"] = enemies
    return {k: v for k, v in summary.items() if v is not None}


def format_matches(summaries: list[dict]) -> str:
    lines = []
    for i, s in enumerate(summaries, 1):
        lines.append(f"Partida {i}:")
        lines += [f"  {k}: {v}" for k, v in s.items()]
    return "\n".join(lines)


@dataclass
class LiveGameLog:
    """Guarda la evolución de una partida en vivo para el resumen final."""

    rows: list[str] = field(default_factory=list)
    last_snapshot: GameSnapshot | None = None
    _last_minute: int = -1

    def record(self, snap: GameSnapshot) -> None:
        self.last_snapshot = snap
        minute = int(snap.minutes)
        if minute != self._last_minute:
            self._last_minute = minute
            opp = snap.lane_opponent
            vs = f" | rival {opp.champion} nv{opp.level} {opp.cs}CS {opp.kda}" if opp else ""
            self.rows.append(
                f"min {minute}: nv{snap.me.level} {snap.me.kda} {snap.me.cs}CS "
                f"visión {snap.me.ward_score:.0f} oro {snap.current_gold:.0f}{vs}"
            )

    def summary(self) -> str:
        snap = self.last_snapshot
        if snap is None:
            return ""
        key_events = [
            describe_event(e, snap) for e in snap.events
            if e.get("EventName") in {"ChampionKill", "DragonKill", "BaronKill", "HeraldKill", "TurretKilled"}
        ]
        return "\n".join([
            f"Campeón: {snap.me.champion} ({snap.me.role})",
            f"Objetos finales: {', '.join(snap.me.items)}",
            f"Enemigos: {', '.join(f'{p.champion} ({p.role})' for p in snap.enemies)}",
            "Evolución:",
            *self.rows,
            "Eventos clave:",
            *key_events[-40:],
        ])
