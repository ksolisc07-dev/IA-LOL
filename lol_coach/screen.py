"""Capturas de pantalla de la partida para que la IA "vea" lo que pasa.

Guarda en memoria las últimas capturas (una cada pocos segundos) para poder mostrarle
a la IA lo que pasó justo antes de morir. Solo captura mientras hay una partida en curso
y solo se envían imágenes cuando se pide un consejo a la IA.
"""

from __future__ import annotations

import collections
import itertools
import threading
import time
from pathlib import Path

# Zona aproximada del minimapa (esquina inferior derecha), en fracción de la pantalla.
MINIMAP_BOX = (0.78, 0.62, 1.0, 1.0)


def _grab_with_mss(monitor: int):
    import mss
    from PIL import Image

    sct = mss.mss()  # una instancia por hilo

    def grab():
        monitors = sct.monitors
        shot = sct.grab(monitors[monitor if monitor < len(monitors) else 1])
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    return grab


class ScreenRecorder:
    def __init__(self, folder: str | Path, interval: float = 2.0, keep: int = 8, monitor: int = 1,
                 max_width: int = 1280, grab_factory=None):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.max_width = max_width
        self._frames: collections.deque = collections.deque(maxlen=keep)
        self._lock = threading.Lock()
        self._active = threading.Event()
        self._grab_factory = grab_factory or (lambda: _grab_with_mss(monitor))
        self._counter = itertools.count()
        self._warned_black = False
        self.error: str | None = None
        threading.Thread(target=self._run, daemon=True).start()

    def set_active(self, active: bool) -> None:
        if active:
            self._active.set()
        else:
            self._active.clear()
            with self._lock:
                self._frames.clear()

    def _run(self) -> None:
        try:
            grab = self._grab_factory()
        except Exception as exc:
            self.error = str(exc)
            print(f"[captura] No se pudo iniciar la captura de pantalla: {exc}")
            return
        while True:
            self._active.wait()
            try:
                image = grab()
            except Exception as exc:
                self.error = str(exc)
                time.sleep(5)
                continue
            if not self._warned_black and image.convert("L").getextrema()[1] < 10:
                self._warned_black = True
                print("[captura] La captura sale negra. Pon el juego en modo 'Ventana sin bordes' "
                      "(Opciones → Vídeo → Modo de ventana) para que la IA pueda ver tu partida.")
            with self._lock:
                self._frames.append((time.time(), image))
            time.sleep(self.interval)

    def _frame_near(self, seconds_ago: float):
        target = time.time() - seconds_ago
        with self._lock:
            if not self._frames:
                return None
            return min(self._frames, key=lambda f: abs(f[0] - target))[1]

    def _save(self, image, label: str, max_width: int) -> str:
        if image.width > max_width:
            image = image.resize((max_width, round(image.height * max_width / image.width)))
        # Nombres rotativos para no llenar el disco.
        path = self.folder / f"captura_{next(self._counter) % 12:02d}_{label}.jpg"
        image.save(path, "JPEG", quality=80)
        return str(path)

    def _minimap(self, image):
        w, h = image.size
        x0, y0, x1, y1 = MINIMAP_BOX
        return image.crop((int(w * x0), int(h * y0), int(w * x1), int(h * y1)))

    def capture(self, seconds_ago: float = 0) -> list[tuple[str, str]]:
        """Pantalla completa + minimapa ampliado. Devuelve [(ruta, descripción)]."""
        image = self._frame_near(seconds_ago)
        if image is None:
            return []
        when = "ahora" if seconds_ago < 1 else f"hace unos {seconds_ago:.0f} segundos"
        return [
            (self._save(image, "pantalla", self.max_width), f"mi pantalla {when}"),
            (self._save(self._minimap(image), "minimapa", 700), f"zoom del minimapa {when}"),
        ]

    def capture_death(self) -> list[tuple[str, str]]:
        """Lo que pasó justo antes de morir y el momento actual."""
        before = self.capture(seconds_ago=6)
        now = self._frame_near(0)
        if now is None:
            return before
        return before + [(self._save(now, "muerte", self.max_width), "mi pantalla al morir")]

    def capture_minimap(self) -> list[tuple[str, str]]:
        """Solo el minimapa ampliado: suficiente para ubicar al jungla enemigo."""
        image = self._frame_near(0)
        if image is None:
            return []
        return [(self._save(self._minimap(image), "minimapa", 700), "zoom del minimapa ahora")]
