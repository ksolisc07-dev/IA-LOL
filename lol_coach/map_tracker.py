"""Lectura del mapa sin IA: objetivos, dónde se vio al jungla enemigo y a quién gankear.

La Live Client Data API no da posiciones, así que el jungla enemigo se "ve" a través de
los eventos en los que aparece (asesinatos, asistencias, objetivos). Con la IA activada,
además se le muestra el minimapa para que lo busque.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.game_state import GameSnapshot, PlayerState

# Tiempos de aparición (temporada 2026: sin Atakhan y Barón al minuto 20).
# Si Riot los cambia en un parche, solo hay que ajustar esta tabla.
# clave: (nombre, primera aparición, reaparición o None, lado del mapa, desaparece a los)
OBJECTIVES = {
    "dragon": ("el dragón", 5 * 60, 5 * 60, "bot", None),
    "larvas": ("las larvas del vacío", 8 * 60, None, "top", 14 * 60 + 45),
    "heraldo": ("el Heraldo", 15 * 60, None, "top", 19 * 60 + 45),
    "baron": ("el Barón", 20 * 60, 6 * 60, "top", None),
}
ELDER_RESPAWN = 6 * 60
OBJECTIVE_EVENTS = {"DragonKill": "dragon", "HordeKill": "larvas", "HeraldKill": "heraldo", "BaronKill": "baron"}

LANE_OF_POSITION = {"TOP": "top", "MIDDLE": "mid", "BOTTOM": "bot", "UTILITY": "bot", "JUNGLE": "la jungla"}
OPPOSITE = {"top": "bot", "bot": "top"}
SIGHTING_FRESH = 60  # segundos durante los que un avistamiento sirve para decidir


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def find_jungler(players: list[PlayerState]) -> PlayerState | None:
    return (next((p for p in players if p.position == "JUNGLE"), None)
            or next((p for p in players if p.has_smite), None))


@dataclass
class Sighting:
    time: float
    place: str  # "top", "mid", "bot" o "la jungla"
    detail: str


@dataclass
class MapReport:
    summary: str  # datos para la IA
    suggestion: str  # consejo por reglas (modo gratuito)


@dataclass
class MapTracker:
    next_spawn: dict[str, float | None] = field(
        default_factory=lambda: {k: v[1] for k, v in OBJECTIVES.items()})
    dragons: dict[str, int] = field(default_factory=dict)  # equipo -> dragones
    sightings: list[Sighting] = field(default_factory=list)
    _announced: set[str] = field(default_factory=set)

    # ------------------------------------------------------------ objetivos
    def _objective_name(self, key: str) -> str:
        if key == "dragon" and max(self.dragons.values(), default=0) >= 4:
            return "el Dragón Anciano"
        return OBJECTIVES[key][0]

    def status(self, key: str, now: float) -> str:
        """'vivo', 'pronto' (menos de 90 s), 'luego' o 'no'."""
        spawn = self.next_spawn.get(key)
        despawn = OBJECTIVES[key][4]
        if spawn is None or (despawn and now >= despawn):
            return "no"
        if now >= spawn:
            return "vivo"
        return "pronto" if spawn - now <= 90 else "luego"

    def on_event(self, event: dict, snap: GameSnapshot) -> list[tuple[str, int]]:
        """Procesa un evento nuevo. Devuelve avisos (mensaje, prioridad)."""
        name = event.get("EventName")
        t = float(event.get("EventTime", snap.game_time))
        killer = snap.player_by_alias(event.get("KillerName", ""))
        enemy_jg = find_jungler(snap.enemies)
        notes: list[tuple[str, int]] = []

        if name in OBJECTIVE_EVENTS:
            key = OBJECTIVE_EVENTS[name]
            respawn = OBJECTIVES[key][2]
            if key == "dragon":
                if killer:
                    self.dragons[killer.team] = self.dragons.get(killer.team, 0) + 1
                elder = event.get("DragonType") == "Elder" or max(self.dragons.values(), default=0) >= 4
                respawn = ELDER_RESPAWN if elder else respawn
            self.next_spawn[key] = t + respawn if respawn else None
            if key == "heraldo":
                self.next_spawn["larvas"] = None
            self._announced.discard(key)
            if killer and enemy_jg and killer is enemy_jg:
                self._sight(t, OBJECTIVES[key][3], f"tomó {OBJECTIVES[key][0]}")

        elif name == "ChampionKill" and enemy_jg:
            victim = snap.player_by_alias(event.get("VictimName", ""))
            assisters = event.get("Assisters", [])
            jg_helped = killer is enemy_jg or any(a in enemy_jg.aliases for a in assisters)
            if jg_helped and victim:
                place = LANE_OF_POSITION.get(victim.position, "la jungla")
                self._sight(t, place, f"participó en la muerte de {victim.champion}")
                if victim is not snap.me:
                    notes += self._sighting_note(snap, enemy_jg, place)
            elif victim is enemy_jg and killer:
                self._sight(t, LANE_OF_POSITION.get(killer.position, "la jungla"), f"murió ante {killer.champion}")
        return notes

    def _sight(self, t: float, place: str, detail: str) -> None:
        self.sightings.append(Sighting(t, place, detail))
        del self.sightings[:-10]

    def _sighting_note(self, snap: GameSnapshot, jg: PlayerState, place: str) -> list[tuple[str, int]]:
        me = snap.me
        if place not in OPPOSITE:
            return []
        far_side = OPPOSITE[place]
        if me.position == "JUNGLE":
            return [(f"{jg.champion} se mostró en {place}. El lado {far_side} está libre: "
                     f"gankea {far_side} o invade su jungla de ese lado.", 2)]
        my_lane = LANE_OF_POSITION.get(me.position)
        if my_lane == far_side:
            return [(f"El jungla enemigo está en {place}. Puedes presionar tu línea con más confianza.", 1)]
        return []

    def tick(self, now: float) -> list[tuple[str, int]]:
        """Avisos de objetivos que aparecen en un minuto."""
        notes = []
        for key, (_, _, _, side, _) in OBJECTIVES.items():
            spawn = self.next_spawn.get(key)
            if spawn is None or key in self._announced or not (spawn - 60 <= now < spawn):
                continue
            if self.status(key, spawn) == "no":
                continue
            self._announced.add(key)
            river = "inferior" if side == "bot" else "superior"
            notes.append((f"{_cap(self._objective_name(key))} aparece en un minuto. "
                          f"Empuja tu oleada y pon visión en el río {river}.", 2))
        return notes

    # -------------------------------------------------------------- lectura
    def last_sighting(self, now: float) -> Sighting | None:
        return self.sightings[-1] if self.sightings else None

    def gank_targets(self, snap: GameSnapshot) -> list[tuple[str, str]]:
        """Líneas ordenadas por lo favorable que es gankear ahora: [(línea, motivo)]."""
        now = snap.game_time
        seen = self.last_sighting(now)
        fresh_side = seen.place if seen and now - seen.time <= SIGHTING_FRESH else None
        lanes = {"top": ["TOP"], "mid": ["MIDDLE"], "bot": ["BOTTOM", "UTILITY"]}
        scored = []
        for lane, positions in lanes.items():
            allies = [p for p in snap.allies if p.position in positions and p is not snap.me]
            enemies = [p for p in snap.enemies if p.position in positions]
            if not allies or not enemies or all(p.is_dead for p in enemies) or all(p.is_dead for p in allies):
                continue
            ally_lvl = max(p.level for p in allies if not p.is_dead)
            enemy_lvl = max(p.level for p in enemies if not p.is_dead)
            score = (ally_lvl - enemy_lvl) + 0.3 * sum(p.deaths for p in enemies) - 0.3 * sum(p.deaths for p in allies)
            reasons = [f"{'/'.join(p.champion for p in allies)} nivel {ally_lvl} contra "
                       f"{'/'.join(p.champion for p in enemies)} nivel {enemy_lvl}"]
            if fresh_side and fresh_side == lane:
                score -= 3
                reasons.append("su jungla está cerca")
            elif fresh_side in OPPOSITE and OPPOSITE[fresh_side] == lane:
                score += 2
                reasons.append(f"su jungla está en {fresh_side}")
            scored.append((score, lane, ", ".join(reasons)))
        return [(lane, why) for _, lane, why in sorted(scored, reverse=True)]

    def report(self, snap: GameSnapshot) -> MapReport:
        now = snap.game_time
        enemy_jg = find_jungler(snap.enemies)
        lines = ["Lectura del mapa (según eventos; no son posiciones exactas):"]
        jg_name = enemy_jg.champion if enemy_jg else "el jungla enemigo"
        seen = self.last_sighting(now)
        if enemy_jg and enemy_jg.is_dead:
            lines.append(f"- {jg_name} (jungla enemigo) está MUERTO, reaparece en {enemy_jg.respawn_timer:.0f} s.")
        elif seen:
            lines.append(f"- {jg_name} (jungla enemigo) visto por última vez en {seen.place} "
                         f"hace {now - seen.time:.0f} s ({seen.detail}).")
        else:
            lines.append(f"- {jg_name} (jungla enemigo) no ha aparecido en ningún evento todavía.")
        for key in OBJECTIVES:
            state = self.status(key, now)
            side = "río inferior, lado bot" if OBJECTIVES[key][3] == "bot" else "río superior, lado top"
            name = f"{_cap(self._objective_name(key))} ({side})"
            if state == "vivo":
                lines.append(f"- {name}: disponible ahora.")
            elif state in ("pronto", "luego"):
                lines.append(f"- {name}: aparece en {_clock(self.next_spawn[key] - now)}.")
        targets = self.gank_targets(snap)
        if targets:
            lines.append("- Ganks más favorables según niveles y avistamientos: "
                         + "; ".join(f"{lane} ({why})" for lane, why in targets[:2]))
        return MapReport("\n".join(lines), self._suggest(snap, enemy_jg, seen, targets))

    def _suggest(self, snap: GameSnapshot, enemy_jg, seen: Sighting | None, targets) -> str:
        now = snap.game_time
        me = snap.me
        jg_name = enemy_jg.champion if enemy_jg else "El jungla enemigo"
        alive = [k for k in OBJECTIVES if self.status(k, now) == "vivo"]
        soon = [k for k in OBJECTIVES if self.status(k, now) == "pronto"]
        fresh = seen if seen and now - seen.time <= SIGHTING_FRESH else None

        if enemy_jg and enemy_jg.is_dead and (alive or soon):
            obj = self._objective_name((alive or soon)[0])
            return f"{jg_name} está muerto {enemy_jg.respawn_timer:.0f} segundos: es el momento de ir por {obj}."
        for key in alive:
            side = OBJECTIVES[key][3]
            if fresh and fresh.place in OPPOSITE and fresh.place != side:
                return f"{jg_name} se vio en {fresh.place}: buen momento para hacer {self._objective_name(key)}."
        if me.position == "JUNGLE" and targets:
            lane, why = targets[0]
            return f"Mejor ganke ahora: {lane}, porque {why}."
        if soon:
            return f"Prepárate para {self._objective_name(soon[0])}: empuja tu oleada y pon visión."
        if not seen and now > 4 * 60:
            return f"No se ha visto a {jg_name} en un buen rato. Pon visión en el río y juega con cuidado."
        return ""
