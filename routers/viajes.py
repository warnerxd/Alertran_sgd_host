# routers/viajes.py
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.viajes import ViajesRequest, JobCreado, JobEstado, CancelarResponse
from services.viajes_service import ViajesService
from services.job_manager import job_manager

router = APIRouter(prefix="/viajes", tags=["Viajes"])


@router.post("/procesar", response_model=JobCreado, summary="Iniciar procesamiento de un viaje")
async def procesar_viaje(
    request: ViajesRequest,
):
    """
    Busca la carta porte en ALERTRAN (funcionalidad 7.3.2) y crea desviaciones
    para todos los envíos con paginación automática.
    Devuelve un `job_id` para consultar el estado o conectarse por WebSocket.
    """
    job_id  = job_manager.crear_job()
    service = ViajesService(
        job_id=job_id,
        jm=job_manager,
        usuario=request.usuario,
        password=request.password,
        ciudad=request.ciudad,
        numero_viaje=request.numero_viaje,
        codigo_desviacion=request.codigo_desviacion,
        observaciones=request.observaciones,
        num_navegadores=request.num_navegadores,
        headless=request.headless,
        pagina_inicio=request.pagina_inicio,
    )
    service.iniciar()
    return JobCreado(job_id=job_id)


@router.get("/estado/{job_id}", response_model=JobEstado, summary="Consultar estado del job")
async def estado_job(job_id: str):
    job = job_manager.obtener_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return JobEstado(
        job_id=job.job_id,
        status=job.status,
        progress=job.progress,
        estado_msg=job.estado_msg,
        logs=job.logs,
        results=job.results,
        created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get("/checkpoint/{numero_viaje}", summary="Leer checkpoint guardado para un viaje")
async def leer_checkpoint(numero_viaje: str):
    """
    Devuelve el checkpoint guardado en disco para el viaje indicado.
    Si no existe o no coincide el número, devuelve `tiene_checkpoint: false`.
    """
    import re
    viaje_safe = re.sub(r'[^\w\-]', '_', str(numero_viaje))
    p = Path.home() / ".alertran" / "checkpoints" / f"viaje_{viaje_safe}.json"
    if p.exists():
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
            return {
                "tiene_checkpoint": True,
                "pagina_completada": int(data["pagina_completada"]),
                "timestamp": data.get("timestamp"),
            }
        except Exception:
            pass
    return {"tiene_checkpoint": False, "pagina_completada": 0, "timestamp": None}


@router.post("/cancelar/{job_id}", response_model=CancelarResponse, summary="Cancelar un job en ejecución")
async def cancelar_job(job_id: str):
    job = job_manager.obtener_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"El job ya está en estado '{job.status}'")
    job_manager.cancelar_job(job_id)
    return CancelarResponse(job_id=job_id, mensaje="Señal de cancelación enviada")
