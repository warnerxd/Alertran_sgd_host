# routers/ws.py
import asyncio
from fastapi import APIRouter, WebSocket
from services.job_manager import job_manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_status(websocket: WebSocket):
    """
    Endpoint de estado del servidor.
    Envía un snapshot del estado general y mantiene la conexión viva con pings.
    Útil para validar conectividad WSS sin necesitar un job_id.
    """
    await websocket.accept()
    try:
        jobs = job_manager.listar_jobs()
        running = [j for j in jobs if j["status"] == "running"]
        await websocket.send_json({
            "type": "server_status",
            "data": {
                "status": "ok",
                "jobs_activos": len(running),
                "jobs_total": len(jobs),
            },
        })
        # Mantener conexión con pings hasta que el cliente cierre
        while True:
            await asyncio.sleep(30)
            await websocket.send_json({"type": "ping"})
    except Exception:
        pass


@router.websocket("/ws/{job_id}")
async def websocket_job(websocket: WebSocket, job_id: str):
    """
    Conectarse a este WebSocket para recibir eventos en tiempo real de un job.

    Tipos de mensajes que recibirás:
    - `snapshot`      — estado completo al conectarse
    - `log`           — línea de log nueva
    - `progress`      — porcentaje 0-100
    - `estado`        — mensaje de estado textual
    - `guia_procesada`— resultado de una guía individual
    - `tiempo`        — ETA o tiempo transcurrido
    - `finalizado`    — job completado (con resultados)
    - `cancelado`     — job cancelado
    - `error`         — error fatal
    - `ping`          — keepalive cada 30s
    """
    await job_manager.suscribir_ws(job_id, websocket)
