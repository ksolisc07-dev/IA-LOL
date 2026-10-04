# IA-LOL: coach de IA para tus rankeds de League of Legends

Un coach que te acompaña **por voz** durante tus partidas clasificatorias. Te dice qué estás haciendo mal, te recomienda qué armarte según el equipo enemigo y, al terminar, te da un resumen con tus errores principales.

## Qué hace

**Durante la partida** (`python -m lol_coach`):
- **Plan de juego al empezar**: cómo jugar contra tu rival de línea, tu condición de victoria y qué build armarte contra esa composición.
- **Alertas instantáneas** (no gastan IA):
  - farmeo bajo (CS/min) o ir por detrás de tu rival en súbditos o niveles,
  - oro acumulado sin gastar ("vuelve a base"),
  - rachas de muertes,
  - visión baja,
  - el dragón o el Barón aparecen en 1 minuto,
  - el enemigo tiene Barón.
- **Cuando mueres**: la IA te explica qué hiciste mal y qué comprar con tu oro.
- **Revisión periódica** (cada 4 min): el consejo más importante para los próximos minutos.
- **Preguntas en vivo**: escribe en la consola, por ejemplo "¿qué me armo contra Zed?" o "¿voy a dragón?", y te responde por voz.
- **Resumen al terminar**: qué hiciste bien, tus 2 errores principales y qué practicar.

**Después de jugar** (`python -m lol_coach analizar`): descarga tus últimas rankeds con la API de Riot y genera un informe con tus errores recurrentes, recomendaciones de build y de campeones, y un plan de práctica.

## Cómo funciona

Lee la **Live Client Data API** oficial que el propio juego expone en `https://127.0.0.1:2999` mientras hay una partida en curso. Es la misma fuente que usan apps como Porofessor o Blitz. Solo lee datos que ya ves en pantalla (marcador, objetos, eventos) y **no toca el cliente ni automatiza nada**. Las alertas salen de reglas locales y los consejos los genera Claude (Anthropic). La voz usa el sintetizador de tu sistema operativo (en Windows, SAPI) mediante `pyttsx3`.

## Instalación fácil (Windows, sin Python)

1. Descarga **`LoLCoach-Instalador.exe`** desde la sección *Releases* del repositorio (o desde *Actions → Instalador de Windows → Artifacts*).
2. Ábrelo y sigue los pasos. No pide permisos de administrador y crea un acceso directo en el escritorio.
3. Abre **LoL Coach IA**. La primera vez te pide tu API key de Anthropic y la guarda.
4. Elige en el menú: coach en vivo, demo o análisis de tus rankeds.

> Como el programa no está firmado digitalmente, Windows puede mostrar "Windows protegió tu PC". Pulsa **Más información → Ejecutar de todas formas**.

## Instalación con Python (alternativa)

Doble clic en **`instalar.bat`**: instala Python (si falta) y las dependencias, te pide la API key y crea el acceso directo "LoL Coach IA" en el escritorio.

## Instalación manual (Windows)

1. Instala [Python 3.10+](https://www.python.org/downloads/) y marca "Add Python to PATH".
2. En una terminal, dentro de esta carpeta:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. Copia `.env.example` a `.env` y pon tu `ANTHROPIC_API_KEY` (la obtienes en https://console.anthropic.com).
4. Para la voz en español: *Configuración → Hora e idioma → Voz → Agregar voces → Español*. El coach elige automáticamente una voz en español si hay alguna instalada.

## Uso

```bash
# Prueba sin abrir el juego (usa una partida de ejemplo)
python -m lol_coach demo

# Coach en vivo: ábrelo antes o durante la partida y déjalo corriendo
python -m lol_coach

# Solo texto, sin voz
python -m lol_coach --sin-voz

# Analiza tus últimas 10 rankeds (requiere RIOT_API_KEY en el .env)
python -m lol_coach analizar --riot-id "TuNombre#LAN" --plataforma la1 --partidas 10 --salida informe.md
```

Plataformas: `la1` (LAN), `la2` (LAS), `na1`, `br1`, `euw1`, `eun1`, `kr`, `jp1`, `oc1`, etc.

Consejo: juega en modo **ventana sin bordes** para poder escribir preguntas en la consola sin minimizar el juego.

## Configuración

Todas las opciones están en `.env.example`:
- `COACH_MODEL`: modelo de IA (por defecto `claude-opus-5-5`).
- `COACH_LIVE_EFFORT`: nivel de razonamiento en partida. `low` responde más rápido.
- `COACH_REVIEW_INTERVAL`: segundos entre revisiones periódicas.
- `COACH_VOICE` y `COACH_VOICE_RATE`: activar la voz y su velocidad.

## Estructura

| Archivo | Qué hace |
|---|---|
| `lol_coach/live_client.py` | Lee los datos de la partida en vivo |
| `lol_coach/game_state.py` | Interpreta los datos (tú, tu rival de línea, los equipos, los eventos) |
| `lol_coach/analyzer.py` | Reglas de alertas instantáneas |
| `lol_coach/coach.py` | Prompts y llamadas a Claude |
| `lol_coach/voice.py` | Texto a voz |
| `lol_coach/riot_api.py`, `postgame.py` | Análisis de partidas pasadas |
| `lol_coach/cli.py` | Comandos y bucle principal |

## Pruebas

```bash
pip install pytest
python -m pytest
```
