"""Punto de entrada: python -m lol_coach [en-vivo|demo|analizar]."""

from __future__ import annotations

import argparse
import subprocess
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

from lol_coach.analyzer import Analyzer
from lol_coach.coach import Coach
from lol_coach import free_coach
from lol_coach.ai_backends import detect_backend, find_claude_code
from lol_coach.config import Config, app_dir, save_setting
from lol_coach.game_state import GameSnapshot, parse_snapshot
from lol_coach.live_client import FileClient, GameNotRunning, LiveClient
from lol_coach.postgame import LiveGameLog, format_matches, summarize_match
from lol_coach.riot_api import normalize_platform
from lol_coach.voice import Voice

DEMO_FILE = Path(__file__).parent / "demo_data" / "sample_game.json"


class CoachWorker:
    """Ejecuta las llamadas a la IA en segundo plano, una a la vez.

    Solo guarda la petición pendiente más reciente: un consejo sobre una situación
    de hace un minuto ya no le sirve al jugador.
    """

    def __init__(self, coach: Coach, voice: Voice):
        self.coach = coach
        self.voice = voice
        self._cond = threading.Condition()
        self._pending = None
        self._busy = False
        threading.Thread(target=self._run, daemon=True).start()

    def submit(self, fn, *args, force: bool = False) -> None:
        with self._cond:
            if not force and (self._busy or self._pending is not None):
                return  # Ya hay un consejo en camino; no saturar.
            self._pending = (fn, args)
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._pending is None:
                    self._cond.wait()
                fn, args = self._pending
                self._pending, self._busy = None, True
            try:
                self.voice.say(fn(*args), important=True)
            except Exception as exc:  # que un fallo puntual no detenga al coach
                print(f"[coach] Error al generar consejo: {exc}")
            finally:
                with self._cond:
                    self._busy = False


def _question_loop(worker: CoachWorker, state: dict) -> None:
    print("Escribe una pregunta y pulsa Enter en cualquier momento (ej.: '¿qué me armo?').")
    for line in sys.stdin:
        question = line.strip()
        if question:
            worker.submit(worker.coach.answer, state.get("snap"), question, force=True)


def make_coach(cfg: Config) -> Coach:
    backend = detect_backend(cfg.mode, cfg.model, cfg.subscription_model)
    coach = Coach(backend, cfg.live_effort, cfg.review_effort)
    print(f"Modo del coach: {coach.mode}")
    if backend is None and cfg.mode == "auto":
        print("  (Si tienes Claude Pro o Max, instala Claude Code para activar la IA gratis; mira el README.)")
    return coach


def run_live(cfg: Config, client=None) -> None:
    voice = Voice(cfg.voice_enabled, cfg.voice_rate)
    coach = make_coach(cfg)
    worker = CoachWorker(coach, voice)
    client = client or LiveClient()
    state: dict[str, GameSnapshot | None] = {"snap": None}
    threading.Thread(target=_question_loop, args=(worker, state), daemon=True).start()

    analyzer: Analyzer | None = None
    log: LiveGameLog | None = None
    print("Esperando a que empiece una partida de League of Legends...")
    while True:
        try:
            snap = parse_snapshot(client.fetch())
        except (GameNotRunning, ValueError, KeyError):
            if log is not None and log.last_snapshot is not None:
                print("La partida terminó. Generando resumen...")
                worker.submit(coach.post_game, log.summary(), force=True)
                coach.recent_tips.clear()
            analyzer, log, state["snap"] = None, None, None
            time.sleep(5)
            continue

        if analyzer is None:
            analyzer, log = Analyzer(review_interval=cfg.review_interval), LiveGameLog()
            print(f"Partida detectada: {snap.me.champion} ({snap.me.role}).")
        state["snap"] = snap
        log.record(snap)

        alerts = analyzer.update(snap)
        for alert in sorted(alerts, key=lambda a: -a.priority):
            voice.say(alert.message, important=alert.priority >= 3)
        reasons = [a.coach_reason for a in alerts if a.coach_reason]
        if reasons:
            reason = "muerte" if "muerte" in reasons else reasons[0]
            context = [a.message for a in alerts if a.message]
            worker.submit(coach.live_advice, snap, reason, context, force=reason != "revision")
        time.sleep(cfg.poll_seconds)


def run_demo(cfg: Config) -> None:
    """Analiza una partida de ejemplo sin necesidad de tener el juego abierto."""
    snap = parse_snapshot(FileClient(DEMO_FILE).fetch())
    print("Partida de ejemplo:\n")
    print(snap.to_prompt())
    analyzer = Analyzer()
    # Simula que el coach ya estaba activo antes del último evento (tu muerte).
    analyzer.update(replace(snap, events=snap.events[:-1], game_time=snap.game_time - 5))
    alerts = analyzer.update(snap)
    print("\nAlertas automáticas:")
    for alert in alerts:
        if alert.message:
            print(f"  - {alert.message}")
    voice = Voice(cfg.voice_enabled, cfg.voice_rate)
    coach = make_coach(cfg)
    print("\nPlan de juego al empezar la partida:")
    voice.say(free_coach.game_plan(snap), important=True)
    print("Consejo tras tu muerte:")
    voice.say(coach.live_advice(snap, "muerte", [a.message for a in alerts if a.message]), important=True)
    if cfg.voice_enabled:
        time.sleep(15)  # dar tiempo a que termine de hablar


def run_review(cfg: Config, riot_id: str, platform: str, count: int, output: str | None) -> None:
    from lol_coach.riot_api import RiotAPIError, RiotClient, item_names

    print(f"\nBuscando las rankeds de {riot_id} en {platform}...")

    if not cfg.riot_api_key:
        sys.exit("Falta RIOT_API_KEY. Consíguela en https://developer.riotgames.com y ponla en tu .env")
    try:
        riot = RiotClient(cfg.riot_api_key, platform)
        puuid = riot.puuid(riot_id)
        ids = riot.match_ids(puuid, count=count)
        if not ids:
            sys.exit("No se encontraron partidas clasificatorias recientes.")
        names = item_names()
        print(f"Descargando {len(ids)} partidas...")
        summaries = [summarize_match(riot.match(mid), puuid, names) for mid in ids]
    except RiotAPIError as exc:
        sys.exit(f"Error de la API de Riot: {exc}")

    coach = make_coach(cfg)
    if coach.backend:
        print("Analizando con IA (puede tardar un minuto)...\n")
    report = coach.review_matches(format_matches(summaries))
    print(report)
    if output:
        Path(output).write_text(report, encoding="utf-8")
        print(f"\nInforme guardado en {output}")


def setup_subscription() -> None:
    """Instala Claude Code (si falta) e inicia sesión con la cuenta de Claude Pro/Max."""
    print("\nLa IA usa tu suscripción Claude Pro o Max mediante Claude Code (el plan gratis no sirve).")
    exe = find_claude_code()
    if exe is None:
        if sys.platform != "win32":
            print("Instala Claude Code con: curl -fsSL https://claude.ai/install.sh | bash")
            return
        if input("Claude Code no está instalado. ¿Instalarlo ahora? [S/n]: ").strip().lower() in ("n", "no"):
            return
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                        "irm https://claude.ai/install.ps1 | iex"])
        exe = find_claude_code()
        if exe is None:
            print("No se pudo instalar. Instálalo a mano en PowerShell con:")
            print("  irm https://claude.ai/install.ps1 | iex")
            return
    print("\nSe abrirá el navegador para iniciar sesión con tu cuenta de Claude.")
    subprocess.run([exe, "auth", "login", "--claudeai"])
    status = subprocess.run([exe, "auth", "status", "--text"], capture_output=True, text=True)
    print(status.stdout or status.stderr)
    save_setting("COACH_MODO", "auto")
    print("Listo. Desde ahora el coach usará la IA con tu suscripción.")


def _review_from_menu(cfg: Config) -> None:
    if not cfg.riot_api_key:
        print("\nNecesitas una API key de Riot (gratis): https://developer.riotgames.com")
        key = input("Pégala aquí (o Enter para volver): ").strip()
        if not key:
            return
        save_setting("RIOT_API_KEY", key)
        cfg.riot_api_key = key
    riot_id = input(f"Tu Riot ID (Nombre#TAG) [{cfg.riot_id or ''}]: ").strip() or cfg.riot_id or ""
    platform = input(f"Servidor (lan, las, na, euw, br...) [{cfg.riot_platform}]: ").strip()
    platform = normalize_platform(platform or cfg.riot_platform)
    save_setting("RIOT_ID", riot_id)
    save_setting("RIOT_PLATFORM", platform)
    cfg.riot_id, cfg.riot_platform = riot_id, platform
    run_review(cfg, riot_id, platform, 10, str(app_dir() / "informe.md"))


def run_menu(cfg: Config) -> None:
    """Menú para quien abre el programa con doble clic. Vuelve al menú tras cada opción."""
    actions = {"1": run_live, "2": run_demo, "3": _review_from_menu}
    while True:
        has_ai = detect_backend(cfg.mode, cfg.model, cfg.subscription_model) is not None
        print("\n=== Coach para League of Legends ===")
        print(f"IA: {'activada' if has_ai else 'desactivada (modo gratuito)'}\n")
        print("  1) Coach en vivo (déjalo abierto mientras juegas)")
        print("  2) Demo con una partida de ejemplo")
        print("  3) Analizar mis últimas rankeds")
        print("  4) Activar la IA con mi suscripción de Claude (Pro/Max)")
        print("  5) Salir\n")
        choice = input("Elige una opción [1]: ").strip() or "1"
        if choice == "5":
            return
        try:
            if choice == "4":
                setup_subscription()
                cfg.mode = "auto"
            elif choice in actions:
                actions[choice](cfg)
        except SystemExit as exc:
            if isinstance(exc.code, str):
                print(f"\n{exc.code}")
        except KeyboardInterrupt:
            print()
        except Exception as exc:  # que un error no cierre la ventana sin explicación
            print(f"\nOcurrió un error: {exc}")


def main(argv: list[str] | None = None) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            # Evita errores con tildes y emojis en consolas de Windows.
            stream.reconfigure(encoding="utf-8", errors="replace")
    cfg = Config()
    parser = argparse.ArgumentParser(prog="lol_coach", description="Coach para tus rankeds de LoL")
    parser.add_argument("--sin-voz", action="store_true", help="solo mostrar texto")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("en-vivo", help="coach durante la partida (por defecto)")
    sub.add_parser("demo", help="prueba con una partida de ejemplo")
    sub.add_parser("menu", help="menú interactivo")
    sub.add_parser("activar-ia", help="instala Claude Code e inicia sesión con tu Claude Pro/Max")
    review = sub.add_parser("analizar", help="analiza tus últimas rankeds con la API de Riot")
    review.add_argument("--riot-id", default=cfg.riot_id, help="Nombre#TAG")
    review.add_argument("--plataforma", default=cfg.riot_platform, help="la1, la2, na1, euw1, kr...")
    review.add_argument("--partidas", type=int, default=10)
    review.add_argument("--salida", help="guardar el informe en un archivo .md")
    args = parser.parse_args(argv)

    if args.sin_voz:
        cfg.voice_enabled = False
    try:
        if args.cmd == "menu" or (args.cmd is None and getattr(sys, "frozen", False)):
            run_menu(cfg)
        elif args.cmd == "activar-ia":
            setup_subscription()
        elif args.cmd == "demo":
            run_demo(cfg)
        elif args.cmd == "analizar":
            if not args.riot_id:
                sys.exit("Indica tu Riot ID con --riot-id Nombre#TAG o RIOT_ID en el .env")
            run_review(cfg, args.riot_id, args.plataforma, args.partidas, args.salida)
        else:
            run_live(cfg)
    except KeyboardInterrupt:
        print("\n¡Suerte en tus rankeds!")
    except SystemExit as exc:
        # Mostrar el mensaje antes de la pausa final; si no, la ventana se cierra sin verlo.
        if isinstance(exc.code, str):
            print(f"\n{exc.code}")
            raise SystemExit(1) from None
        raise
    finally:
        if getattr(sys, "frozen", False):
            # Abierto con doble clic: que la ventana no se cierre sin dejar leer el mensaje.
            try:
                input("\nPulsa Enter para cerrar...")
            except (KeyboardInterrupt, EOFError):
                pass
