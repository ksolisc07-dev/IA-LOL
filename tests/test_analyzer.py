from dataclasses import replace
from types import SimpleNamespace

from lol_coach import free_coach
from lol_coach.ai_backends import AIError, AnthropicAPI
from lol_coach.analyzer import Analyzer
from lol_coach.cli import DEMO_FILE
from lol_coach.coach import Coach
from lol_coach.game_state import parse_snapshot
from lol_coach.live_client import FileClient
from lol_coach.postgame import LiveGameLog, summarize_match


def demo_snapshot():
    return parse_snapshot(FileClient(DEMO_FILE).fetch())


def test_parse_snapshot_identifies_player_and_opponent():
    snap = demo_snapshot()
    assert snap.me.champion == "Jinx"
    assert snap.me.role == "ADC"
    assert len(snap.allies) == 5 and len(snap.enemies) == 5
    assert snap.lane_opponent.champion == "Caitlyn"
    text = snap.to_prompt()
    assert "Rival de línea: Caitlyn" in text
    assert "Kha'Zix (enemigo) mató a Jinx (yo)" in text


def test_first_update_requests_game_plan_and_ignores_old_events():
    alerts = Analyzer().update(replace(demo_snapshot(), game_time=60))
    assert [a.coach_reason for a in alerts] == ["inicio"]


def test_detects_death_streak_and_farming_problems():
    snap = demo_snapshot()
    analyzer = Analyzer()
    analyzer.update(replace(snap, events=snap.events[:-1], game_time=snap.game_time - 5))
    alerts = analyzer.update(snap)
    messages = " ".join(a.message for a in alerts)
    assert any(a.coach_reason == "muerte" for a in alerts)
    assert "3 muertes en diez minutos" in messages
    assert "súbditos por detrás de Caitlyn" in messages
    assert "te saca 2 niveles" in messages
    assert "visión es baja" in messages


def test_cooldowns_prevent_repeating_alerts():
    snap = demo_snapshot()
    analyzer = Analyzer()
    analyzer.update(replace(snap, events=snap.events[:-1]))
    analyzer.update(snap)
    again = analyzer.update(replace(snap, game_time=snap.game_time + 10))
    assert again == []


def test_gold_and_dragon_timer_alerts():
    snap = demo_snapshot()
    alive_me = replace(snap.me, is_dead=False)
    analyzer = Analyzer()
    analyzer.update(snap)
    rich = replace(snap, me=alive_me, current_gold=1800, game_time=548.3 + 250)
    messages = [a.message for a in analyzer.update(rich)]
    assert any("1800 de oro" in m for m in messages)
    assert any("dragón aparece en un minuto" in m for m in messages)


def test_periodic_review():
    snap = demo_snapshot()
    analyzer = Analyzer(review_interval=60)
    analyzer.update(snap)
    later = replace(snap, me=replace(snap.me, is_dead=False), game_time=snap.game_time + 61)
    assert any(a.coach_reason == "revision" for a in analyzer.update(later))


class FakeMessages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="thinking", thinking=""),
                     SimpleNamespace(type="text", text="Compra Ángel de la guarda.")],
        )


def test_coach_builds_prompt_and_tracks_tips():
    fake = FakeMessages()
    client = SimpleNamespace(beta=SimpleNamespace(messages=fake))
    coach = Coach(AnthropicAPI("claude-opus-5-5", client=client))
    advice = coach.live_advice(demo_snapshot(), "muerte", ["Has muerto."])
    assert advice == "Compra Ángel de la guarda."
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "low"}
    prompt = call["messages"][0]["content"][-1]["text"]
    assert "Acabo de morir" in prompt and "Has muerto." in prompt
    coach.live_advice(demo_snapshot(), "revision")
    assert "Compra Ángel de la guarda." in fake.calls[1]["messages"][0]["content"][-1]["text"]


def test_live_game_log_summary():
    log = LiveGameLog()
    snap = demo_snapshot()
    log.record(snap)
    log.record(snap)  # mismo minuto: no duplica
    summary = log.summary()
    assert summary.count("min 14") == 1
    assert "Campeón: Jinx (ADC)" in summary


def test_summarize_match():
    def p(puuid, team, pos, champ, k, d, a, win):
        return {"puuid": puuid, "teamId": team, "teamPosition": pos, "championName": champ,
                "kills": k, "deaths": d, "assists": a, "win": win, "totalMinionsKilled": 200,
                "neutralMinionsKilled": 10, "goldEarned": 12000, "totalDamageDealtToChampions": 20000,
                "visionScore": 30, "visionWardsBoughtInGame": 2,
                **{f"item{i}": 0 for i in range(7)}, "item0": 3031}
    match = {"info": {"gameDuration": 1800, "participants": [
        p("me", 100, "BOTTOM", "Jinx", 5, 2, 7, True),
        p("ally", 100, "MIDDLE", "Ahri", 5, 3, 4, True),
        p("opp", 200, "BOTTOM", "Caitlyn", 3, 5, 2, False),
    ]}}
    s = summarize_match(match, "me", {3031: "Filo infinito"})
    assert s["resultado"] == "Victoria"
    assert s["cs_min"] == 7.0
    assert s["participacion_asesinatos"] == "120%"
    assert s["objetos"] == ["Filo infinito"]
    assert s["rival"]["campeon"] == "Caitlyn"


def test_save_setting_replaces_existing(tmp_path, monkeypatch):
    from lol_coach.config import save_setting

    env = tmp_path / ".env"
    env.write_text("RIOT_ID=Viejo#LAN\nCOACH_VOICE=1\n", encoding="utf-8")
    monkeypatch.delenv("RIOT_ID", raising=False)
    save_setting("RIOT_ID", "Nuevo#LAN", env)
    assert env.read_text(encoding="utf-8").splitlines() == ["COACH_VOICE=1", "RIOT_ID=Nuevo#LAN"]


def test_free_build_advice_reads_enemy_comp():
    snap = demo_snapshot()
    comp, recs = free_coach.build_recommendations(snap)
    # Kha'Zix y Zed son asesinos; Malphite es tanque; mezcla de daño.
    assert set(comp.assassins) == {"Kha'Zix", "Zed"}
    assert comp.tanks == ["Malphite"]
    assert free_coach.my_kind(snap) == "adc"
    assert ("Ángel Guardián", "contra los asesinos Kha'Zix y Zed") in recs


def test_free_build_advice_heavy_ap_and_healers():
    snap = demo_snapshot()
    names = [("Soraka", "Soraka"), ("Ahri", "Ahri"), ("Lux", "Lux"), ("Syndra", "Syndra"), ("Malphite", "Malphite")]
    enemies = [replace(e, champion=n, champion_id=i) for e, (n, i) in zip(snap.enemies, names)]
    me = replace(snap.me, champion="Garen", champion_id="Garen", position="TOP", items=[])
    snap = replace(snap, enemies=enemies, me=me, game_time=60)
    comp, recs = free_coach.build_recommendations(snap)
    assert comp.heavy_ap and comp.healers == ["Soraka"]
    assert [name for name, _ in recs] == ["Botas de Mercurio", "El Llamado del Verdugo", "Fauces de Malmortius"]


def test_free_death_advice_detects_gank():
    snap = demo_snapshot()
    text = free_coach.death_advice(snap)
    assert "Te atraparon entre 2" not in text  # solo hubo un asistente
    assert "Kha'Zix" in text or "jungla" in text


def test_coach_without_ai_uses_rules():
    coach = Coach(None)
    assert coach.mode == "gratuito (sin IA)"
    assert "Caitlyn" in coach.live_advice(demo_snapshot(), "inicio")
    assert "solo puedo responder" in coach.answer(demo_snapshot(), "¿voy a dragón?")
    assert "Te conviene armar" in coach.answer(demo_snapshot(), "¿qué me armo?")


def test_coach_falls_back_to_rules_when_ai_fails():
    class Broken:
        name = "roto"

        def ask(self, *args):
            raise AIError("sin conexión")

    advice = Coach(Broken()).live_advice(demo_snapshot(), "inicio")
    assert "Caitlyn" in advice


def test_detect_backend_modes(monkeypatch):
    from lol_coach import ai_backends

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(ai_backends, "find_claude_code", lambda: None)
    assert ai_backends.detect_backend("auto", "m", "sonnet") is None
    monkeypatch.setattr(ai_backends, "find_claude_code", lambda: "/usr/bin/claude")
    assert isinstance(ai_backends.detect_backend("auto", "m", "sonnet"), ai_backends.ClaudeSubscription)
    assert ai_backends.detect_backend("gratis", "m", "sonnet") is None


def test_platform_aliases():
    from lol_coach.riot_api import RiotAPIError, RiotClient, normalize_platform

    assert normalize_platform(" LAN ") == "la1"
    assert normalize_platform("las") == "la2"
    assert normalize_platform("euw1") == "euw1"
    assert RiotClient("key", "lan").region == "americas"
    try:
        RiotClient("key", "marte")
    except RiotAPIError as exc:
        assert "lan, las" in str(exc)
    else:
        raise AssertionError("debería fallar")


def test_start_mid_game_is_not_called_game_start():
    alerts = Analyzer().update(demo_snapshot())  # la partida de ejemplo va por el minuto 14
    assert [a.coach_reason for a in alerts] == ["conexion"]
    early = replace(demo_snapshot(), game_time=90)
    assert [a.coach_reason for a in Analyzer().update(early)] == ["inicio"]


def test_screen_recorder_keeps_recent_frames(tmp_path):
    import time as _time

    from PIL import Image

    from lol_coach.screen import ScreenRecorder

    colors = iter([(200, 0, 0), (0, 200, 0), (0, 0, 200)] + [(0, 0, 200)] * 100)
    rec = ScreenRecorder(tmp_path, interval=0.05,
                         grab_factory=lambda: (lambda: Image.new("RGB", (1920, 1080), next(colors))))
    assert rec.capture() == []  # inactivo: no captura nada
    rec.set_active(True)
    _time.sleep(0.4)
    files = rec.capture_death()
    assert [desc for _, desc in files] == [
        "mi pantalla hace unos 6 segundos", "zoom del minimapa hace unos 6 segundos", "mi pantalla al morir"]
    full = Image.open(files[0][0])
    assert full.width == 1280  # reducida para enviar menos datos
    rec.set_active(False)
    assert rec.capture() == []


def test_subscription_backend_sends_images(monkeypatch, tmp_path):
    from lol_coach import ai_backends

    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"], seen["input"] = cmd, kwargs["input"]
        return SimpleNamespace(returncode=0, stdout="Ve con tu equipo.", stderr="")

    monkeypatch.setattr(ai_backends.subprocess, "run", fake_run)
    shot = tmp_path / "captura.jpg"
    shot.write_bytes(b"x")
    backend = ai_backends.ClaudeSubscription("claude")
    assert backend.ask("sistema", "consejo", "low", 100, images=[(str(shot), "mi pantalla")]) == "Ve con tu equipo."
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == "Read"
    assert str(tmp_path) in seen["cmd"]
    assert str(shot) in seen["input"] and "mi pantalla" in seen["input"]
    backend.ask("sistema", "consejo", "low", 100)
    assert seen["cmd"][seen["cmd"].index("--tools") + 1] == ""
