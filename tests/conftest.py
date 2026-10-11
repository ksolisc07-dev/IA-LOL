import pytest

from lol_coach import champions, items


@pytest.fixture(autouse=True)
def offline_data(monkeypatch):
    """Las pruebas usan los datos incluidos, sin descargar nada de Data Dragon."""
    monkeypatch.setattr(items, "_loaded", True)
    monkeypatch.setattr(items, "_items", {})
    monkeypatch.setattr(champions, "_ddragon_loaded", True)
