# services/viajes_service.py
"""
Conversión de workers/desviacion_viajes_thread.py a servicio async puro.
Sin Qt — usa BaseService para emitir eventos al job_manager.
"""
from datetime import datetime, timedelta
import asyncio
import time
import re
import urllib.request
from playwright.async_api import async_playwright

from services.base_service import BaseService
from services.job_manager import JobManager
from config.settings import (
    MAX_REINTENTOS, TIEMPO_ESPERA_CLICK, TIEMPO_ESPERA_NAVEGACION,
    TIEMPO_ESPERA_INGRESO_CODIGOS, URL_ALERTRAN
)


class ViajesService(BaseService):
    """Procesa desvíos de viajes con paginación."""

    def __init__(
        self,
        job_id: str,
        jm: JobManager,
        usuario: str,
        password: str,
        ciudad: str,
        numero_viaje: str,
        codigo_desviacion: str,
        observaciones: str,
        num_navegadores: int = 1,
        headless: bool = True,
        pagina_inicio: int = 1,
    ):
        super().__init__(job_id, jm)
        self.usuario            = usuario
        self.password           = password
        self.ciudad             = ciudad
        self.numero_viaje       = numero_viaje
        self.codigo_desviacion  = codigo_desviacion
        self.observaciones      = observaciones
        self.headless           = headless
        self.pagina_inicio      = max(1, int(pagina_inicio))
        self.num_navegadores    = min(max(1, int(num_navegadores)), 10)

        # Estado
        self.guias_error            = []
        self.guias_advertencia      = []
        self.guias_procesadas_exito = set()
        self.guias_en_error         = set()
        self.paginas_procesadas     = 0
        self.total_paginas          = 0
        self.proceso_viaje_exitoso  = False

    # ── Selección de base / ciudad ───────────────────────────────────────────

    async def seleccionar_base(self, menu, nav_idx: int):
        ciudad_codigo = self.ciudad[:3] if self.ciudad and len(self.ciudad) >= 3 else "ABA"
        await self.log(f"🔍 [Nav{nav_idx}] Seleccionando base para código: {ciudad_codigo}")

        estrategias = [
            lambda: menu.locator(f'td:has-text("{ciudad_codigo}") span'),
            lambda: menu.locator(f'td:has-text("{ciudad_codigo}")'),
            lambda: menu.get_by_text(re.compile(f"{ciudad_codigo}.*", re.IGNORECASE)),
            lambda: menu.get_by_role("cell").filter(has_text=re.compile(ciudad_codigo, re.IGNORECASE)),
        ]

        for i, estrategia in enumerate(estrategias, 1):
            try:
                sel = estrategia()
                if await sel.count() > 0:
                    await sel.first.click(timeout=5000)
                    await self.log(f"✅ [Nav{nav_idx}] Base seleccionada (estrategia {i})")
                    await asyncio.sleep(1)
                    return True
            except Exception as e:
                await self.log(f"ℹ️ [Nav{nav_idx}] Estrategia {i} no funcionó: {str(e)[:50]}")

        # Estrategia por nombre completo
        try:
            ciudad_nombre = self.ciudad[4:] if len(self.ciudad) > 4 else ""
            if ciudad_nombre:
                sel = menu.get_by_text(re.compile(f".*{ciudad_nombre}.*", re.IGNORECASE))
                if await sel.count() > 0:
                    await sel.first.click(timeout=5000)
                    await self.log(f"✅ [Nav{nav_idx}] Base seleccionada por nombre")
                    await asyncio.sleep(1)
                    return True
        except Exception:
            pass

        await self.log(f"ℹ️ [Nav{nav_idx}] No fue necesario seleccionar base o no se encontró")
        return False

    async def navegar_a_funcionalidad_base(self, page, nav_idx: int):
        try:
            if not await self.verificar_pagina_activa(page):
                return None
            menu = page.frame_locator('frame[name="menu"]')
            await self.seleccionar_base(menu, nav_idx)

            try:
                await self.log(f"🔍 [Nav{nav_idx}] Buscando ciudad: {self.ciudad}")
                ciudad_selector = menu.get_by_role("list").get_by_text(self.ciudad, exact=False)
                if await ciudad_selector.count() > 0:
                    await ciudad_selector.first.click(timeout=5000)
                    await self.log(f"✅ [Nav{nav_idx}] Ciudad seleccionada: {self.ciudad}")
                    await asyncio.sleep(TIEMPO_ESPERA_CLICK * 2 / 1000)
                else:
                    await self.log(f"⚠️ [Nav{nav_idx}] No se encontró la ciudad: {self.ciudad}")
            except Exception as e:
                await self.log(f"ℹ️ [Nav{nav_idx}] Error seleccionando ciudad: {str(e)[:50]}")

            return menu
        except Exception as e:
            await self.log(f"❌ [Nav{nav_idx}] Error en navegación base: {str(e)}")
            return None

    async def navegar_a_7_3_2(self, page, menu, nav_idx: int) -> bool:
        try:
            funcionalidad = menu.locator('input[name="funcionalidad_codigo"]:not([type="hidden"])')
            await funcionalidad.wait_for(state="visible", timeout=20000)
            await funcionalidad.fill("")
            await asyncio.sleep(0.2)
            await funcionalidad.fill("7.3.2")
            await asyncio.sleep(0.2)
            await funcionalidad.press("Enter")
            await self.log(f"⌨️ [Nav{nav_idx}] Funcionalidad 7.3.2 ingresada")
            await self.esperar_overlay(page)
            await asyncio.sleep(TIEMPO_ESPERA_NAVEGACION / 1000)
            await self.log(f"✅ [Nav{nav_idx}] Navegación a 7.3.2 completada")
            return True
        except Exception as e:
            await self.log(f"❌ [Nav{nav_idx}] Error navegando a 7.3.2: {str(e)}")
            return False

    # ── Búsqueda de carta porte ──────────────────────────────────────────────

    async def buscar_carta_porte(self, page, nav_idx: int) -> bool:
        try:
            await self.log(f"🔍 [Nav{nav_idx}] Buscando carta porte: {self.numero_viaje}")
            menu_frame = page.frame_locator('frame[name="menu"]')
            principal  = menu_frame.frame_locator('iframe[name="principal"]')
            filtro     = principal.frame_locator('frame[name="filtro"]')

            campo_carta = filtro.locator('input[name="carta_porte"]')
            if await campo_carta.count() > 0:
                await campo_carta.click()
                await campo_carta.fill(self.numero_viaje)
                await asyncio.sleep(0.5)
                await filtro.get_by_role("button", name="Buscar").click()
                await self.esperar_overlay(page)
                await asyncio.sleep(3)
                await self.log(f"✅ [Nav{nav_idx}] Búsqueda completada")
                return True
            else:
                await self.log(f"⚠️ [Nav{nav_idx}] No se encontró campo carta_porte")
                return False
        except Exception as e:
            await self.log(f"❌ [Nav{nav_idx}] Error en búsqueda: {str(e)}")
            return False

    # ── Helpers de frame ─────────────────────────────────────────────────────

    async def reobtener_frames(self, page):
        menu_frame = page.frame_locator('frame[name="menu"]')
        principal  = menu_frame.frame_locator('iframe[name="principal"]')
        return principal.frame_locator('frame[name="resultado"]')

    async def detectar_sin_resultados(self, page) -> bool:
        try:
            mensajes = [
                "No se encontraron datos", "No hay resultados",
                "No existen registros", "0 resultados",
            ]
            resultado = (
                page.frame_locator('frame[name="menu"]')
                    .frame_locator('iframe[name="principal"]')
                    .frame_locator('frame[name="resultado"]')
            )
            for mensaje in mensajes:
                try:
                    if await resultado.get_by_text(mensaje, exact=False).count() > 0:
                        return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    # ── Paginación ───────────────────────────────────────────────────────────

    async def obtener_total_paginas(self, resultado, nav_idx: int) -> int:
        try:
            el = resultado.locator('input[name="pagina_maximo"]')
            if await el.count() > 0:
                valor = await el.first.get_attribute("value")
                if valor and valor.isdigit():
                    total = int(valor)
                    await self.log(f"📄 [Nav{nav_idx}] Páginas totales: {total}")
                    return total
            await self.log(f"📄 [Nav{nav_idx}] Sin paginación detectada — asumiendo 1 página")
            return 1
        except Exception as e:
            await self.log(f"⚠️ [Nav{nav_idx}] Error obteniendo páginas: {str(e)}")
            return 1

    async def ir_a_siguiente_pagina(self, page, resultado, nav_idx: int, pagina_actual: int, total_paginas: int) -> bool:
        try:
            siguiente_numero = pagina_actual + 1
            _esperas = [5, 10, 15]

            # Estrategia 1: enlace "Siguiente"
            for intento in range(1, 4):
                resultado = await self.reobtener_frames(page)
                siguiente_link = resultado.get_by_role("link", name="Siguiente")
                if await siguiente_link.count() > 0:
                    await self.log(f"➡️ [Nav{nav_idx}] Clic en Siguiente")
                    await siguiente_link.first.click()
                    await self.esperar_overlay(page)
                    try:
                        await resultado.locator('input[name="all"]').wait_for(state="visible", timeout=8000)
                    except Exception:
                        await asyncio.sleep(3)
                    return True
                if intento < 3:
                    espera = _esperas[intento - 1]
                    await self.log(f"⏳ [Nav{nav_idx}] Esperando paginación... (intento {intento}/3, {espera}s)")
                    await asyncio.sleep(espera)

            # Estrategia 2: enlace con número
            enlace_numero = resultado.locator(f'a:has-text("{siguiente_numero}")')
            if await enlace_numero.count() > 0:
                await self.log(f"➡️ [Nav{nav_idx}] Clic en página {siguiente_numero}")
                await enlace_numero.first.click()
                await self.esperar_overlay(page)
                try:
                    await resultado.locator('input[name="all"]').wait_for(state="visible", timeout=8000)
                except Exception:
                    await asyncio.sleep(3)
                return True

            # Estrategia 3: submit JS
            await self.log(f"⏳ [Nav{nav_idx}] Intentando navegación JS a página {siguiente_numero}...")
            try:
                nav_ok = await page.evaluate(f"""
                    () => {{
                        const frames = window.frames;
                        for (let i = 0; i < frames.length; i++) {{
                            try {{
                                const doc = frames[i].document;
                                const inp = doc.querySelector('input[name="pagina_actual"]');
                                const form = inp && inp.form;
                                if (form) {{
                                    inp.value = '{siguiente_numero}';
                                    form.submit();
                                    return true;
                                }}
                            }} catch(e) {{}}
                        }}
                        return false;
                    }}
                """)
                if nav_ok:
                    await self.esperar_overlay(page)
                    try:
                        resultado2 = await self.reobtener_frames(page)
                        await resultado2.locator('input[name="all"]').wait_for(state="visible", timeout=8000)
                    except Exception:
                        await asyncio.sleep(3)
                    await self.log(f"➡️ [Nav{nav_idx}] Navegación JS a página {siguiente_numero} exitosa")
                    return True
            except Exception as js_err:
                await self.log(f"⚠️ [Nav{nav_idx}] JS fallback falló: {str(js_err)[:60]}")

            await self.log(f"⚠️ [Nav{nav_idx}] No se encontró enlace para página {siguiente_numero}")
            return False
        except Exception as e:
            await self.log(f"⚠️ [Nav{nav_idx}] Error al ir a siguiente página: {str(e)}")
            return False

    # ── Selección y asignación ───────────────────────────────────────────────

    async def seleccionar_todos_envios(self, resultado, nav_idx: int) -> bool:
        try:
            checkbox_all = resultado.locator('input[name="all"]').first
            if await checkbox_all.count() > 0:
                await checkbox_all.check()
                await self.log(f"✅ [Nav{nav_idx}] Seleccionados todos los envíos de la página")
                await asyncio.sleep(1)
                return True
            checkboxes = resultado.locator('input[type="checkbox"]')
            n = await checkboxes.count()
            if n > 0:
                for i in range(n):
                    await checkboxes.nth(i).check()
                await self.log(f"✅ [Nav{nav_idx}] Seleccionados {n} envíos")
                await asyncio.sleep(1)
                return True
            return False
        except Exception as e:
            await self.log(f"⚠️ [Nav{nav_idx}] Error seleccionando envíos: {str(e)}")
            return False

    async def asignar_incidencia(self, page, resultado, tipo: str, nav_idx: int) -> bool:
        _ERROR_INCIDENCIA = "no hay ningun tipo de incidencia"

        for intento in range(1, MAX_REINTENTOS + 1):
            try:
                await self.log(
                    f"🔄 [Nav{nav_idx}] Asignando incidencia tipo {tipo}"
                    + (f" (intento {intento}/{MAX_REINTENTOS})" if intento > 1 else "")
                )

                incidencia_input = resultado.locator('input[name="incidencia_codigo"]').first
                if await incidencia_input.count() > 0:
                    await incidencia_input.click(click_count=3)
                    await incidencia_input.fill("")
                    await asyncio.sleep(0.2)
                    await incidencia_input.fill(tipo)
                    if intento > 1:
                        await incidencia_input.press("Tab")
                        await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)
                    await incidencia_input.press("Enter")
                    await self.log(f"✅ [Nav{nav_idx}] Código incidencia {tipo} ingresado")
                    await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)

                fuente_input = resultado.locator('input[name="tipo_origen_incidencia_codigo"]').first
                if await fuente_input.count() > 0:
                    await fuente_input.click(click_count=3)
                    await fuente_input.fill("018")
                    await fuente_input.press("Enter")
                    await self.log(f"✅ [Nav{nav_idx}] Fuente 018 ingresada")
                    await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)

                ampliacion_input = resultado.locator('textarea[name="ampliacion_incidencia"]').first
                if await ampliacion_input.count() > 0:
                    await ampliacion_input.click()
                    await ampliacion_input.fill(self.observaciones)
                    await self.log(f"✅ [Nav{nav_idx}] Ampliación ingresada")
                    await asyncio.sleep(0.5)

                await self.log(f"🖱️ [Nav{nav_idx}] Haciendo clic en Aceptar")
                dialog_info = {"mensaje": ""}

                async def _on_dialog(dialog):
                    dialog_info["mensaje"] = dialog.message
                    await self.log(f"💬 [Nav{nav_idx}] Diálogo: {dialog.message}")
                    await dialog.accept()

                page.once("dialog", _on_dialog)
                try:
                    await resultado.get_by_role("button", name="Aceptar").click()
                except Exception as click_err:
                    try:
                        page.remove_listener("dialog", _on_dialog)
                    except Exception:
                        pass
                    raise click_err

                await self.esperar_overlay(page)
                await asyncio.sleep(4)

                if _ERROR_INCIDENCIA in dialog_info["mensaje"].lower():
                    if intento < MAX_REINTENTOS:
                        await self.log(
                            f"⚠️ [Nav{nav_idx}] Incidencia no reconocida — reintentando "
                            f"({intento}/{MAX_REINTENTOS})..."
                        )
                        await asyncio.sleep(2)
                        continue
                    else:
                        await self.log(
                            f"❌ [Nav{nav_idx}] No se pudo asignar incidencia tras "
                            f"{MAX_REINTENTOS} intentos: tipo {tipo} no válido"
                        )
                        return False

                await self.log(f"✅ [Nav{nav_idx}] Incidencia {tipo} asignada correctamente")
                return True

            except Exception as e:
                err_str = str(e)
                if "Timeout" in err_str or "timeout" in err_str:
                    await self.log(
                        f"⏳ [Nav{nav_idx}] Timeout detectado — reintentando página "
                        f"({intento}/{MAX_REINTENTOS})..."
                    )
                    if intento >= MAX_REINTENTOS:
                        return False
                    await asyncio.sleep(4)
                    continue
                await self.log(f"⚠️ [Nav{nav_idx}] Error en intento {intento}: {err_str}")
                if intento >= MAX_REINTENTOS:
                    return False
                await asyncio.sleep(4)

        return False

    # ── Procesamiento principal del viaje ────────────────────────────────────

    async def procesar_viaje_con_carta_porte(self, page, nav_idx: int) -> bool:
        try:
            await self.log(f"🔍 [Nav{nav_idx}] Procesando carta porte: {self.numero_viaje}")

            menu_frame = page.frame_locator('frame[name="menu"]')
            principal  = menu_frame.frame_locator('iframe[name="principal"]')
            resultado  = principal.frame_locator('frame[name="resultado"]')

            if await self.detectar_sin_resultados(page):
                await self.log(f"⚠️ [Nav{nav_idx}] Carta porte sin resultados")
                return False

            total_paginas = await self.obtener_total_paginas(resultado, nav_idx)
            self.total_paginas = total_paginas
            await self.log(f"📄 [Nav{nav_idx}] Total de páginas a procesar: {total_paginas}")

            tipo = self.codigo_desviacion
            paginas_procesadas = 0
            pagina_inicio = max(1, self.pagina_inicio)

            # Avanzar hasta checkpoint
            if pagina_inicio > 1:
                await self.log(f"⏩ [Nav{nav_idx}] Reanudando desde página {pagina_inicio}...")
                for _p in range(1, pagina_inicio):
                    resultado = await self.reobtener_frames(page)
                    avanzado = await self.ir_a_siguiente_pagina(page, resultado, nav_idx, _p, total_paginas)
                    if not avanzado:
                        await self.log(f"⚠️ [Nav{nav_idx}] No se pudo llegar a página {pagina_inicio}, iniciando desde {_p + 1}")
                        pagina_inicio = _p + 1
                        break
                    await asyncio.sleep(1)
                await self.log(f"✅ [Nav{nav_idx}] Posicionado en página {pagina_inicio}")

            for pagina in range(pagina_inicio, total_paginas + 1):
                await self.check_pausa()
                if self.cancelado:
                    return False

                await self.progreso(int(pagina / total_paginas * 90))
                resultado = await self.reobtener_frames(page)

                try:
                    pag_sys = await resultado.locator('input[name="pagina_actual"]').first.get_attribute("value")
                    await self.log(f"📄 [Nav{nav_idx}] ===== PÁGINA {pagina} DE {total_paginas} (sistema: {pag_sys}) =====")
                except Exception:
                    await self.log(f"📄 [Nav{nav_idx}] ===== PÁGINA {pagina} DE {total_paginas} =====")

                if await resultado.locator('input[name="all"]').count() == 0:
                    await self.log(f"✅ [Nav{nav_idx}] Sin envíos pendientes — proceso completo")
                    break

                seleccionados = await self.seleccionar_todos_envios(resultado, nav_idx)

                # Verificar cancelación después de la selección (operación lenta)
                if self.jm.es_cancelado(self.job_id):
                    self.cancelar()
                if self.cancelado:
                    return False

                if seleccionados:
                    exito = await self.asignar_incidencia(page, resultado, tipo, nav_idx)

                    if exito:
                        # Guardar checkpoint ANTES de verificar cancelación:
                        # la incidencia ya fue asignada, la siguiente ejecución debe
                        # partir de la página siguiente aunque se cancele ahora.
                        paginas_procesadas += 1
                        self.paginas_procesadas = paginas_procesadas
                        self._guardar_checkpoint(pagina)
                        await self.log(f"✅ [Nav{nav_idx}] Página {pagina} procesada correctamente")

                    # Verificar cancelación después de asignar incidencia (operación lenta)
                    if self.jm.es_cancelado(self.job_id):
                        self.cancelar()
                    if self.cancelado:
                        return False

                    if exito:
                        if pagina < total_paginas:
                            await asyncio.sleep(2)
                            resultado = await self.reobtener_frames(page)
                            siguiente = await self.ir_a_siguiente_pagina(page, resultado, nav_idx, pagina, total_paginas)
                            if not siguiente:
                                await self.log(f"⚠️ [Nav{nav_idx}] No se pudo avanzar a la página {pagina + 1}")
                                break
                            await self.esperar_overlay(page)
                            await asyncio.sleep(2)

                            # Verificar cancelación después de navegar a siguiente página
                            if self.jm.es_cancelado(self.job_id):
                                self.cancelar()
                            if self.cancelado:
                                return False
                    else:
                        await self.log(f"❌ [Nav{nav_idx}] Error procesando página {pagina}")
                        break
                else:
                    await self.log(f"⚠️ [Nav{nav_idx}] No hay envíos para seleccionar en página {pagina}")
                    if pagina < total_paginas:
                        await asyncio.sleep(1)
                        resultado = await self.reobtener_frames(page)
                        siguiente = await self.ir_a_siguiente_pagina(page, resultado, nav_idx, pagina, total_paginas)
                        if not siguiente:
                            break

            self.paginas_procesadas = paginas_procesadas
            self.total_paginas      = total_paginas
            await self.log(
                f"🎉 [Nav{nav_idx}] Proceso completado - "
                f"{paginas_procesadas} de {total_paginas} páginas procesadas"
            )
            return paginas_procesadas > 0

        except Exception as e:
            await self.log(f"❌ [Nav{nav_idx}] Error: {str(e)}")
            return False

    # ── Checkpoint ───────────────────────────────────────────────────────────

    def _checkpoint_path(self):
        from pathlib import Path
        import re
        viaje_safe = re.sub(r'[^\w\-]', '_', str(self.numero_viaje))
        return Path.home() / ".alertran" / "checkpoints" / f"viaje_{viaje_safe}.json"

    def _guardar_checkpoint(self, pagina_completada: int):
        import json
        try:
            p = self._checkpoint_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "viaje": str(self.numero_viaje),
                "pagina_completada": pagina_completada,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _limpiar_checkpoint(self):
        try:
            p = self._checkpoint_path()
            if p.exists():
                p.unlink()
        except Exception:
            pass

    # ── Timer y worker ───────────────────────────────────────────────────────

    async def _emitir_tiempo_transcurrido(self):
        while not self.cancelado and self.procesando:
            if self.tiempo_inicio:
                elapsed = int(time.time() - self.tiempo_inicio)
                elapsed_str = str(timedelta(seconds=elapsed))
                await self.tiempo_restante(f"⏱️ Transcurrido: {elapsed_str}")
            await asyncio.sleep(10)

    async def trabajador_navegador(self, nav_idx: int):
        try:
            if nav_idx > 1:
                await self.log(f"ℹ️ [Nav{nav_idx}] Viaje único — procesamiento asignado a Nav1")
                return

            page = self.pages[nav_idx - 1]
            await self.log(f"🌐 [Nav{nav_idx}] Iniciando procesamiento...")
            await self.progreso(10)

            exito = await self.procesar_viaje_con_carta_porte(page, nav_idx)

            if exito:
                self.proceso_viaje_exitoso = True
                await self.progreso(100)
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await self.guia_procesada(
                    self.numero_viaje, "✅ PROCESADO",
                    f"Incidencia {self.codigo_desviacion}", f"Nav{nav_idx}", fecha
                )
            else:
                await self.log(f"❌ [Nav{nav_idx}] El viaje {self.numero_viaje} no se procesó correctamente")

            await asyncio.sleep(5)
        except Exception as e:
            await self.log(f"❌ [Nav{nav_idx}] Error fatal: {str(e)}")

    # ── Inicialización de navegadores ────────────────────────────────────────

    async def _inicializar_navegadores(self, p) -> bool:
        for i in range(self.num_navegadores):
            if self.cancelado:
                break
            await self.log(f"▶️ Iniciando navegador {i+1}/{self.num_navegadores}...")
            try:
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

                self.browsers.append(browser)
                self.contexts.append(context)
                self.pages.append(page)

                await self.log(f"🌐 [Nav{i+1}] Navegando a {URL_ALERTRAN}")
                await page.goto(URL_ALERTRAN, timeout=60000)
                await asyncio.sleep(3)

                if not await self.hacer_login(page, i + 1):
                    await self.error(f"Error login navegador {i+1}")
                    return False

                menu = await self.navegar_a_funcionalidad_base(page, i + 1)
                if not menu:
                    await self.error(f"Error navegación base navegador {i+1}")
                    return False

                if not await self.navegar_a_7_3_2(page, menu, i + 1):
                    await self.error(f"Error navegación 7.3.2 navegador {i+1}")
                    return False

                if not await self.buscar_carta_porte(page, i + 1):
                    await self.error(f"No se encontró el campo de búsqueda en Nav{i+1}")
                    return False

                await self.log(f"✅ [Nav{i+1}] Navegador listo en 7.3.2")
            except Exception as e:
                await self.log(f"❌ [Nav{i+1}] Error inicializando: {str(e)}")
                return False

        return True

    # ── Verificación de latencia ─────────────────────────────────────────────

    async def _verificar_latencia_servidor(self):
        try:
            inicio = time.time()
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: urllib.request.urlopen(URL_ALERTRAN, timeout=10)
            )
            latencia = int((time.time() - inicio) * 1000)
            if latencia > 3000:
                await self.log(f"⚠️ Servidor lento: {latencia}ms — considere reintentar más tarde")
            else:
                await self.log(f"🌐 Latencia servidor: {latencia}ms — OK")
        except Exception as e:
            await self.log(f"⚠️ No se pudo verificar latencia: {str(e)[:60]}")

    # ── Finalización ─────────────────────────────────────────────────────────

    async def _finalizar_proceso(self):
        if not self.cancelado:
            if self.proceso_viaje_exitoso:
                self._limpiar_checkpoint()
            else:
                await self.log("💾 Checkpoint conservado — el proceso no completó todas las páginas")

            tiempo_total      = time.time() - self.tiempo_inicio
            tiempo_formateado = str(timedelta(seconds=int(tiempo_total)))

            await self.log(f"\n {'='*50}")
            await self.log(f" 🕑 Completado en {tiempo_formateado}")
            await self.log(f" ✅ Viaje procesado: {self.numero_viaje}")
            await self.log(f" 📌 Tipo incidencia: {self.codigo_desviacion}")
            await self.log(f" {'='*50}")

            results = {
                "viaje": self.numero_viaje,
                "paginas_procesadas": self.paginas_procesadas,
                "total_paginas": self.total_paginas,
                "exitoso": self.proceso_viaje_exitoso,
                "tiempo_total": tiempo_formateado,
            }
            await self.jm.emit_finalizado(self.job_id, results)
        else:
            await self.log(f"💾 Checkpoint guardado en página {self.paginas_procesadas} — reanudar desde {self.paginas_procesadas + 1}")
            checkpoint_info = {
                "paginas_procesadas": self.paginas_procesadas,
                "total_paginas": self.total_paginas,
            }
            await self.jm.emit_cancelado(self.job_id, checkpoint_info)

    # ── Punto de entrada ─────────────────────────────────────────────────────

    async def ejecutar(self):
        """Método principal — se ejecuta como background task de FastAPI."""
        self.lock = asyncio.Lock()
        self.jm.marcar_running(self.job_id)

        try:
            self.tiempo_inicio = time.time()
            await self.estado(f"Procesando viaje {self.numero_viaje} en 7.3.2...")

            await self.log(f"\n {'='*50}")
            await self.log(f" 🚀 INICIANDO PROCESO")
            await self.log(f" {'='*50}")
            await self.log(f" 👤 Usuario: {self.usuario}")
            await self.log(f" 📍 Ciudad: {self.ciudad}")
            await self.log(f" 🎫 Viaje: {self.numero_viaje}")
            await self.log(f" 📌 Tipo: {self.codigo_desviacion}")
            await self.log(f" 📝 Observaciones: {self.observaciones}")
            await self.log(f" {'='*50}\n")

            await self._verificar_latencia_servidor()

            async with async_playwright() as p:
                try:
                    inicializado = await self._inicializar_navegadores(p)
                    if inicializado and not self.cancelado:
                        tareas      = [self.trabajador_navegador(i + 1) for i in range(self.num_navegadores)]
                        timer_task  = asyncio.ensure_future(self._emitir_tiempo_transcurrido())
                        try:
                            await asyncio.gather(*tareas)
                        finally:
                            timer_task.cancel()
                            try:
                                await timer_task
                            except asyncio.CancelledError:
                                pass
                finally:
                    for browser in self.browsers:
                        try:
                            if browser:
                                await browser.close()
                        except Exception:
                            pass

            await self._finalizar_proceso()

        except Exception as e:
            import traceback
            error_data = {
                "message": f"Error: {str(e)}",
                "paginas_procesadas": self.paginas_procesadas,
                "total_paginas": self.total_paginas,
            }
            await self.jm.emit_error(self.job_id, error_data)
            await self.log(f"🔴 Detalle: {traceback.format_exc()}")
