# services/base_service.py
"""
Clase base para todos los servicios — lógica compartida de Playwright
sin dependencias de Qt/PySide6.

Reemplaza workers/base_worker.py.
Los emit_* delegan en job_manager en lugar de señales Qt.
"""
import asyncio
import sys
import threading
from datetime import timedelta
import time

from utils.file_utils import FileUtils
from services.job_manager import JobManager


class BaseService:
    """Clase base para DesviacionesService y ViajesService."""

    def __init__(self, job_id: str, jm: JobManager):
        self.job_id = job_id
        self.jm = jm

        # Estado de control
        self.procesando = True
        self.cancelado  = False
        self.pausado    = False
        self.tiempo_inicio = None

        # Recursos de Playwright
        self.pages    = []
        self.browsers = []
        self.contexts = []

        # Utilidades
        self.carpeta_descargas = FileUtils.obtener_carpeta_descargas()
        self.file_utils        = FileUtils()

    # ── Helpers de emisión ───────────────────────────────────────────────────

    async def log(self, msg: str):
        await self.jm.emit_log(self.job_id, msg)

    async def progreso(self, value: int):
        await self.jm.emit_progreso(self.job_id, value)

    async def estado(self, msg: str):
        await self.jm.emit_estado(self.job_id, msg)

    async def guia_procesada(self, guia: str, status: str, resultado: str, nav: str, fecha: str):
        await self.jm.emit_guia_procesada(self.job_id, guia, status, resultado, nav, fecha)

    async def tiempo_restante(self, msg: str):
        await self.jm.emit_tiempo(self.job_id, msg)

    async def error(self, msg: str):
        await self.jm.emit_error(self.job_id, msg)

    # ── Control de flujo ─────────────────────────────────────────────────────

    def iniciar(self):
        """Lanza ejecutar() en un thread dedicado con ProactorEventLoop (necesario para Playwright en Windows)."""
        def _run():
            if sys.platform == "win32":
                loop = asyncio.ProactorEventLoop()
            else:
                loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.ejecutar())
            except Exception as exc:
                # Si ejecutar() crashea fuera de su propio try-except, emitir error
                self.jm._emit_sync(self.job_id, "error", f"Error inesperado: {exc}")
            finally:
                loop.close()

        threading.Thread(target=_run, daemon=True).start()

    def cancelar(self):
        self.cancelado  = True
        self.procesando = False
        self.pausado    = False

    def pausar(self):
        self.pausado = True

    def reanudar(self):
        self.pausado = False

    async def check_pausa(self):
        """Espera mientras el proceso esté pausado o verifica cancelación externa."""
        # Chequear también cancelación desde el job_manager
        if self.jm.es_cancelado(self.job_id):
            self.cancelar()
        while self.pausado and not self.cancelado:
            await asyncio.sleep(0.5)
            if self.jm.es_cancelado(self.job_id):
                self.cancelar()

    # ── Métodos de navegación compartidos ───────────────────────────────────

    async def esperar_overlay(self, page, timeout=10000):
        """Espera a que desaparezca el overlay de carga."""
        try:
            await page.wait_for_selector(
                "#capa_selector", state="hidden", timeout=timeout
            )
        except Exception:
            pass
        await asyncio.sleep(0.3)

    async def verificar_pagina_activa(self, page) -> bool:
        try:
            await page.title()
            return True
        except Exception:
            return False

    async def hacer_login(self, page, nav_idx: int) -> bool:
        try:
            await self.log(f"🔐 [Nav{nav_idx}] Iniciando sesión...")
            await page.fill('input[name="j_username"]', self.usuario)
            await asyncio.sleep(0.2)
            await page.fill('input[name="j_password"]', self.password)
            await asyncio.sleep(0.2)
            await page.get_by_role("button", name="Aceptar").click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)
            if await page.locator('input[name="j_username"]').count() > 0:
                await self.log(f"❌ [Nav{nav_idx}] Login fallido — credenciales incorrectas")
                return False
            await self.log(f"✅ [Nav{nav_idx}] Sesión iniciada correctamente")
            return True
        except Exception as e:
            await self.log(f"❌ [Nav{nav_idx}] Error login: {str(e)}")
            return False

    async def calcular_tiempo_restante(self, procesadas: int, total: int):
        """Emite tiempo restante estimado + velocidad en guías/min."""
        if self.tiempo_inicio and procesadas > 0:
            elapsed = time.time() - self.tiempo_inicio
            if elapsed > 0:
                velocidad = procesadas / elapsed
                restantes = total - procesadas
                segundos_restantes = restantes / velocidad if velocidad > 0 else 0
                tiempo_str = str(timedelta(seconds=int(segundos_restantes)))
                guias_min  = round(velocidad * 60, 1)
                await self.tiempo_restante(
                    f"⏱️ Restante: {tiempo_str}  |  🚀 {guias_min} guías/min"
                )
