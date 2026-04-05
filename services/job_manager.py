# services/job_manager.py
"""
Gestión de jobs en memoria + broadcast a WebSockets.

Cada job tiene:
  - status:   pending | running | completed | cancelled | error
  - progress: 0-100
  - logs:     lista de strings acumulados
  - results:  dict con resultados finales
  - queue:    asyncio.Queue para eventos nuevos (consume el WS handler)
  - ws_list:  WebSockets suscritos al job
"""
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import WebSocket


class Job:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = "pending"          # pending | running | completed | cancelled | error
        self.progress = 0
        self.estado_msg = ""             # mensaje de estado textual
        self.logs: List[str] = []
        self.results: dict = {}
        self.created_at = datetime.now().isoformat()
        self.finished_at: Optional[str] = None

        # Cola de eventos para WebSocket: cada elemento es un dict JSON
        self.queue: asyncio.Queue = asyncio.Queue()

        # WebSockets activos suscritos a este job
        self.ws_list: List[WebSocket] = []


class JobManager:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        self._main_loop = loop

    # ── Creación ─────────────────────────────────────────────────────────────

    def crear_job(self) -> str:
        """Crea un nuevo job y devuelve su ID."""
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = Job(job_id)
        return job_id

    def obtener_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def listar_jobs(self) -> List[dict]:
        return [self._snapshot(j) for j in self._jobs.values()]

    # ── Emisión de eventos ───────────────────────────────────────────────────

    async def emit_log(self, job_id: str, msg: str):
        await self._emit(job_id, "log", msg)

    async def emit_progreso(self, job_id: str, value: int):
        job = self._jobs.get(job_id)
        if job:
            job.progress = value
        await self._emit(job_id, "progress", value)

    async def emit_estado(self, job_id: str, msg: str):
        job = self._jobs.get(job_id)
        if job:
            job.estado_msg = msg
        await self._emit(job_id, "estado", msg)

    async def emit_guia_procesada(self, job_id: str, guia: str, status: str, resultado: str, nav: str, fecha: str):
        await self._emit(job_id, "guia_procesada", {
            "guia": guia, "status": status, "resultado": resultado,
            "nav": nav, "fecha": fecha
        })

    async def emit_tiempo(self, job_id: str, msg: str):
        await self._emit(job_id, "tiempo", msg)

    async def emit_finalizado(self, job_id: str, results: dict):
        job = self._jobs.get(job_id)
        if job:
            job.status = "completed"
            job.progress = 100
            job.results = results
            job.finished_at = datetime.now().isoformat()
        await self._emit(job_id, "finalizado", results)

    async def emit_cancelado(self, job_id: str, data: dict = None):
        job = self._jobs.get(job_id)
        if job:
            job.status = "cancelled"
            job.finished_at = datetime.now().isoformat()
            if data:
                job.results = data
        await self._emit(job_id, "cancelado", data or {})

    async def emit_error(self, job_id: str, data):
        job = self._jobs.get(job_id)
        if job:
            job.status = "error"
            job.finished_at = datetime.now().isoformat()
            if isinstance(data, dict):
                job.results = data
        await self._emit(job_id, "error", data)

    def marcar_running(self, job_id: str):
        job = self._jobs.get(job_id)
        if job:
            job.status = "running"

    # ── Control de flujo ─────────────────────────────────────────────────────

    def cancelar_job(self, job_id: str):
        """Marca el job para cancelación (el service lo detecta en check_pausa)."""
        job = self._jobs.get(job_id)
        if job:
            job.status = "cancelled"

    def es_cancelado(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        return job is not None and job.status == "cancelled"

    # ── WebSocket ────────────────────────────────────────────────────────────

    async def suscribir_ws(self, job_id: str, ws: WebSocket):
        """Acepta la conexión WS y envía el estado actual del job."""
        await ws.accept()

        job = self._jobs.get(job_id)
        if not job:
            await ws.send_json({"type": "error", "data": "Job no encontrado"})
            await ws.close(code=4004)
            return

        job.ws_list.append(ws)

        # Vaciar la cola de eventos anteriores a esta conexión
        # (el snapshot ya incluye logs y estado actuales)
        while not job.queue.empty():
            try:
                job.queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # Enviar snapshot del estado actual al recién conectado
        await ws.send_json({"type": "snapshot", "data": self._snapshot(job)})

        # Si el job ya terminó, cerrar inmediatamente
        if job.status in ("completed", "cancelled", "error"):
            if ws in job.ws_list:
                job.ws_list.remove(ws)
            return

        # Leer eventos de la cola y reenviarlos al WS
        try:
            while True:
                # Esperar próximo evento (con timeout para detectar WS cerrado)
                try:
                    event = await asyncio.wait_for(job.queue.get(), timeout=30)
                    await ws.send_json(event)
                    if event.get("type") in ("finalizado", "cancelado", "error"):
                        break
                except asyncio.TimeoutError:
                    # Ping para mantener conexión viva
                    await ws.send_json({"type": "ping"})
        except Exception:
            pass
        finally:
            if ws in job.ws_list:
                job.ws_list.remove(ws)

    # ── Internos ─────────────────────────────────────────────────────────────

    def _emit_sync(self, job_id: str, event_type: str, data):
        """Thread-safe: puede llamarse desde cualquier thread."""
        job = self._jobs.get(job_id)
        if not job:
            return
        event = {"type": event_type, "data": data}
        if event_type == "log":
            job.logs.append(data)
        if event_type == "error":
            job.status = "error"
            job.finished_at = datetime.now().isoformat()
            if isinstance(data, dict):
                job.results = data
        elif event_type == "finalizado":
            job.status = "completed"
            job.finished_at = datetime.now().isoformat()
        elif event_type == "cancelado":
            job.status = "cancelled"
            job.finished_at = datetime.now().isoformat()
        if self._main_loop and not self._main_loop.is_closed():
            try:
                # Encola el evento en el loop principal desde cualquier thread
                self._main_loop.call_soon_threadsafe(job.queue.put_nowait, event)
            except RuntimeError:
                pass
        else:
            try:
                job.queue.put_nowait(event)
            except Exception:
                pass

    async def _emit(self, job_id: str, event_type: str, data):
        self._emit_sync(job_id, event_type, data)

    @staticmethod
    def _snapshot(job: Job) -> dict:
        return {
            "job_id": job.job_id,
            "status": job.status,
            "progress": job.progress,
            "estado_msg": job.estado_msg,
            "logs": job.logs,
            "results": job.results,
            "created_at": job.created_at,
            "finished_at": job.finished_at,
        }


# Instancia global (singleton)
job_manager = JobManager()
