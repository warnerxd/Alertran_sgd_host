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

Persistencia:
  - Al finalizar cada job se escribe data/historial.json en disco.
  - Al arrancar se carga el archivo y se purgan jobs más viejos que HIST_TTL_DIAS.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Dict, List, Optional
from fastapi import WebSocket

_TZ = ZoneInfo("America/Bogota")

def _ahora() -> str:
    """Timestamp ISO en hora Colombia (UTC-5)."""
    return datetime.now(_TZ).strftime("%Y-%m-%dT%H:%M:%S")

from config.settings import HIST_TTL_DIAS, HIST_MAX_LOGS

_HIST_FILE = Path("data/historial.json")


class Job:
    def __init__(self, job_id: str):
        self.job_id = job_id
        self.status = "pending"          # pending | running | completed | cancelled | error
        self.progress = 0
        self.estado_msg = ""             # mensaje de estado textual
        self.logs: List[str] = []
        self.results: dict = {}
        self.created_at = _ahora()
        self.finished_at: Optional[str] = None
        # Cola de eventos para WebSocket: cada elemento es un dict JSON
        self.queue: asyncio.Queue = asyncio.Queue()

        # WebSockets activos suscritos a este job
        self.ws_list: List[WebSocket] = []


class JobManager:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None
        self._cargar_historial()

    def set_main_loop(self, loop: asyncio.AbstractEventLoop):
        self._main_loop = loop

    # ── Persistencia ─────────────────────────────────────────────────────────

    def _cargar_historial(self):
        """Carga jobs terminados desde disco y purga los que superan el TTL."""
        try:
            if not _HIST_FILE.exists():
                return
            raw = json.loads(_HIST_FILE.read_text(encoding="utf-8"))
            limite = datetime.now(_TZ) - timedelta(days=HIST_TTL_DIAS)
            for snap in raw:
                # Purgar por TTL
                try:
                    created = datetime.fromisoformat(snap.get("created_at", ""))
                    # compatibilidad: si es naive, asumir hora Colombia
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=_TZ)
                    if created < limite:
                        continue
                except Exception:
                    pass

                job = Job(snap["job_id"])
                job.status      = snap.get("status", "completed")
                job.progress    = snap.get("progress", 100)
                job.estado_msg  = snap.get("estado_msg", "")
                job.logs        = snap.get("logs", [])
                job.results     = snap.get("results", {})
                job.created_at  = snap.get("created_at", job.created_at)
                job.finished_at = snap.get("finished_at")
                self._jobs[job.job_id] = job
        except Exception:
            pass  # historial corrupto o inexistente — arrancar limpio

    def _guardar_historial(self):
        """Escribe todos los jobs terminados a disco (solo los finalizados)."""
        try:
            _HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
            terminados = [
                j for j in self._jobs.values()
                if j.status in ("completed", "cancelled", "error")
            ]
            snapshots = []
            for j in terminados:
                snap = self._snapshot(j)
                # Limitar logs para no inflar el archivo
                snap["logs"] = snap["logs"][-HIST_MAX_LOGS:]
                snapshots.append(snap)
            _HIST_FILE.write_text(
                json.dumps(snapshots, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def purgar_ttl(self):
        """Elimina de memoria los jobs terminados que superan el TTL."""
        limite = datetime.now(_TZ) - timedelta(days=HIST_TTL_DIAS)
        a_borrar = []
        for job_id, job in self._jobs.items():
            if job.status not in ("completed", "cancelled", "error"):
                continue
            try:
                created = datetime.fromisoformat(job.created_at)
                if created.tzinfo is None:
                    created = created.replace(tzinfo=_TZ)
                if created < limite:
                    a_borrar.append(job_id)
            except Exception:
                pass
        for job_id in a_borrar:
            del self._jobs[job_id]
        if a_borrar:
            self._guardar_historial()

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
            job.finished_at = _ahora()
        await self._emit(job_id, "finalizado", results)
        self._guardar_historial()

    async def emit_cancelado(self, job_id: str, data: dict = None):
        job = self._jobs.get(job_id)
        if job:
            job.status = "cancelled"
            job.finished_at = _ahora()
            if data:
                job.results = data
        await self._emit(job_id, "cancelado", data or {})
        self._guardar_historial()

    async def emit_error(self, job_id: str, data):
        job = self._jobs.get(job_id)
        if job:
            job.status = "error"
            job.finished_at = _ahora()
            if isinstance(data, dict):
                job.results = data
        await self._emit(job_id, "error", data)
        self._guardar_historial()

    def set_meta(self, job_id: str, meta: dict):
        """Almacena metadatos de contexto en job.results al inicio del job."""
        job = self._jobs.get(job_id)
        if job:
            job.results = {**meta, **job.results}

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
            job.finished_at = _ahora()
            if isinstance(data, dict):
                job.results = data
        elif event_type == "finalizado":
            job.status = "completed"
            job.finished_at = _ahora()
        elif event_type == "cancelado":
            job.status = "cancelled"
            job.finished_at = _ahora()
        if self._main_loop and not self._main_loop.is_closed():
            try:
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
