"""Salida por voz (texto a voz) en un hilo aparte para no bloquear el bucle."""

from __future__ import annotations

import queue
import threading

SPANISH_HINTS = ("spanish", "español", "espanol", "es-", "es_", "sabina", "helena", "laura", "pablo", "raul")


class Voice:
    def __init__(self, enabled: bool = True, rate: int = 185):
        self.enabled = enabled
        self.rate = rate
        self._queue: queue.Queue[str] = queue.Queue()
        if enabled:
            threading.Thread(target=self._worker, daemon=True).start()

    def say(self, text: str, important: bool = False) -> None:
        text = text.strip()
        if not text:
            return
        print(f"\n🎧 Coach: {text}\n", flush=True)
        if not self.enabled:
            return
        if not important and self._queue.qsize() >= 2:
            return  # No acumular mensajes viejos que ya no sirven.
        self._queue.put(text)

    def _worker(self) -> None:
        try:
            import pyttsx3
        except ImportError:
            print("[voz] pyttsx3 no está instalado; solo se mostrará texto. Instala con: pip install pyttsx3")
            self.enabled = False
            return
        try:
            # El motor debe crearse en el mismo hilo que lo usa.
            engine = pyttsx3.init()
        except Exception as exc:  # p. ej. sin motor de voz en el sistema
            print(f"[voz] No se pudo iniciar el motor de voz: {exc}")
            self.enabled = False
            return
        engine.setProperty("rate", self.rate)
        for voice in engine.getProperty("voices"):
            ident = f"{voice.id} {voice.name} {getattr(voice, 'languages', '')}".lower()
            if any(h in ident for h in SPANISH_HINTS):
                engine.setProperty("voice", voice.id)
                break
        while True:
            text = self._queue.get()
            engine.say(text)
            engine.runAndWait()
