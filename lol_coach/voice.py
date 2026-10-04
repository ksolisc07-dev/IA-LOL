"""Salida por voz (texto a voz) en un hilo aparte para no bloquear el bucle.

En Windows se usa el motor de voz del sistema (System.Speech, el mismo del Narrador)
a través de un proceso de PowerShell que se mantiene abierto. En otros sistemas, pyttsx3.
"""

from __future__ import annotations

import base64
import queue
import subprocess
import sys
import threading
import time

SPANISH_HINTS = ("spanish", "español", "espanol", "es-", "es_", "sabina", "helena", "laura", "pablo", "raul")

# El texto llega en base64 (UTF-8) para no depender de la codificación de la consola.
_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($env:COACH_VOICE_WAV) { $s.SetOutputToWaveFile($env:COACH_VOICE_WAV) } else { $s.SetOutputToDefaultAudioDevice() }
$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es*' } | Select-Object -First 1
if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
$s.Rate = __RATE__
[Console]::Out.WriteLine('VOZ|' + $s.Voice.Name + '|' + $s.Voice.Culture.Name)
[Console]::Out.Flush()
while ($null -ne ($l = [Console]::In.ReadLine())) {
    if ($l) { $s.Speak([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($l))) }
    [Console]::Out.WriteLine('OK')
    [Console]::Out.Flush()
}
"""


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
        script = _PS_SCRIPT.replace("__RATE__", str(_wpm_to_sapi_rate(self.rate)))
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", encoded],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        header = proc.stdout.readline().strip()
        if not header.startswith("VOZ|"):
            raise RuntimeError(proc.stderr.read().strip()[:300] or "no se pudo iniciar la voz de Windows")
        _, name, culture = (header.split("|") + ["", ""])[:3]
        print(f"[voz] Usando la voz de Windows: {name} ({culture})")
        if not culture.lower().startswith("es"):
            print("[voz] No tienes una voz en español instalada. Agrégala en Configuración → "
                  "Hora e idioma → Voz → Agregar voces → Español, y reinicia el coach.")
        while True:
            text = self._queue.get()
            self._speaking = True
            try:
                line = base64.b64encode(" ".join(text.split()).encode("utf-8")).decode("ascii")
                proc.stdin.write(line + "\n")
                proc.stdin.flush()
                if proc.stdout.readline().strip() != "OK":
                    raise RuntimeError(proc.stderr.read().strip()[:300] or "el proceso de voz se cerró")
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
