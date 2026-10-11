"""Reglas rápidas (sin IA) que detectan errores comunes en tiempo real.

Las alertas de reglas son instantáneas y gratuitas. Algunas, además, piden a la
IA un consejo más elaborado (``coach_reason``), por ejemplo cuando mueres.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lol_coach.game_state import GameSnapshot
from lol_coach.map_tracker import MapReport, MapTracker

CS_TARGET = {"JUNGLE": 5.0, "UTILITY": 0.0}
DEFAULT_CS_TARGET = 6.5


@dataclass
class Alert:
    message: str
    # Si no es None, también se pide a la IA un consejo por este motivo.
    coach_reason: str | None = None
    priority: int = 1
    # Lectura del mapa que acompaña a los avisos de "mapa".
    map_report: MapReport | None = None


@dataclass
class Analyzer:
    review_interval: int = 240
    map_interval: int = 90
    tracker: MapTracker = field(default_factory=MapTracker)
    _cooldowns: dict[str, float] = field(default_factory=dict)
    _seen_event_ids: set[int] = field(default_factory=set)
    _death_times: list[float] = field(default_factory=list)
    _last_review: float = 0.0
    _last_map: float = 0.0
    _started: bool = False

    def _ready(self, key: str, now: float, cooldown: float) -> bool:
        last = self._cooldowns.get(key)
        if last is not None and now - last < cooldown:
            return False
        self._cooldowns[key] = now
        return True

    def update(self, snap: GameSnapshot) -> list[Alert]:
        alerts: list[Alert] = []
        now = snap.game_time

        if not self._started:
            self._started = True
            self._last_review = self._last_map = now
            # Procesa en silencio los eventos previos (p. ej. si arrancas el coach a mitad de
            # partida) para tener timers de objetivos y racha de muertes correctos.
            self._process_events(snap)
            if now < 180:
                alerts.append(Alert("Coach activado. Preparando tu plan de juego.", coach_reason="inicio", priority=2))
            else:
                alerts.append(Alert("Coach activado a mitad de partida. Analizando la situación.",
                                    coach_reason="conexion", priority=2))
            return alerts

        alerts += self._process_events(snap)
        alerts += [Alert(msg, priority=p) for msg, p in self.tracker.tick(now)]
        alerts += self._economy(snap)
        alerts += self._farming(snap)
        alerts += self._vision(snap)

        if now - self._last_review >= self.review_interval and not snap.me.is_dead:
            self._last_review = self._last_map = now
            alerts.append(Alert("", coach_reason="revision"))
        elif self.map_interval and now - self._last_map >= self.map_interval and not snap.me.is_dead:
            self._last_map = now
            alerts.append(Alert("", coach_reason="mapa", map_report=self.tracker.report(snap)))
        return alerts

    def map_report(self, snap: GameSnapshot) -> MapReport:
        return self.tracker.report(snap)

    # ---------------------------------------------------------------- eventos
    def _process_events(self, snap: GameSnapshot) -> list[Alert]:
        alerts: list[Alert] = []
        for event in snap.events:
            event_id = event.get("EventID", -1)
            if event_id in self._seen_event_ids:
                continue
            self._seen_event_ids.add(event_id)
            name = event.get("EventName")
            t = float(event.get("EventTime", snap.game_time))

            if name == "ChampionKill" and event.get("VictimName") in snap.me.aliases:
                self._death_times.append(t)
                recent = [d for d in self._death_times if t - d <= 600]
                if len(recent) >= 3:
                    msg = (f"Llevas {len(recent)} muertes en diez minutos. "
                           "Juega más seguro, farmea bajo torre y espera a tu jungla.")
                else:
                    msg = "Has muerto."
                alerts.append(Alert(msg, coach_reason="muerte", priority=3))

            alerts += [Alert(msg, priority=p) for msg, p in self.tracker.on_event(event, snap)]
            if name == "BaronKill":
                killer = snap.player_by_alias(event.get("KillerName", ""))
                if killer and killer.team != snap.me.team:
                    alerts.append(Alert("El enemigo tiene Barón. No pelees en campo abierto, "
                                        "defiende bajo torre y limpia oleadas.", priority=3))
        return alerts

    # ------------------------------------------------------------- economía
    def _economy(self, snap: GameSnapshot) -> list[Alert]:
        if snap.me.is_dead or snap.game_time < 120:
            return []
        gold = snap.current_gold
        if gold >= 1500 and self._ready("oro", snap.game_time, 90):
            return [Alert(f"Tienes {gold:.0f} de oro sin gastar. Busca un buen momento para volver a base "
                          "y completar objeto.")]
        return []

    def _farming(self, snap: GameSnapshot) -> list[Alert]:
        alerts: list[Alert] = []
        me = snap.me
        minutes = snap.minutes
        if minutes < 6:
            return alerts
        target = CS_TARGET.get(me.position, DEFAULT_CS_TARGET)
        cs_min = me.cs / minutes
        if target and cs_min < target - 1 and self._ready("cs", snap.game_time, 300):
            alerts.append(Alert(f"Vas a {cs_min:.1f} súbditos por minuto. El objetivo es al menos {target:.0f}. "
                                "No dejes morir oleadas sin farmear."))

        opp = snap.lane_opponent
        if opp and me.position not in ("UTILITY", ""):
            cs_diff = opp.cs - me.cs
            if cs_diff >= 20 and self._ready("cs_diff", snap.game_time, 300):
                alerts.append(Alert(f"Vas {cs_diff} súbditos por detrás de {opp.champion}. "
                                    "Prioriza el farmeo antes que los intercambios arriesgados."))
        if opp and opp.level - me.level >= 2 and self._ready("nivel", snap.game_time, 240):
            alerts.append(Alert(f"{opp.champion} te saca {opp.level - me.level} niveles. "
                                "Evita pelear hasta recuperar experiencia.", priority=2))
        return alerts

    def _vision(self, snap: GameSnapshot) -> list[Alert]:
        if snap.minutes < 10:
            return []
        per_min = 1.5 if snap.me.position == "UTILITY" else 0.5
        expected = snap.minutes * per_min
        if snap.me.ward_score < expected * 0.6 and self._ready("vision", snap.game_time, 360):
            return [Alert("Tu visión es baja. Usa tu abalorio cada vez que esté disponible "
                          "y compra guardianes de control.")]
        return []
