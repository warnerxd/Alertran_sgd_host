# utils/history_storage.py
"""
Persistencia del historial de guías procesadas entre sesiones.
Guarda y carga desde ~/.alertran/historial.json
"""
import json
from pathlib import Path
from datetime import datetime


class HistoryStorage:
    """Guarda y recupera el historial completo en disco."""

    _FILE       = Path.home() / ".alertran" / "historial.json"
    MAX_REGISTROS = 50_000   # tope para no crecer indefinidamente

    @classmethod
    def guardar(cls, datos: list) -> None:
        """
        Persiste la lista de tuplas (guia, estado, resultado, navegador, fecha).
        Si hay más de MAX_REGISTROS, conserva los más recientes.
        """
        try:
            cls._FILE.parent.mkdir(parents=True, exist_ok=True)
            registros = [
                {
                    "guia":      d[0],
                    "estado":    d[1],
                    "resultado": d[2],
                    "navegador": d[3],
                    "fecha":     d[4],
                }
                for d in datos[-cls.MAX_REGISTROS:]
            ]
            with open(cls._FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version":  1,
                        "guardado": datetime.now().isoformat(),
                        "total":    len(registros),
                        "datos":    registros,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )
        except Exception:
            pass   # nunca interrumpir el proceso por un fallo de escritura

    @classmethod
    def cargar(cls) -> list:
        """
        Devuelve lista de tuplas; lista vacía si no existe o hay error.
        """
        try:
            if not cls._FILE.exists():
                return []
            with open(cls._FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [
                (
                    d["guia"],
                    d["estado"],
                    d["resultado"],
                    d["navegador"],
                    d["fecha"],
                )
                for d in data.get("datos", [])
            ]
        except Exception:
            return []

    @classmethod
    def limpiar(cls) -> None:
        """Elimina el archivo de historial."""
        try:
            if cls._FILE.exists():
                cls._FILE.unlink()
        except Exception:
            pass
