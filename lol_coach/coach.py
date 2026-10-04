"""Coach basado en Claude: convierte el estado de la partida en consejos."""

from __future__ import annotations

from lol_coach import free_coach
from lol_coach.ai_backends import AIError
from lol_coach.game_state import GameSnapshot

LIVE_SYSTEM = """Eres un coach profesional de League of Legends (nivel Challenger) que acompaña \
a un jugador durante sus partidas clasificatorias. Hablas en español, con un tono directo, \
honesto y motivador, como un coach real en el oído del jugador.

Tu respuesta se leerá en voz alta con un sintetizador de voz mientras el jugador está jugando:
- Máximo 2 o 3 frases cortas (unas 45 palabras). Nada de listas, viñetas, markdown ni emojis.
- Ve al grano: primero el error más importante o la acción más urgente, luego el porqué en pocas palabras.
- Sé concreto: nombra campeones, objetos, timings y posiciones del mapa.
- Al recomendar objetos, ten en cuenta la composición enemiga (daño físico o mágico, curaciones, \
tanques, control de masas) y los objetos que ya tienen. Usa los nombres de objetos tal como \
aparecen en los datos de la partida cuando sea posible.
- No repitas consejos que ya diste hace poco salvo que el jugador siga cometiendo el mismo error.
- Puedes equivocarte sobre el parche actual; prioriza principios sólidos sobre detalles de números."""

REVIEW_SYSTEM = """Eres un coach profesional de League of Legends (nivel Challenger). Hablas en \
español. Analizas partidas clasificatorias de tu alumno para encontrar los patrones que le \
están costando victorias. Eres honesto y específico: cada crítica viene con una acción \
concreta para corregirla. Prioriza los 3-4 problemas que más impacto tienen en ganar partidas \
(farmeo, muertes evitables, visión, participación en objetivos, decisiones de build) en lugar \
de listar todo."""

REASON_PROMPTS = {
    "inicio": "Acaba de empezar la partida. Dame el plan de juego: cómo jugar contra mi rival de línea, "
              "cuál es mi condición de victoria y qué objetos debería armarme contra esta composición enemiga.",
    "muerte": "Acabo de morir. Dime qué probablemente hice mal según el contexto y qué debería "
              "comprar ahora con mi oro disponible (si puedo comprar algo útil).",
    "revision": "Revisión rápida: ¿qué es lo más importante que debería mejorar o hacer en los próximos minutos?",
}


class Coach:
    """Da consejos con IA si hay un backend disponible y, si no, con reglas gratuitas."""

    def __init__(self, backend=None, live_effort: str = "low", review_effort: str = "high"):
        self.backend = backend
        self.live_effort = live_effort
        self.review_effort = review_effort
        self.recent_tips: list[str] = []

    @property
    def mode(self) -> str:
        return f"IA con {self.backend.name}" if self.backend else "gratuito (sin IA)"

    def _ask(self, system: str, prompt: str, effort: str, max_tokens: int) -> str | None:
        """Pregunta a la IA; devuelve None si no hay IA o si falla (se usan las reglas)."""
        if self.backend is None:
            return None
        try:
            return self.backend.ask(system, prompt, effort, max_tokens)
        except AIError as exc:
            print(f"[IA] {exc} Uso el modo gratuito para este consejo.")
            return None

    def _live_prompt(self, snap: GameSnapshot, request: str, alerts: list[str]) -> str:
        parts = ["Estado actual de la partida:", snap.to_prompt(), "",
                 "Análisis automático de la composición enemiga:", free_coach.build_advice(snap)]
        if alerts:
            parts += ["", "Alertas automáticas recientes:", *[f"- {a}" for a in alerts]]
        if self.recent_tips:
            parts += ["", "Consejos que ya diste hace poco (no los repitas):",
                      *[f"- {t}" for t in self.recent_tips[-4:]]]
        parts += ["", request]
        return "\n".join(parts)

    def live_advice(self, snap: GameSnapshot, reason: str, alerts: list[str] | None = None) -> str:
        request = REASON_PROMPTS.get(reason, REASON_PROMPTS["revision"])
        prompt = self._live_prompt(snap, request, alerts or [])
        advice = self._ask(LIVE_SYSTEM, prompt, self.live_effort, max_tokens=4000)
        if advice is None:
            advice = free_coach.advice(snap, reason)
        if advice:
            self.recent_tips.append(advice)
        return advice

    def answer(self, snap: GameSnapshot | None, question: str) -> str:
        if snap is None:
            prompt = f"No hay una partida en curso. Pregunta del jugador: {question}"
        else:
            prompt = self._live_prompt(snap, f"Pregunta del jugador: {question}", [])
        advice = self._ask(LIVE_SYSTEM, prompt, self.live_effort, max_tokens=4000)
        return advice if advice is not None else free_coach.answer(snap, question)

    def post_game(self, game_summary: str) -> str:
        prompt = (
            "Acaba de terminar esta partida. Este es el registro minuto a minuto de mis "
            f"estadísticas y los eventos clave:\n\n{game_summary}\n\n"
            "Hazme un resumen hablado (máximo 6 frases, sin markdown, se leerá en voz alta): "
            "qué hice bien, cuáles fueron mis dos errores principales y qué practicar en la próxima partida."
        )
        advice = self._ask(REVIEW_SYSTEM, prompt, self.review_effort, max_tokens=8000)
        return advice if advice is not None else "Partida terminada. Buen trabajo, a por la siguiente."

    def review_matches(self, matches_report: str) -> str:
        prompt = (
            "Estos son los datos de mis últimas partidas clasificatorias:\n\n"
            f"{matches_report}\n\n"
            "Escribe un informe en markdown con: 1) resumen de mi rendimiento, 2) los errores "
            "recurrentes más importantes con evidencia de los datos, 3) recomendaciones de build y "
            "de pool de campeones, 4) un plan de práctica concreto para las próximas 10 partidas."
        )
        report = self._ask(REVIEW_SYSTEM, prompt, self.review_effort, max_tokens=16000)
        if report is None:
            return "# Tus últimas partidas\n\n(Análisis con IA no disponible en modo gratuito.)\n\n" + matches_report
        return report
