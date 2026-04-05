# routers/desviaciones.py
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional
import tempfile, os

from schemas.desviaciones import DesviacionesRequest, JobCreado, JobEstado, CancelarResponse
from services.desviaciones_service import DesviacionesService
from services.job_manager import job_manager

router = APIRouter(prefix="/desviaciones", tags=["Desviaciones"])


@router.post("/procesar", response_model=JobCreado, summary="Iniciar procesamiento de guías desde lista JSON")
async def procesar_desviaciones(
    request: DesviacionesRequest,
):
    """
    Inicia el procesamiento de guías usando una lista en el body JSON.
    Devuelve un `job_id` para consultar el estado o conectarse por WebSocket.
    """
    job_id  = job_manager.crear_job()
    service = DesviacionesService(
        job_id=job_id,
        jm=job_manager,
        usuario=request.usuario,
        password=request.password,
        ciudad=request.ciudad,
        tipo=request.tipo,
        ampliacion=request.ampliacion,
        excel_path=None,
        num_navegadores=request.num_navegadores,
        guias_list=request.guias_list,
        headless=request.headless,
        preview=request.preview,
    )
    service.iniciar()
    return JobCreado(job_id=job_id)


@router.post("/procesar-excel", response_model=JobCreado, summary="Iniciar procesamiento de guías desde archivo Excel")
async def procesar_desviaciones_excel(
    archivo: UploadFile = File(..., description="Archivo Excel con guías en columna A"),
    usuario: str = Form(...),
    password: str = Form(...),
    ciudad: str = Form(...),
    tipo: str = Form(...),
    ampliacion: str = Form(default=""),
    num_navegadores: int = Form(default=1),
    headless: bool = Form(default=True),
):
    """
    Sube un archivo Excel y procesa las guías de la columna A.
    """
    # Guardar Excel en archivo temporal
    suffix = os.path.splitext(archivo.filename)[1] or ".xlsx"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        contenido = await archivo.read()
        tmp.write(contenido)
        tmp_path = tmp.name

    job_id  = job_manager.crear_job()
    service = DesviacionesService(
        job_id=job_id,
        jm=job_manager,
        usuario=usuario,
        password=password,
        ciudad=ciudad,
        tipo=tipo,
        ampliacion=ampliacion,
        excel_path=tmp_path,
        num_navegadores=num_navegadores,
        guias_list=None,
        headless=headless,
    )

    import asyncio, sys, threading

    def _ejecutar_y_limpiar():
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        else:
            loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(service.ejecutar())
        finally:
            loop.close()
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    threading.Thread(target=_ejecutar_y_limpiar, daemon=True).start()
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


@router.post("/cancelar/{job_id}", response_model=CancelarResponse, summary="Cancelar un job en ejecución")
async def cancelar_job(job_id: str):
    job = job_manager.obtener_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    if job.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"El job ya está en estado '{job.status}'")
    job_manager.cancelar_job(job_id)
    return CancelarResponse(job_id=job_id, mensaje="Señal de cancelación enviada")
