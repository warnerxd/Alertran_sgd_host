# workers/base_worker.py
"""
Clase base para todos los workers — centraliza lógica común:
  - hacer_login, esperar_overlay, verificar_pagina_activa
  - calcular_tiempo_restante con velocidad (guías/min)
  - Control de flujo: cancelar / pausar / reanudar
"""
from PySide6.QtCore import QThread
import asyncio
from datetime import timedelta
import time

from models.signals import ProcesoSenales
from utils.file_utils import FileUtils


class BaseWorker(QThread):
    """Clase base para ProcesoThread y DesviacionViajesThread."""

    def __init__(self):
        super().__init__()
        self.senales = ProcesoSenales()

        # Estado de control
        self.procesando = True
        self.cancelado  = False
        self.pausado    = False
        self.tiempo_inicio = None

        # Recursos de playwright
        self.pages    = []
        self.browsers = []
        self.contexts = []

        # Utilidades
        self.carpeta_descargas = FileUtils.obtener_carpeta_descargas()
        self.file_utils        = FileUtils()

    # ── Control de flujo ────────────────────────────────────────────────────

    def cancelar(self):
        """Detiene el proceso definitivamente."""
        self.cancelado  = True
        self.procesando = False
        self.pausado    = False   # desbloquea check_pausa si estaba esperando

    def pausar(self):
        """Pausa el proceso hasta llamar a reanudar()."""
        self.pausado = True

    def reanudar(self):
        """Reanuda el proceso pausado."""
        self.pausado = False

    async def check_pausa(self):
        """Espera activamente mientras el proceso esté pausado."""
        while self.pausado and not self.cancelado:
            await asyncio.sleep(0.5)

    # ── Métodos compartidos de navegación ───────────────────────────────────

    async def esperar_overlay(self, page, timeout=10000):
        """Espera a que desaparezca el overlay de carga."""
        try:
            await page.wait_for_selector(
                "#capa_selector", state="hidden", timeout=timeout
            )
        except Exception:
            pass
        await asyncio.sleep(0.3)

    async def verificar_pagina_activa(self, page):
        """Devuelve True si la página sigue respondiendo."""
        try:
            await page.title()
            return True
        except Exception:
            return False

    async def hacer_login(self, page, nav_idx):
        """Realiza el login en ALERTRAN usando self.usuario / self.password."""
        try:
            self.senales.log.emit(f"🔐 [Nav{nav_idx}] Iniciando sesión...")
            await page.fill('input[name="j_username"]', self.usuario)
            await asyncio.sleep(0.2)
            await page.fill('input[name="j_password"]', self.password)
            await asyncio.sleep(0.2)
            await page.get_by_role("button", name="Aceptar").click()
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(1)
            if await page.locator('input[name="j_username"]').count() > 0:
                self.senales.log.emit(
                    f"❌ [Nav{nav_idx}] Login fallido — credenciales incorrectas"
                )
                return False
            self.senales.log.emit(f"✅ [Nav{nav_idx}] Sesión iniciada correctamente")
            return True
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error login: {str(e)}")
            return False

    async def calcular_tiempo_restante(self, procesadas, total):
        """Emite tiempo restante estimado + velocidad en guías/min."""
        if self.tiempo_inicio and procesadas > 0:
            elapsed = time.time() - self.tiempo_inicio
            if elapsed > 0:
                velocidad = procesadas / elapsed          # guías/seg
                restantes = total - procesadas
                segundos_restantes = restantes / velocidad if velocidad > 0 else 0
                tiempo_str = str(timedelta(seconds=int(segundos_restantes)))
                guias_min  = round(velocidad * 60, 1)
                self.senales.tiempo_restante.emit(
                    f"⏱️ Restante: {tiempo_str}  |  🚀 {guias_min} guías/min"
                )
