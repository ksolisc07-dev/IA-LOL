"""Salida por voz (texto a voz) en un hilo aparte para no bloquear el bucle.

En Windows se usa directamente el motor de voz del sistema (SAPI, el mismo del Narrador).
En otros sistemas, pyttsx3.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import time

SPANISH_HINTS = ("spanish", "español", "espanol", "es-", "es_", "sabina", "helena", "laura", "pablo", "raul")
SSFM_CREATE_FOR_WRITE = 3  # SpeechStreamFileMode de SAPI


def _is_spanish_lcid(language: str) -> bool:
    """SAPI da el idioma como LCID hexadecimal (p. ej. "80A" = es-MX); 0x0A es español."""
    try:
        return int(language.split(";")[0], 16) & 0x3FF == 0x0A
    except ValueError:
        return False


def _wpm_to_sapi_rate(rate: int) -> int:
    """Convierte palabras por minuto (estilo pyttsx3) a la escala -10..10 de Windows."""
    return max(-10, min(10, round((rate - 170) / 15)))


class Voice:
    def __init__(self, enabled: bool = True, rate: int = 185):
        self.enabled = enabled
        self.rate = rate
        self._queue: queue.Queue[str] = queue.Queue()
        self._speaking = False
        if enabled:
            target = self._windows_worker if sys.platform == "win32" else self._pyttsx3_worker
            threading.Thread(target=self._safe(target), daemon=True).start()

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

    def wait(self, timeout: float = 60) -> None:
        """Espera a que termine de hablar (útil antes de cerrar el programa)."""
        end = time.time() + timeout
        while self.enabled and (self._speaking or not self._queue.empty()) and time.time() < end:
            time.sleep(0.2)

    def _safe(self, target):
        def run():
            try:
                target()
            except Exception as exc:  # nunca fallar en silencio
                print(f"[voz] La voz dejó de funcionar: {exc}. Solo se mostrará texto.")
            self.enabled = False
        return run

    def _windows_worker(self) -> None:
        import comtypes
        import comtypes.client

        # Cada hilo que usa COM debe inicializarlo; sin esto la voz falla en silencio.
        comtypes.CoInitialize()
        engine = comtypes.client.CreateObject("SAPI.SpVoice")
        voices = engine.GetVoices()
        chosen = None
        for i in range(voices.Count):
            token = voices.Item(i)
            if _is_spanish_lcid(token.GetAttribute("Language") or ""):
                chosen = token
                break
        if chosen is not None:
            engine.Voice = chosen
        engine.Rate = _wpm_to_sapi_rate(self.rate)
        print(f"[voz] Usando la voz de Windows: {engine.Voice.GetDescription()}")
        if chosen is None:
            print("[voz] No tienes una voz en español instalada. Agrégala en Configuración → "
                  "Hora e idioma → Voz → Agregar voces → Español, y reinicia el coach.")

        stream = None
        wav = os.getenv("COACH_VOICE_WAV")  # para pruebas sin altavoces: graba a un archivo
        if wav:
            stream = comtypes.client.CreateObject("SAPI.SpFileStream")
            stream.Open(wav, SSFM_CREATE_FOR_WRITE)
            engine.AudioOutputStream = stream
        while True:
            text = self._queue.get()
            self._speaking = True
            try:
                engine.Speak(" ".join(text.split()))
                if stream is not None:
                    stream.Close()
                    stream = None
            finally:
                self._speaking = False

    def _pyttsx3_worker(self) -> None:
        try:
            import pyttsx3
        except ImportError:
            print("[voz] pyttsx3 no está instalado; solo se mostrará texto. Instala con: pip install pyttsx3")
            return
        # El motor debe crearse en el mismo hilo que lo usa.
        engine = pyttsx3.init()
        engine.setProperty("rate", self.rate)
        for voice in engine.getProperty("voices"):
            ident = f"{voice.id} {voice.name} {getattr(voice, 'languages', '')}".lower()
            if any(h in ident for h in SPANISH_HINTS):
                engine.setProperty("voice", voice.id)
                break
        while True:
            text = self._queue.get()
            self._speaking = True
            try:
                engine.say(text)
                engine.runAndWait()
            finally:
                self._speaking = False
