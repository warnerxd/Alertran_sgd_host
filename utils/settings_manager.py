# utils/settings_manager.py
"""
Gestión de configuraciones persistentes de la aplicación.
Almacena en ~/.alertran/settings.json y expone un singleton SettingsManager.
"""
import json
from pathlib import Path

# Valores por defecto (coinciden con config/settings.py)
_DEFAULTS: dict = {
    "TIEMPO_ESPERA_RECUPERACION":  4000,
    "TIEMPO_ESPERA_NAVEGACION":    3000,
    "TIEMPO_ESPERA_CLICK":         2000,
    "TIEMPO_ESPERA_CARGA":         8000,
    "TIEMPO_ESPERA_ENTRE_GUIAS":   2000,
    "TIEMPO_ESPERA_INGRESO_CODIGOS": 1500,
    "TIEMPO_ESPERA_VOLVER":        5000,
    "MAX_REINTENTOS":              3,
    # credenciales
    "recordar_usuario":  False,
    "usuario_guardado":  "",
    # UI layout
    "splitter_sizes":    [570, 830],
}


class SettingsManager:
    """
    Singleton para leer/escribir configuración.
    Uso:  s = SettingsManager.get_instance()
          s.get("MAX_REINTENTOS")   →  3
          s.set("MAX_REINTENTOS", 5); s.save()
    """

    _FILE:     Path              = Path.home() / ".alertran" / "settings.json"
    _instance: "SettingsManager" = None   # type: ignore[assignment]

    def __init__(self) -> None:
        self._data: dict = _DEFAULTS.copy()
        self._load()

    # ── Singleton ────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "SettingsManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            if self._FILE.exists():
                with open(self._FILE, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Cargar claves conocidas con prioridad
                for key in _DEFAULTS:
                    if key in saved:
                        self._data[key] = saved[key]
                # Cargar claves extra (ej. checkpoints) que no están en _DEFAULTS
                for key, value in saved.items():
                    if key not in _DEFAULTS:
                        self._data[key] = value
        except Exception:
            pass

    def save(self) -> None:
        try:
            self._FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self._FILE, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Acceso ───────────────────────────────────────────────────────────────

    def get(self, key: str, default=None):
        """Devuelve el valor de la clave; si no existe usa default o el valor por defecto."""
        return self._data.get(
            key, default if default is not None else _DEFAULTS.get(key)
        )

    def set(self, key: str, value) -> None:
        self._data[key] = value
