# main.py
"""
ALERTRAN SGD — API REST + WebSocket
Ejecutar: uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import sys
import asyncio

# Windows + Python 3.12+ usa SelectorEventLoop por defecto,
# que no soporta subprocesos. Playwright los necesita.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from routers import desviaciones, viajes, ws
from services.job_manager import job_manager
from config.constants import CIUDADES, TIPOS_INCIDENCIA

# En producción: ROOT_PATH=/Alertran_SGD (para que /docs funcione correctamente)
_root_path = os.getenv("ROOT_PATH", "")

app = FastAPI(
    title="ALERTRAN SGD API",
    root_path=_root_path,
    description=(
        "API para automatizar la creación de desviaciones e incidencias "
        "en el sistema ALERTRAN de Latin Logistics."
    ),
    version="1.0.0",
)

# CORS — ajustar origins en producción
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(desviaciones.router)
app.include_router(viajes.router)
app.include_router(ws.router)


@app.on_event("startup")
async def _startup():
    # Guarda el loop principal para que job_manager pueda emitir
    # eventos thread-safe desde los threads de Playwright
    job_manager.set_main_loop(asyncio.get_running_loop())


# ── Archivos estáticos (frontend) ────────────────────────────────────────────
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")

#_static = Path(__file__).parent / "static"
#app.mount("/static", StaticFiles(directory=_static), name="static")


# ── Endpoints de utilidad ────────────────────────────────────────────────────

@app.get("/")
async def raiz():
    return FileResponse("static/index.html")


#@app.get("/", tags=["Info"])
#async def raiz():
#    """Sirve el frontend web."""
#    return FileResponse(_static / "index.html")


@app.get("/manifest.json", include_in_schema=False)
async def manifest():
    return FileResponse("static/manifest.json", media_type="application/manifest+json")


@app.get("/config", tags=["Configuración"])
async def obtener_config():
    """Devuelve las listas de ciudades y tipos de incidencia disponibles."""
    return {
        "ciudades": CIUDADES,
        "tipos_incidencia": TIPOS_INCIDENCIA,
    }


@app.get("/jobs", tags=["Jobs"])
async def listar_jobs():
    """Lista todos los jobs activos e históricos de esta sesión."""
    return job_manager.listar_jobs()



@app.get("/server/status", tags=["Server"])
async def server_status():
    """Estado de carga del servidor: jobs activos y tipo."""
    jobs = job_manager.listar_jobs()
    running = [j for j in jobs if j["status"] == "running"]
    return {
        "running": len(running),
        "jobs": [
            {
                "job_id": j["job_id"],
                "tipo":   j["results"].get("_tipo_job", "desconocido"),
                "estado": j["estado_msg"],
            }
            for j in running
        ],
    }


from fastapi.responses import FileResponse

@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    return FileResponse("static/index.html")
