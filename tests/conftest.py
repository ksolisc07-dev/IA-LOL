import pytest

from lol_coach import champions, free_coach


@pytest.fixture(autouse=True)
def offline_data(monkeypatch):
    """Las pruebas usan los datos incluidos, sin descargar nada de Data Dragon."""
    monkeypatch.setattr(free_coach, "_items_loaded", True)
    monkeypatch.setattr(champions, "_ddragon_loaded", True)
