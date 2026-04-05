# routers/ws.py
from fastapi import APIRouter, WebSocket
from services.job_manager import job_manager

router = APIRouter(tags=["WebSocket"])


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
