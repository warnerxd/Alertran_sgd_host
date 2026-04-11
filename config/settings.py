# config/settings.py
"""
Configuraciones generales de tiempo y proceso.
Al importar, intenta leer overrides desde ~/.alertran/settings.json
para que los cambios hechos en el diálogo de configuración avanzada
se apliquen sin tocar este archivo.
"""
import json
from pathlib import Path

# ── Cargar overrides guardados por el usuario ────────────────────────────────
_FILE   = Path.home() / ".alertran" / "settings.json"
_saved: dict = {}
try:
    if _FILE.exists():
        with open(_FILE, "r", encoding="utf-8") as _f:
            _saved = json.load(_f)
except Exception:
    pass

# ── Tiempos de espera (en milisegundos) ──────────────────────────────────────
TIEMPO_ESPERA_RECUPERACION    = int(_saved.get("TIEMPO_ESPERA_RECUPERACION",    6000))
TIEMPO_ESPERA_NAVEGACION      = int(_saved.get("TIEMPO_ESPERA_NAVEGACION",      5000))
TIEMPO_ESPERA_CLICK           = int(_saved.get("TIEMPO_ESPERA_CLICK",           2000))
TIEMPO_ESPERA_CARGA           = int(_saved.get("TIEMPO_ESPERA_CARGA",           8000))
TIEMPO_ESPERA_ENTRE_GUIAS     = int(_saved.get("TIEMPO_ESPERA_ENTRE_GUIAS",     2000))
TIEMPO_ESPERA_INGRESO_CODIGOS = int(_saved.get("TIEMPO_ESPERA_INGRESO_CODIGOS", 1500))
TIEMPO_ESPERA_VOLVER          = int(_saved.get("TIEMPO_ESPERA_VOLVER",          8000))

# ── Configuración de proceso ──────────────────────────────────────────────────
MAX_REINTENTOS    = int(_saved.get("MAX_REINTENTOS", 3))
MAX_NAVEGADORES   = 8
ORIGEN_INCIDENCIA = _saved.get("ORIGEN_INCIDENCIA", "018")  # Código de origen para incidencias
URL_ALERTRAN      = "https://alertran.latinlogistics.com.co/padua/inicio.do"

# ── Historial ─────────────────────────────────────────────────────────────────
HIST_TTL_DIAS = int(_saved.get("HIST_TTL_DIAS", 30))   # días antes de purgar jobs antiguos
HIST_MAX_LOGS = int(_saved.get("HIST_MAX_LOGS", 1000))  # máx líneas de log guardadas por job
