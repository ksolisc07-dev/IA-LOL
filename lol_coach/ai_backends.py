"""Formas de conectar con Claude.

- ClaudeSubscription: usa Claude Code con tu suscripción Claude Pro/Max (sin API key).
- AnthropicAPI: usa una API key de pago de console.anthropic.com.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

import anthropic


class AIError(Exception):
    pass


class ClaudeSubscription:
    """Llama a `claude -p` (Claude Code), que usa la sesión iniciada con tu cuenta de Claude."""

    name = "tu suscripción de Claude (Claude Code)"

    def __init__(self, executable: str, model: str = "sonnet", timeout: float = 90):
        self.executable = executable
        self.model = model
        self.timeout = timeout
        # Carpeta vacía para que Claude Code no lea archivos de proyecto.
        self.workdir = tempfile.mkdtemp(prefix="lolcoach_")

    def ask(self, system: str, prompt: str, effort: str, max_tokens: int) -> str:
        # En una sola línea: los argumentos con saltos de línea fallan si "claude" es un .cmd en Windows.
        system = " ".join(system.split())
        cmd = [self.executable, "-p", "--system-prompt", system, "--tools", "",
               "--model", self.model, "--effort", effort, "--output-format", "text",
               "--no-session-persistence"]
        env = dict(os.environ)
        # Si hubiera una API key en el entorno, Claude Code la usaría en vez de la suscripción.
        env.pop("ANTHROPIC_API_KEY", None)
        try:
            result = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                timeout=self.timeout, cwd=self.workdir, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AIError(f"Claude Code no respondió: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[:300]
            raise AIError(f"Claude Code falló ({detail}). ¿Iniciaste sesión ejecutando 'claude'?")
        return result.stdout.strip()


class AnthropicAPI:
    name = "la API de Anthropic"

    def __init__(self, model: str, client: anthropic.Anthropic | None = None):
        self.client = client or anthropic.Anthropic()
        self.model = model

    def ask(self, system: str, prompt: str, effort: str, max_tokens: int) -> str:
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                # Si el modelo rechaza la petición, la API reintenta automáticamente con otro modelo.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIError as exc:
            raise AIError(str(exc)) from exc
        if response.stop_reason == "refusal":
            return "No pude generar un consejo para esta situación."
        return "".join(b.text for b in response.content if b.type == "text").strip()


def find_claude_code() -> str | None:
    found = shutil.which("claude")
    if found:
        return found
    # Ubicaciones habituales en Windows, por si aún no están en el PATH.
    home = os.path.expanduser("~")
    local = os.getenv("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
    for candidate in (os.path.join(home, ".local", "bin", "claude.exe"),
                      os.path.join(home, ".local", "bin", "claude"),
                      # Instalación con winget
                      os.path.join(local, "Microsoft", "WinGet", "Links", "claude.exe")):
        if os.path.isfile(candidate):
            return candidate
    return None


def detect_backend(mode: str, api_model: str, subscription_model: str):
    """Elige cómo conectar con la IA. Devuelve None para el modo gratuito sin IA."""
    mode = mode.lower()
    if mode in ("gratis", "free", "off"):
        return None
    if mode in ("auto", "api") and os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicAPI(api_model)
    if mode in ("auto", "suscripcion", "claude-code"):
        exe = find_claude_code()
        if exe:
            return ClaudeSubscription(exe, subscription_model)
    return None
