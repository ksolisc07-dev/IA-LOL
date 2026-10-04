"""Convierte el JSON de la Live Client Data API en estructuras fáciles de usar."""

from __future__ import annotations

from dataclasses import dataclass, field

ROLE_NAMES = {
    "TOP": "top",
    "JUNGLE": "jungla",
    "MIDDLE": "mid",
    "BOTTOM": "ADC",
    "UTILITY": "support",
}


@dataclass
class PlayerState:
    name: str
    champion: str
    team: str
    position: str
    level: int
    kills: int
    deaths: int
    assists: int
    cs: int
    ward_score: float
    items: list[str]
    is_dead: bool
    respawn_timer: float
    aliases: set[str] = field(default_factory=set)
    champion_id: str = ""  # id interno (p. ej. "MonkeyKing" para Wukong)

    @property
    def role(self) -> str:
        return ROLE_NAMES.get(self.position, self.position.lower() or "desconocido")

    @property
    def kda(self) -> str:
        return f"{self.kills}/{self.deaths}/{self.assists}"


@dataclass
class GameSnapshot:
    game_time: float
    game_mode: str
    me: PlayerState
    current_gold: float
    stats: dict
    allies: list[PlayerState]
    enemies: list[PlayerState]
    events: list[dict]

    @property
    def minutes(self) -> float:
        return self.game_time / 60

    @property
    def clock(self) -> str:
        total = int(self.game_time)
        return f"{total // 60:02d}:{total % 60:02d}"

    @property
    def lane_opponent(self) -> PlayerState | None:
        if not self.me.position:
            return None
        for enemy in self.enemies:
            if enemy.position == self.me.position:
                return enemy
        return None

    def team_kills(self, players: list[PlayerState]) -> int:
        return sum(p.kills for p in players)

    def player_by_alias(self, alias: str) -> PlayerState | None:
        for player in [*self.allies, *self.enemies]:
            if alias in player.aliases:
                return player
        return None

    def to_prompt(self) -> str:
        """Resumen compacto de la partida para enviarle a la IA."""
        lines = [
            f"Minuto de juego: {self.clock} (modo {self.game_mode})",
            f"Yo: {self.me.champion} ({self.me.role}), nivel {self.me.level}, "
            f"KDA {self.me.kda}, {self.me.cs} CS ({self._cs_min(self.me):.1f}/min), "
            f"puntuación de visión {self.me.ward_score:.0f}, oro sin gastar {self.current_gold:.0f}"
            + (f", MUERTO (reaparece en {self.me.respawn_timer:.0f}s)" if self.me.is_dead else ""),
            f"Mis objetos: {', '.join(self.me.items) or 'ninguno'}",
        ]
        if self.stats:
            keys = ["attackDamage", "abilityPower", "armor", "magicResist", "maxHealth", "attackSpeed"]
            stats = ", ".join(
                f"{k}={self.stats[k]:.2f}" if k == "attackSpeed" else f"{k}={self.stats[k]:.0f}"
                for k in keys
                if isinstance(self.stats.get(k), (int, float))
            )
            lines.append(f"Mis estadísticas: {stats}")
        opp = self.lane_opponent
        if opp:
            lines.append(
                f"Rival de línea: {opp.champion}, nivel {opp.level}, KDA {opp.kda}, {opp.cs} CS, "
                f"objetos: {', '.join(opp.items) or 'ninguno'}"
            )
        lines.append(
            f"Marcador de asesinatos: mi equipo {self.team_kills(self.allies)} - "
            f"{self.team_kills(self.enemies)} enemigo"
        )
        lines.append("Aliados:")
        lines += [self._player_line(p) for p in self.allies if p is not self.me]
        lines.append("Enemigos:")
        lines += [self._player_line(p) for p in self.enemies]
        recent = [e for e in self.events if e.get("EventTime", 0) >= self.game_time - 180]
        if recent:
            lines.append("Eventos de los últimos 3 minutos:")
            lines += [f"  {describe_event(e, self)}" for e in recent[-12:]]
        return "\n".join(lines)

    def _cs_min(self, player: PlayerState) -> float:
        return player.cs / self.minutes if self.minutes > 0 else 0.0

    @staticmethod
    def _player_line(p: PlayerState) -> str:
        dead = " [muerto]" if p.is_dead else ""
        return (
            f"  {p.champion} ({p.role}) nv{p.level} {p.kda} {p.cs}CS{dead} - "
            f"objetos: {', '.join(p.items) or 'ninguno'}"
        )


def _aliases(raw: dict) -> set[str]:
    names = {raw.get("riotId"), raw.get("riotIdGameName"), raw.get("summonerName")}
    riot_id = raw.get("riotId") or ""
    if "#" in riot_id:
        names.add(riot_id.split("#", 1)[0])
    return {n for n in names if n}


def _parse_player(raw: dict) -> PlayerState:
    scores = raw.get("scores", {})
    items = sorted(raw.get("items", []), key=lambda i: i.get("slot", 0))
    return PlayerState(
        name=raw.get("riotId") or raw.get("summonerName") or "?",
        champion=raw.get("championName", "?"),
        team=raw.get("team", "?"),
        position=raw.get("position", "") or "",
        level=int(raw.get("level", 1)),
        kills=int(scores.get("kills", 0)),
        deaths=int(scores.get("deaths", 0)),
        assists=int(scores.get("assists", 0)),
        cs=int(scores.get("creepScore", 0)),
        ward_score=float(scores.get("wardScore", 0.0)),
        items=[i.get("displayName", str(i.get("itemID"))) for i in items],
        is_dead=bool(raw.get("isDead", False)),
        respawn_timer=float(raw.get("respawnTimer", 0.0)),
        aliases=_aliases(raw),
        champion_id=(raw.get("rawChampionName") or "").rsplit("_", 1)[-1],
    )


def parse_snapshot(data: dict) -> GameSnapshot:
    active = data["activePlayer"]
    my_aliases = _aliases(active)
    players = [_parse_player(p) for p in data.get("allPlayers", [])]
    me = next((p for p in players if p.aliases & my_aliases), None)
    if me is None:
        raise ValueError("No se encontró al jugador activo en la lista de jugadores")
    allies = [p for p in players if p.team == me.team]
    enemies = [p for p in players if p.team != me.team]
    return GameSnapshot(
        game_time=float(data.get("gameData", {}).get("gameTime", 0.0)),
        game_mode=data.get("gameData", {}).get("gameMode", "?"),
        me=me,
        current_gold=float(active.get("currentGold", 0.0)),
        stats=active.get("championStats", {}),
        allies=allies,
        enemies=enemies,
        events=data.get("events", {}).get("Events", []),
    )


def _who(name: str | None, snap: GameSnapshot) -> str:
    if not name:
        return "?"
    player = snap.player_by_alias(name)
    if player is None:
        return name  # torre, súbdito, monstruo...
    side = "aliado" if player.team == snap.me.team else "enemigo"
    if player is snap.me:
        side = "yo"
    return f"{player.champion} ({side})"


def describe_event(event: dict, snap: GameSnapshot) -> str:
    t = int(event.get("EventTime", 0))
    clock = f"{t // 60:02d}:{t % 60:02d}"
    name = event.get("EventName", "")
    killer = _who(event.get("KillerName"), snap)
    if name == "ChampionKill":
        return f"{clock} {killer} mató a {_who(event.get('VictimName'), snap)}"
    if name == "DragonKill":
        return f"{clock} {killer} tomó dragón {event.get('DragonType', '')}"
    if name == "BaronKill":
        return f"{clock} {killer} tomó Barón"
    if name in {"HeraldKill", "HordeKill"}:
        return f"{clock} {killer} tomó {'Heraldo' if name == 'HeraldKill' else 'larvas del vacío'}"
    if name == "TurretKilled":
        return f"{clock} cayó la torre {event.get('TurretKilled', '')}"
    if name == "InhibKilled":
        return f"{clock} cayó el inhibidor {event.get('InhibKilled', '')}"
    return f"{clock} {name}"
