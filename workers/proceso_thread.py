# workers/proceso_thread.py
"""
Thread principal para el procesamiento con múltiples navegadores
"""
from datetime import datetime, timedelta
import asyncio
import time
import random
from playwright.async_api import async_playwright
from typing import List, Union
from pathlib import Path

from workers.base_worker import BaseWorker
from config.settings import (
    MAX_REINTENTOS, TIEMPO_ESPERA_CLICK, TIEMPO_ESPERA_NAVEGACION,
    TIEMPO_ESPERA_INGRESO_CODIGOS, TIEMPO_ESPERA_VOLVER, URL_ALERTRAN,
    ORIGEN_INCIDENCIA
)

class ProcesoThread(BaseWorker):
    """Thread principal para el procesamiento"""

    def __init__(self, usuario, password, ciudad, tipo, ampliacion, excel_path, num_navegadores, guias_list=None, headless=False, preview=False):
        super().__init__()   # inicializa senales, flags, pages, file_utils, etc.
        self.usuario = usuario
        self.password = password
        self.ciudad = ciudad
        self.tipo = tipo
        self.ampliacion = ampliacion
        self.excel_path = excel_path
        self.guias_list = guias_list   # Lista pre-cargada (alternativa al Excel)
        self.num_navegadores = min(num_navegadores, 100)
        self.headless = headless
        self.preview = preview         # Si True: solo valida login y navegación, no procesa guías

        # Estado del proceso
        self.guias_error = []
        self.guias_advertencia = []
        self.guias_ent = []
        self.guias_procesadas_exito = set()
        self.guias_procesadas_ent = set()
        self.guias_en_error = set()
        self.cola_guias = []
        self.total_guias = 0

    # ── Helpers de frame locators ────────────────────────────────────────────

    def _principal(self, page):
        """Frame principal (menu → principal)"""
        return (page.frame_locator('frame[name="menu"]')
                    .frame_locator('iframe[name="principal"]'))

    def _filtro(self, page):
        return self._principal(page).frame_locator('frame[name="filtro"]')

    def _resultado(self, page):
        return self._principal(page).frame_locator('frame[name="resultado"]')

    def _contenido(self, page):
        return self._principal(page).frame_locator('frame[name="contenido"]')

    def _solapas(self, page):
        return self._principal(page).frame_locator('frame[name="solapas"]')

    # ────────────────────────────────────────────────────────────────────────

    def leer_excel(self, ruta: Union[str, Path]) -> List[str]:
        """Lee el archivo Excel y extrae las guías"""
        return self.file_utils.leer_guias_excel(Path(ruta))

    async def verificar_estado_ent(self, page, nav_idx):
        """Verifica si la guía tiene estado ENT"""
        try:
            elemento_ent = self._resultado(page).get_by_role("cell", name="ENT", exact=True)
            if await elemento_ent.count() > 0:
                self.senales.log.emit(f"📦 [Nav{nav_idx}] Estado ENT detectado")
                return True
            return False
        except Exception:
            return False

    async def navegar_a_funcionalidad_7_8(self, page, nav_idx):
        """Navega a la funcionalidad 7.8"""
        try:
            self.senales.log.emit(f"🧭 [Nav{nav_idx}] Navegando a 7.8...")
            
            if not await self.verificar_pagina_activa(page):
                return False
            
            menu = page.frame_locator('frame[name="menu"]')
            
            try:
                base_selector = menu.get_by_role("cell", name="ABA BARRANQUILLA AEROPUE").locator("span")
                if await base_selector.count() > 0:
                    await base_selector.click(timeout=3000)
            except Exception:
                pass

            try:
                ciudad_selector = menu.get_by_role("list").get_by_text(self.ciudad)
                if await ciudad_selector.count() > 0:
                    await ciudad_selector.click(timeout=2000)
                    await asyncio.sleep(TIEMPO_ESPERA_CLICK * 2 / 1000)
            except Exception:
                pass

            funcionalidad = menu.locator('input[name="funcionalidad_codigo"]:not([type="hidden"])')
            await funcionalidad.wait_for(state="visible", timeout=20000)
            await funcionalidad.fill("")
            await asyncio.sleep(0.2)
            await funcionalidad.fill("7.8")
            await asyncio.sleep(0.2)
            await funcionalidad.press("Enter")

            await self.esperar_overlay(page)
            await asyncio.sleep(TIEMPO_ESPERA_NAVEGACION / 1000)
            
            self.senales.log.emit(f"✅ [Nav{nav_idx}] Navegación completada")
            return True
            
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error navegación: {str(e)}")
            return False

    async def ingresar_codigos(self, contenido, tipo, origen, nav_idx):
        """Ingresa los códigos de tipo y origen"""
        try:
            tipo_input = contenido.locator('input[name="tipo_incidencia_codigo"]:not([type="hidden"])')
            await tipo_input.wait_for(state="visible", timeout=10000)
            await tipo_input.fill("")
            await tipo_input.fill(tipo)
            await tipo_input.press("Enter")

            origen_input = contenido.locator('input[name="tipo_origen_incidencia_codigo"]:not([type="hidden"])')
            await origen_input.wait_for(state="visible", timeout=10000)
            await origen_input.fill("")
            await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)
            await origen_input.fill(origen)
            await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)
            await origen_input.press("Enter")
            await asyncio.sleep(TIEMPO_ESPERA_CLICK / 1000)

            return True
        except Exception as e:
            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Error códigos: {str(e)}")
            return False

    async def manejar_boton_volver(self, solapas, guia, nav_idx):
        """Maneja el botón Volver"""
        try:
            self.senales.log.emit(f"⏎ [Nav{nav_idx}] Clic en Volver...")
            await asyncio.sleep(2)
            
            boton_volver = solapas.get_by_role("button", name="Volver")
            
            if await boton_volver.count() == 0:
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Botón Volver no encontrado")
                return False
            
            await boton_volver.click(timeout=TIEMPO_ESPERA_VOLVER)
            await self.esperar_overlay(self.pages[nav_idx - 1])

            # Esperar a que el formulario de búsqueda esté listo antes de continuar
            _page = self.pages[nav_idx - 1]
            _filtro = self._filtro(_page)
            try:
                await _filtro.locator('input[name="nenvio"]:not([type="hidden"])').wait_for(
                    state="visible", timeout=8000
                )
            except Exception:
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Formulario no cargó tras Volver — renavegando...")
                await self.navegar_a_funcionalidad_7_8(_page, nav_idx)

            return await self.verificar_pagina_activa(self.pages[nav_idx - 1])
            
        except Exception as e:
            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Error Volver: {str(e)}")
            return False

    async def verificar_incidencia_creada(self, page, nav_idx, guia):
        """Verifica si la incidencia se creó correctamente"""
        try:
            contenido = self._contenido(page)

            # Verificar que el frame tenga contenido real antes de evaluar
            try:
                body_text = await contenido.locator("body").inner_text(timeout=4000)
                if not body_text.strip():
                    self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Frame vacío tras creación — estado indeterminado")
                    return None
            except Exception:
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] No se pudo leer el frame — estado indeterminado")
                return None

            mensajes_error = [
                "No se pudo", "Error al crear", "Exception",
                "No fue posible", "Reintente", "Ya existe una incidencia"
            ]

            for mensaje in mensajes_error:
                try:
                    if await contenido.get_by_text(mensaje, exact=False).count() > 0:
                        self.senales.log.emit(f"❌ [Nav{nav_idx}] Error detectado: {mensaje}")
                        return False
                except Exception:
                    pass

            self.senales.log.emit(f"✅ [Nav{nav_idx}] Sin errores detectados — creación confirmada")
            return True

        except Exception as e:
            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Error en verificación: {str(e)}")
            return None

    async def detectar_error_guia(self, page):
        """Detecta si hay error en la guía"""
        errores = ["No se encontraron", "No existe", "sin resultados"]
        resultado = self._resultado(page)
        for texto in errores:
            try:
                if await resultado.get_by_text(texto, exact=False).count() > 0:
                    return True
            except Exception:
                pass
        return False

    async def _registrar_error(self, guia, error_msg, nav_idx):
        """Registra un error en la lista"""
        async with self.lock:
            self.guias_error.append((guia, f"[Nav{nav_idx}] {error_msg}"))
            self.guias_en_error.add(guia)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.senales.guia_procesada.emit(
            guia, "❌ ERROR", error_msg, f"Nav{nav_idx}", fecha
        )

    async def _manejar_ent(self, guia, nav_idx, solapas):
        """Maneja el caso de guía ENT"""
        mensaje = f"📦 [Nav{nav_idx}] {guia} - GUÍA ENTREGADA (ENT)"
        self.senales.log.emit(mensaje)
        async with self.lock:
            self.guias_ent.append(guia)
            self.guias_procesadas_ent.add(guia)
        
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.senales.guia_procesada.emit(guia, "📦 ENTREGADA", "ENT", f"Nav{nav_idx}", fecha)
        
        try:
            boton_volver = solapas.get_by_role("button", name="Volver")
            if await boton_volver.count() > 0:
                await boton_volver.click(timeout=10000)
                await self.esperar_overlay(self.pages[nav_idx - 1])
        except Exception:
            pass

        return True

    async def _evaluar_resultado(self, guia, nav_idx, incidencia_creada, exito_volver, intento):
        """Evalúa el resultado de la creación"""
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if incidencia_creada is True:
            async with self.lock:
                self.guias_procesadas_exito.add(guia)
            if not exito_volver:
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Timeout en Volver — incidencia ya creada, continuando")
            self.senales.guia_procesada.emit(
                guia, "✅ PROCESADA", f"Tipo {self.tipo}", f"Nav{nav_idx}", fecha
            )
            self.senales.log.emit(f"✅ [Nav{nav_idx}] {guia} OK")
            return True
        elif incidencia_creada is None:
            async with self.lock:
                self.guias_advertencia.append((guia, f"[Nav{nav_idx}] Estado indeterminado"))
            self.senales.guia_procesada.emit(
                guia, "⚠️ ADVERTENCIA", "NO CONFIRMADO", f"Nav{nav_idx}", fecha
            )
            return True
        else:
            error_msg = "Incidencia no creada"
            await self._registrar_error(guia, error_msg, nav_idx)
            
            if intento < MAX_REINTENTOS and not incidencia_creada:
                return False
            return True

    async def _ejecutar_creacion(self, page, guia, nav_idx, contenido):
        """Ejecuta la creación de la incidencia"""
        await contenido.get_by_role("button", name="Crear").click()
        await self.esperar_overlay(page)  # espera respuesta del servidor en lugar de sleep fijo
        return await self.verificar_incidencia_creada(page, nav_idx, guia)

    async def _procesar_creacion_incidencia(self, page, guia, nav_idx, resultado, contenido, solapas, intento):
        """Procesa la creación de la incidencia"""
        if await self.detectar_error_guia(page):
            error_msg = "Guía sin resultados"
            await self._registrar_error(guia, error_msg, nav_idx)
            raise Exception(error_msg)

        # Reintento en el click del link — el servidor puede tardar bajo carga alta
        _abierta = False
        for _intento_click in range(1, 3):
            try:
                await resultado.get_by_role("link", name=guia).click(timeout=25000)
                _abierta = True
                break
            except Exception:
                if _intento_click < 2:
                    self.senales.log.emit(f"🔄 [Nav{nav_idx}] Link {guia} no respondió — reintentando...")
                    await asyncio.sleep(2)
        if not _abierta:
            error_msg = "No se pudo abrir la guía tras 2 intentos"
            await self._registrar_error(guia, error_msg, nav_idx)
            raise Exception(error_msg)

        await self.esperar_overlay(page)
        await asyncio.sleep(TIEMPO_ESPERA_CLICK / 1000)

        if not await self.ingresar_codigos(contenido, self.tipo, ORIGEN_INCIDENCIA, nav_idx):
            error_msg = "Error ingresando códigos"
            await self._registrar_error(guia, error_msg, nav_idx)
            raise Exception(error_msg)

        await contenido.locator('textarea[name="ampliacion_incidencia"]').fill(self.ampliacion)

        resultado_creacion = await self._ejecutar_creacion(page, guia, nav_idx, contenido)
        exito_volver = await self.manejar_boton_volver(solapas, guia, nav_idx)
        
        return await self._evaluar_resultado(
            guia, nav_idx, resultado_creacion, exito_volver, intento
        )

    async def crear_incidencia(self, page, guia, nav_idx, intento=1):
        """Crea una incidencia para una guía"""
        async with self.lock:
            if any(guia in s for s in [self.guias_procesadas_exito, 
                                        self.guias_procesadas_ent, 
                                        self.guias_en_error]):
                self.senales.log.emit(f"⏭️ [Nav{nav_idx}] Guía {guia} ya procesada - omitiendo")
                return True
        
        if not await self.verificar_pagina_activa(page):
            raise Exception("Página no activa")

        filtro = self._filtro(page)
        resultado = self._resultado(page)
        contenido = self._contenido(page)
        solapas = self._solapas(page)

        envio = filtro.locator('input[name="nenvio"]:not([type="hidden"])')
        try:
            await envio.wait_for(state="visible", timeout=8000)
        except Exception:
            # Frame filtro no cargó — intentar re-navegación a 7.8 y reconstruir locators
            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Frame filtro no disponible — renavegando a 7.8...")
            if not await self.navegar_a_funcionalidad_7_8(page, nav_idx):
                error_msg = "Recuperación fallida: no se pudo navegar a 7.8"
                await self._registrar_error(guia, error_msg, nav_idx)
                raise Exception(error_msg)
            filtro    = self._filtro(page)
            resultado = self._resultado(page)
            contenido = self._contenido(page)
            solapas   = self._solapas(page)
            envio = filtro.locator('input[name="nenvio"]:not([type="hidden"])')
            try:
                await envio.wait_for(state="visible", timeout=10000)
            except Exception as e2:
                error_msg = f"Campo búsqueda no disponible tras recuperación: {str(e2)}"
                await self._registrar_error(guia, error_msg, nav_idx)
                raise Exception(error_msg)

        await envio.fill("")
        await asyncio.sleep(0.5)
        await envio.fill(guia)
        await asyncio.sleep(0.5)
        await envio.press("Enter")

        await self.esperar_overlay(page)
        await asyncio.sleep(TIEMPO_ESPERA_CLICK / 1000)

        if await self.verificar_estado_ent(page, nav_idx):
            return await self._manejar_ent(guia, nav_idx, solapas)

        return await self._procesar_creacion_incidencia(
            page, guia, nav_idx, resultado, contenido, solapas, intento
        )

    async def trabajador_navegador(self, nav_idx, total_guias, resultados):
        """Worker para cada navegador"""
        try:
            page = self.pages[nav_idx - 1]
            guias_procesadas_local = 0
            
            while self.procesando and not self.cancelado:
                await self.check_pausa()
                if self.cancelado:
                    break
                async with self.lock:
                    if not self.cola_guias:
                        break
                    guia = self.cola_guias.pop(0)
                    
                    if any(guia in s for s in [self.guias_procesadas_exito,
                                                self.guias_procesadas_ent,
                                                self.guias_en_error]):
                        self.senales.log.emit(f"⏭️ [Nav{nav_idx}] Guía {guia} ya procesada - saltando")
                        continue
                
                try:
                    self.senales.log.emit(f"🌐 [Nav{nav_idx}] Procesando: {guia}")
                    exito = await self.crear_incidencia(page, guia, nav_idx)
                    
                    if exito:
                        guias_procesadas_local += 1
                        async with self.lock:
                            resultados['exitosas'] += 1
                    
                except Exception as e:
                    self.senales.log.emit(f"❌ [Nav{nav_idx}] Error: {str(e)}")
                
                async with self.lock:
                    resultados['progreso'] += 1
                    progreso = int(resultados['progreso'] / total_guias * 100)
                    self.senales.progreso.emit(progreso)
                    await self.calcular_tiempo_restante(resultados['progreso'], total_guias)
                    self.senales.estado.emit(
                        f"Progreso: {resultados['progreso']}/{total_guias} ({progreso}%) "
                        f"- Éxitos: {resultados['exitosas']}"
                    )
            
            self.senales.log.emit(f"📊 [Nav{nav_idx}] Procesó {guias_procesadas_local} guías")
            
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error fatal: {str(e)}")

    async def _inicializar_un_navegador(self, p, i):
        """Inicializa un navegador individual con conexión escalonada y reintentos con backoff."""
        nav_num = i + 1
        if self.cancelado:
            return False

        self.senales.log.emit(f"▶️ [Nav{nav_num}] Iniciando...")

        launch_args = ['--disable-dev-shm-usage']
        if not self.headless:
            launch_args.append('--start-maximized')

        browser = await p.chromium.launch(headless=self.headless, args=launch_args)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            locale="es-ES"
        )
        page = await context.new_page()
        page.set_default_timeout(60000)

        senales = self.senales

        async def _cerrar_popup_contacto(popup, _nav=nav_num):
            try:
                url = popup.url
                if not url:
                    url = await popup.evaluate("location.href")
                if "contacto_llamadas_consulta" in url:
                    senales.log.emit(f"🪟 [Nav{_nav}] Popup contacto — cerrando...")
                    await asyncio.sleep(0.5)
                    try:
                        boton = popup.get_by_role("button", name="CERRAR")
                        if await boton.count() > 0:
                            await boton.click(timeout=3000)
                            await asyncio.sleep(0.5)
                    except Exception:
                        pass
                    try:
                        await popup.close()
                    except Exception:
                        pass
            except Exception:
                try:
                    await popup.close()
                except Exception:
                    pass

        page.on("popup", lambda p: asyncio.ensure_future(_cerrar_popup_contacto(p)))

        # Asignar al slot preasignado — evita condición de carrera con append()
        self.browsers[i] = browser
        self.contexts[i] = context
        self.pages[i]    = page

        # Stagger con tope: máximo 5s de espera sin importar cuántos navegadores haya.
        # Evita que Nav50 espere 35s (0.7*50) o Nav100 espere 70s antes de conectar.
        if i > 0:
            await asyncio.sleep(min(i * 0.3, 5))

        self.senales.log.emit(f"🌐 [Nav{nav_num}] Conectando...")
        await page.goto(URL_ALERTRAN, timeout=60000, wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        # Login con semáforo (máx 10 simultáneos) + backoff exponencial con jitter
        async with self._login_sem:
            for intento in range(1, MAX_REINTENTOS + 1):
                if self.cancelado:
                    return False

                # Verificar que el formulario de login esté presente
                try:
                    await page.wait_for_selector('input[name="j_username"]', timeout=10000)
                except Exception:
                    self.senales.log.emit(f"⚠️ [Nav{nav_num}] Formulario no disponible — recargando...")
                    await page.goto(URL_ALERTRAN, timeout=60000, wait_until="domcontentloaded")
                    await asyncio.sleep(2)
                    continue

                if await self.hacer_login(page, nav_num):
                    break

                if intento < MAX_REINTENTOS:
                    # Backoff exponencial: 3s, 6s, 12s + jitter aleatorio ±1s
                    base = 3 * (2 ** (intento - 1))
                    espera = base + random.uniform(-1, 1)
                    self.senales.log.emit(
                        f"🔄 [Nav{nav_num}] Reintentando login ({intento}/{MAX_REINTENTOS}) en {espera:.1f}s..."
                    )
                    await asyncio.sleep(espera)
                    await page.goto(URL_ALERTRAN, timeout=60000, wait_until="domcontentloaded")
                    await asyncio.sleep(1.5)
            else:
                self.senales.log.emit(
                    f"❌ [Nav{nav_num}] Login fallido tras {MAX_REINTENTOS} intentos — se omitirá"
                )
                return False

        if not await self.navegar_a_funcionalidad_7_8(page, nav_num):
            self.senales.log.emit(f"❌ [Nav{nav_num}] Error de navegación — se omitirá")
            return False

        self.senales.log.emit(f"✅ [Nav{nav_num}] Listo")
        async with self.lock:
            self._navegadores_listos += 1
            listos = self._navegadores_listos
        self.senales.navegador_inicializado.emit(listos, self.num_navegadores)
        return True

    async def _inicializar_navegadores(self, p):
        """Inicializa todos los navegadores en paralelo.
        Continúa con los que logren inicializarse aunque algunos fallen."""
        self.browsers = [None] * self.num_navegadores
        self.contexts = [None] * self.num_navegadores
        self.pages    = [None] * self.num_navegadores
        self._navegadores_listos = 0  # contador para progreso de inicialización

        # Semáforo: máximo 10 logins simultáneos para no saturar el servidor
        self._login_sem = asyncio.Semaphore(10)

        self.senales.log.emit(
            f"🚀 Iniciando {self.num_navegadores} navegador(es) en paralelo..."
        )
        self.senales.estado.emit(f"Inicializando navegadores: 0/{self.num_navegadores}...")

        resultados = await asyncio.gather(
            *[self._inicializar_un_navegador(p, i) for i in range(self.num_navegadores)],
            return_exceptions=True,
        )

        indices_ok = [i for i, res in enumerate(resultados) if res is True]
        fallidos   = [i + 1 for i, res in enumerate(resultados) if res is not True]

        if fallidos:
            self.senales.log.emit(
                f"⚠️ Nav{', Nav'.join(map(str, fallidos))} no pudieron inicializarse y serán omitidos"
            )

        if not indices_ok:
            self.senales.error.emit("❌ Ningún navegador pudo inicializarse. Abortando.")
            return False

        # Compactar listas eliminando slots None de los fallidos
        self.browsers        = [self.browsers[i] for i in indices_ok]
        self.contexts        = [self.contexts[i] for i in indices_ok]
        self.pages           = [self.pages[i]    for i in indices_ok]
        self.num_navegadores = len(indices_ok)

        self.senales.log.emit(f"✅ {self.num_navegadores} navegador(es) listos para procesar")
        return True

    def _finalizar_proceso(self, exitosas):
        """Finaliza el proceso y guarda resultados"""
        if not self.cancelado:
            if self.guias_error or self.guias_advertencia:
                ruta = self.file_utils.guardar_errores_excel(
                    self.guias_error, self.guias_advertencia, self.carpeta_descargas
                )
                self.senales.archivo_errores.emit(ruta)
            
            tiempo_total = time.time() - self.tiempo_inicio
            tiempo_formateado = str(timedelta(seconds=int(tiempo_total)))
            
            self.senales.log.emit(f"\n 🕑 Completado en {tiempo_formateado}")
            self.senales.log.emit(f" 📝 Desviaciones creadas: {exitosas - len(self.guias_ent)}")
            self.senales.log.emit(f" 📦 Guías ENT (omitidas): {len(self.guias_ent)}")
            self.senales.log.emit(f" ❌ Errores: {len(self.guias_error)}")
            self.senales.log.emit(f" ⚠️ Advertencias: {len(self.guias_advertencia)}")
            
            self.senales.finalizado.emit()
        else:
            self.senales.proceso_cancelado.emit()

    async def proceso_principal(self):
        """Método principal con múltiples navegadores"""
        self.lock = asyncio.Lock()
        self._login_sem = asyncio.Semaphore(10)

        # ── Modo preview: solo verifica login y navegación a 7.8 ─────────────
        if self.preview:
            self.senales.estado.emit("🔍 Probando conexión...")
            self.browsers = [None]
            self.contexts = [None]
            self.pages    = [None]
            self._navegadores_listos = 0
            async with async_playwright() as p:
                ok = await self._inicializar_un_navegador(p, 0)
                for b in self.browsers:
                    try:
                        if b: await b.close()
                    except Exception:
                        pass
            if ok:
                self.senales.log.emit("✅ Conexión OK — credenciales válidas y funcionalidad 7.8 accesible")
                self.senales.estado.emit("✅ Conexión exitosa")
            else:
                self.senales.log.emit("❌ Prueba fallida — revise credenciales o conexión")
                self.senales.estado.emit("❌ Conexión fallida")
            self.senales.finalizado.emit()
            return
        # ─────────────────────────────────────────────────────────────────────

        try:
            if self.guias_list is not None:
                guias_raw = self.guias_list
                self.senales.log.emit(f"📋 Usando {len(guias_raw)} guías ingresadas manualmente")
            else:
                guias_raw = self.leer_excel(self.excel_path)

            guias = list(dict.fromkeys(guias_raw))  # elimina duplicados preservando orden
            duplicadas = len(guias_raw) - len(guias)

            if len(guias) == 0:
                self.senales.error.emit("No hay guías para procesar")
                return

            self.total_guias = len(guias)
            self.tiempo_inicio = time.time()

            msg = f"Procesando {self.total_guias} guías únicas con {self.num_navegadores} navegador(es)"
            if duplicadas > 0:
                msg += f" ({duplicadas} duplicadas ignoradas)"
            self.senales.estado.emit(msg)
            if duplicadas > 0:
                self.senales.log.emit(f"⚠️ Se ignoraron {duplicadas} guías duplicadas del Excel")
                self.senales.duplicadas_detectadas.emit(duplicadas)

            resultados = {'progreso': 0, 'exitosas': 0}
            async with async_playwright() as p:
                try:
                    if not await self._inicializar_navegadores(p):
                        return

                    if not self.cancelado:
                        self.cola_guias = guias.copy()
                        tareas = [
                            self.trabajador_navegador(i+1, self.total_guias, resultados)
                            for i in range(self.num_navegadores)
                        ]
                        await asyncio.gather(*tareas)
                finally:
                    for browser in self.browsers:
                        try:
                            await browser.close()
                        except Exception:
                            pass

            self._finalizar_proceso(resultados['exitosas'])

        except Exception as e:
            self.senales.error.emit(f"Error: {str(e)}")

    def run(self):
        """Ejecuta el thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.proceso_principal())
        finally:
            loop.close()