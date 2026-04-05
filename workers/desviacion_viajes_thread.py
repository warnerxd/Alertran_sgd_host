# workers/desviacion_viajes_thread.py
"""
Thread para el procesamiento de desviación de viajes
"""
from datetime import datetime, timedelta
import asyncio
import time
import re
import urllib.request
from playwright.async_api import async_playwright
from typing import List, Union
from pathlib import Path

from workers.base_worker import BaseWorker
from config.settings import (
    MAX_REINTENTOS, TIEMPO_ESPERA_CLICK, TIEMPO_ESPERA_NAVEGACION,
    TIEMPO_ESPERA_INGRESO_CODIGOS, TIEMPO_ESPERA_VOLVER, URL_ALERTRAN
)
from config.constants import TIPOS_INCIDENCIA

class DesviacionViajesThread(BaseWorker):
    """Thread para desviación de viajes"""

    def __init__(self, usuario, password, ciudad, numero_viaje, codigo_desviacion, observaciones, num_navegadores, headless=False, pagina_inicio=1):
        super().__init__()   # inicializa senales, flags, pages, file_utils, etc.
        self.usuario = usuario
        self.password = password
        self.ciudad = ciudad
        self.numero_viaje = numero_viaje
        self.codigo_desviacion = codigo_desviacion
        self.observaciones = observaciones
        self.headless = headless
        self.pagina_inicio = max(1, int(pagina_inicio))

        # Validar num_navegadores
        if num_navegadores is None:
            num_navegadores = 1
        try:
            num_navegadores = int(num_navegadores)
        except Exception:
            num_navegadores = 1
        self.num_navegadores = min(num_navegadores, 10)

        # Estado del proceso
        self.guias_error = []
        self.guias_advertencia = []
        self.guias_procesadas_exito = set()
        self.guias_procesadas_ent = set()
        self.guias_en_error = set()

        # Resultado de paginación (se actualiza en procesar_viaje_con_carta_porte)
        self.paginas_procesadas = 0
        self.total_paginas = 0
        self.proceso_viaje_exitoso = False  # True solo si todas las páginas completaron

        # Variables para incidencias
        self.tipos_incidencia = TIPOS_INCIDENCIA

    async def seleccionar_base(self, menu, nav_idx):
        """Intenta seleccionar la base usando diferentes estrategias"""
        
        # Extraer código de ciudad (primeras 3 letras)
        ciudad_codigo = self.ciudad[:3] if self.ciudad and len(self.ciudad) >= 3 else "ABA"
        
        self.senales.log.emit(f"🔍 [Nav{nav_idx}] Intentando seleccionar base para código: {ciudad_codigo}")
        
        # Estrategia 1: Buscar por celda con span que contenga el código
        try:
            base_selector = menu.locator(f'td:has-text("{ciudad_codigo}") span')
            if await base_selector.count() > 0:
                await base_selector.first.click(timeout=5000)
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Base seleccionada por span con código {ciudad_codigo}")
                await asyncio.sleep(1)
                return True
        except Exception as e:
            self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] Estrategia 1 no funcionó: {str(e)[:50]}")
        
        # Estrategia 2: Buscar por celda que contenga el código
        try:
            base_selector = menu.locator(f'td:has-text("{ciudad_codigo}")')
            if await base_selector.count() > 0:
                await base_selector.first.click(timeout=5000)
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Base seleccionada por celda con código {ciudad_codigo}")
                await asyncio.sleep(1)
                return True
        except Exception as e:
            self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] Estrategia 2 no funcionó: {str(e)[:50]}")
        
        # Estrategia 3: Buscar cualquier elemento que contenga el código
        try:
            base_selector = menu.get_by_text(re.compile(f"{ciudad_codigo}.*", re.IGNORECASE))
            if await base_selector.count() > 0:
                await base_selector.first.click(timeout=5000)
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Base seleccionada por texto con código {ciudad_codigo}")
                await asyncio.sleep(1)
                return True
        except Exception as e:
            self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] Estrategia 3 no funcionó: {str(e)[:50]}")
        
        # Estrategia 4: Buscar por el nombre completo de la ciudad
        try:
            ciudad_nombre = self.ciudad[4:] if len(self.ciudad) > 4 else ""
            if ciudad_nombre:
                base_selector = menu.get_by_text(re.compile(f".*{ciudad_nombre}.*", re.IGNORECASE))
                if await base_selector.count() > 0:
                    await base_selector.first.click(timeout=5000)
                    self.senales.log.emit(f"✅ [Nav{nav_idx}] Base seleccionada por nombre: {ciudad_nombre[:20]}")
                    await asyncio.sleep(1)
                    return True
        except Exception as e:
            self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] Estrategia 4 no funcionó: {str(e)[:50]}")
        
        # Estrategia 5: Buscar por rol de celda
        try:
            base_selector = menu.get_by_role("cell").filter(has_text=re.compile(ciudad_codigo, re.IGNORECASE))
            if await base_selector.count() > 0:
                await base_selector.first.click(timeout=5000)
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Base seleccionada por cell role con código {ciudad_codigo}")
                await asyncio.sleep(1)
                return True
        except Exception as e:
            self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] Estrategia 5 no funcionó: {str(e)[:50]}")
        
        self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] No fue necesario seleccionar base o no se encontró")
        return False

    async def navegar_a_funcionalidad_base(self, page, nav_idx):
        """Navegación base hasta el menú principal"""
        try:
            if not await self.verificar_pagina_activa(page):
                return False
            
            menu = page.frame_locator('frame[name="menu"]')
            
            # Seleccionar base si es necesario
            await self.seleccionar_base(menu, nav_idx)

            # Seleccionar ciudad
            try:
                self.senales.log.emit(f"🔍 [Nav{nav_idx}] Buscando ciudad: {self.ciudad}")
                ciudad_selector = menu.get_by_role("list").get_by_text(self.ciudad, exact=False)
                if await ciudad_selector.count() > 0:
                    await ciudad_selector.first.click(timeout=5000)
                    self.senales.log.emit(f"✅ [Nav{nav_idx}] Ciudad seleccionada: {self.ciudad}")
                    await asyncio.sleep(TIEMPO_ESPERA_CLICK * 2 / 1000)
                else:
                    self.senales.log.emit(f"⚠️ [Nav{nav_idx}] No se encontró la ciudad: {self.ciudad}")
            except Exception as e:
                self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] Error seleccionando ciudad: {str(e)[:50]}")
            
            return menu
            
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error en navegación base: {str(e)}")
            return None

    async def navegar_a_7_3_2(self, page, menu, nav_idx):
        """Navega específicamente a la funcionalidad 7.3.2"""
        try:
            # Ingresar funcionalidad 7.3.2
            funcionalidad = menu.locator('input[name="funcionalidad_codigo"]:not([type="hidden"])')
            await funcionalidad.wait_for(state="visible", timeout=20000)
            await funcionalidad.fill("")
            await asyncio.sleep(0.2)
            await funcionalidad.fill("7.3.2")
            await asyncio.sleep(0.2)
            await funcionalidad.press("Enter")
            self.senales.log.emit(f"⌨️ [Nav{nav_idx}] Funcionalidad 7.3.2 ingresada")

            await self.esperar_overlay(page)
            await asyncio.sleep(TIEMPO_ESPERA_NAVEGACION / 1000)
            
            self.senales.log.emit(f"✅ [Nav{nav_idx}] Navegación a 7.3.2 completada")
            return True
            
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error navegando a 7.3.2: {str(e)}")
            return False

    # ============ MÉTODO PARA BUSCAR CARTA PORTE ============
    async def buscar_carta_porte(self, page, nav_idx):
        """Busca la carta porte en la pantalla de 7.3.2"""
        try:
            self.senales.log.emit(f"🔍 [Nav{nav_idx}] Buscando carta porte: {self.numero_viaje}")
            
            # Obtener frames
            menu_frame = page.frame_locator('frame[name="menu"]')
            principal = menu_frame.frame_locator('iframe[name="principal"]')
            filtro = principal.frame_locator('frame[name="filtro"]')
            
            # Buscar el campo carta_porte y llenarlo
            campo_carta = filtro.locator('input[name="carta_porte"]')
            if await campo_carta.count() > 0:
                await campo_carta.click()
                await campo_carta.fill(self.numero_viaje)
                await asyncio.sleep(0.5)
                
                # Hacer clic en Buscar
                await filtro.get_by_role("button", name="Buscar").click()
                await self.esperar_overlay(page)
                await asyncio.sleep(3)
                
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Búsqueda completada")
                return True
            else:
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] No se encontró campo carta_porte")
                return False
                
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error en búsqueda: {str(e)}")
            return False

    # ============ MÉTODO PARA REOBTENER FRAMES ============
    async def reobtener_frames(self, page):
        """Reobtiene los frames después de una recarga de página"""
        menu_frame = page.frame_locator('frame[name="menu"]')
        principal = menu_frame.frame_locator('iframe[name="principal"]')
        resultado = principal.frame_locator('frame[name="resultado"]')
        return resultado

    # ============ MÉTODOS PARA PAGINACIÓN ============
    async def obtener_total_paginas(self, resultado, nav_idx):
        """Obtiene el número total de páginas de resultados usando los campos ocultos"""
        try:
            # Buscar el campo oculto pagina_maximo
            pagina_maximo_element = resultado.locator('input[name="pagina_maximo"]')
            if await pagina_maximo_element.count() > 0:
                valor = await pagina_maximo_element.first.get_attribute("value")
                if valor and valor.isdigit():
                    total_paginas = int(valor)
                    self.senales.log.emit(f"📄 [Nav{nav_idx}] Páginas totales: {total_paginas}")
                    return total_paginas
            
            # Si no hay paginación, asumimos que es una sola página
            self.senales.log.emit(f"📄 [Nav{nav_idx}] No se detectó paginación, asumiendo 1 página")
            return 1
            
        except Exception as e:
            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Error obteniendo páginas: {str(e)}")
            return 1

    async def ir_a_siguiente_pagina(self, page, resultado, nav_idx, pagina_actual, total_paginas):
        """Navega a la siguiente página con reintentos y múltiples estrategias"""
        try:
            siguiente_numero = pagina_actual + 1

            # Estrategia 1: Enlace "Siguiente" con backoff progresivo (#8: 5s, 10s, 15s)
            _esperas = [5, 10, 15]
            for intento in range(1, 4):
                resultado = await self.reobtener_frames(page)
                siguiente_link = resultado.get_by_role("link", name="Siguiente")
                if await siguiente_link.count() > 0:
                    self.senales.log.emit(f"➡️ [Nav{nav_idx}] Haciendo clic en Siguiente")
                    await siguiente_link.first.click()
                    await self.esperar_overlay(page)
                    # Espera dinámica: aguardar checkbox visible en lugar de sleep fijo (#3)
                    try:
                        await resultado.locator('input[name="all"]').wait_for(state="visible", timeout=8000)
                    except Exception:
                        await asyncio.sleep(3)
                    return True
                if intento < 3:
                    espera = _esperas[intento - 1]
                    self.senales.log.emit(f"⏳ [Nav{nav_idx}] Esperando paginación... (intento {intento}/3, {espera}s)")
                    await asyncio.sleep(espera)

            # Estrategia 2: Enlace con número de página (fallback)
            enlace_numero = resultado.locator(f'a:has-text("{siguiente_numero}")')
            if await enlace_numero.count() > 0:
                self.senales.log.emit(f"➡️ [Nav{nav_idx}] Haciendo clic en página {siguiente_numero}")
                await enlace_numero.first.click()
                await self.esperar_overlay(page)
                try:
                    await resultado.locator('input[name="all"]').wait_for(state="visible", timeout=8000)
                except Exception:
                    await asyncio.sleep(3)
                return True

            # Estrategia 3: Submit del form con pagina_actual+1 vía JavaScript (#2)
            self.senales.log.emit(f"⏳ [Nav{nav_idx}] Intentando navegación JS a página {siguiente_numero}...")
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
                    self.senales.log.emit(f"➡️ [Nav{nav_idx}] Navegación JS a página {siguiente_numero} exitosa")
                    return True
            except Exception as js_err:
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] JS fallback falló: {str(js_err)[:60]}")

            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] No se encontró enlace para página {siguiente_numero}")
            return False

        except Exception as e:
            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Error al ir a siguiente página: {str(e)}")
            return False

    # ============ MÉTODO PARA ASIGNAR INCIDENCIA ============
    async def asignar_incidencia(self, page, resultado, tipo, nav_idx):
        """Asigna la incidencia a los envíos seleccionados y maneja el diálogo.
        Reintenta si el sistema devuelve 'No hay ningun tipo de incidencia seleccionada'."""

        _ERROR_INCIDENCIA = "no hay ningun tipo de incidencia"

        for intento in range(1, MAX_REINTENTOS + 1):
            try:
                self.senales.log.emit(
                    f"🔄 [Nav{nav_idx}] Asignando incidencia tipo {tipo}"
                    + (f" (intento {intento}/{MAX_REINTENTOS})" if intento > 1 else "")
                )

                # 1. INGRESAR CÓDIGO DE INCIDENCIA
                incidencia_input = resultado.locator('input[name="incidencia_codigo"]').first
                if await incidencia_input.count() > 0:
                    await incidencia_input.click(click_count=3)
                    await incidencia_input.fill("")
                    await asyncio.sleep(0.2)
                    await incidencia_input.fill(tipo)
                    # En reintentos usar Tab para forzar el onblur de validación
                    if intento > 1:
                        await incidencia_input.press("Tab")
                        await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)
                    await incidencia_input.press("Enter")
                    self.senales.log.emit(f"✅ [Nav{nav_idx}] Código incidencia {tipo} ingresado")
                    await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)

                # 2. INGRESAR FUENTE (018)
                fuente_input = resultado.locator('input[name="tipo_origen_incidencia_codigo"]').first
                if await fuente_input.count() > 0:
                    await fuente_input.click(click_count=3)
                    await fuente_input.fill("018")
                    await fuente_input.press("Enter")
                    self.senales.log.emit(f"✅ [Nav{nav_idx}] Fuente 018 ingresada")
                    await asyncio.sleep(TIEMPO_ESPERA_INGRESO_CODIGOS / 1000)

                # 3. INGRESAR AMPLIACIÓN
                ampliacion_input = resultado.locator('textarea[name="ampliacion_incidencia"]').first
                if await ampliacion_input.count() > 0:
                    await ampliacion_input.click()
                    await ampliacion_input.fill(self.observaciones)
                    self.senales.log.emit(f"✅ [Nav{nav_idx}] Ampliación ingresada")
                    await asyncio.sleep(0.5)

                # 4. HACER CLIC EN ACEPTAR Y CAPTURAR MENSAJE DEL DIÁLOGO
                self.senales.log.emit(f"🖱️ [Nav{nav_idx}] Haciendo clic en Aceptar")
                dialog_info = {"mensaje": ""}

                async def _on_dialog(dialog):
                    dialog_info["mensaje"] = dialog.message
                    self.senales.log.emit(f"💬 [Nav{nav_idx}] Diálogo: {dialog.message}")
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
                await asyncio.sleep(4)  # #1 aumentado de 2s a 4s para tráfico pesado

                # 5. VERIFICAR SI EL DIÁLOGO FUE UN ERROR DE INCIDENCIA
                if _ERROR_INCIDENCIA in dialog_info["mensaje"].lower():
                    if intento < MAX_REINTENTOS:
                        self.senales.log.emit(
                            f"⚠️ [Nav{nav_idx}] Incidencia no reconocida — reintentando "
                            f"({intento}/{MAX_REINTENTOS})..."
                        )
                        await asyncio.sleep(2)
                        continue  # volver al inicio del for
                    else:
                        self.senales.log.emit(
                            f"❌ [Nav{nav_idx}] No se pudo asignar incidencia tras "
                            f"{MAX_REINTENTOS} intentos: tipo {tipo} no válido"
                        )
                        return False

                self.senales.log.emit(f"✅ [Nav{nav_idx}] Incidencia {tipo} asignada correctamente")
                return True

            except Exception as e:
                err_str = str(e)
                # #7 — Si es timeout (fallo de red), reintentar la página completa
                if "Timeout" in err_str or "timeout" in err_str:
                    self.senales.log.emit(
                        f"⏳ [Nav{nav_idx}] Timeout detectado — reintentando página "
                        f"({intento}/{MAX_REINTENTOS})..."
                    )
                    if intento >= MAX_REINTENTOS:
                        return False
                    await asyncio.sleep(4)
                    continue
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Error en intento {intento}: {err_str}")
                if intento >= MAX_REINTENTOS:
                    return False
                await asyncio.sleep(4)

        return False

    # ============ MÉTODO PARA SELECCIONAR TODOS LOS ENVÍOS ============
    async def seleccionar_todos_envios(self, resultado, nav_idx):
        """Selecciona todos los envíos de la página actual"""
        try:
            # Buscar checkbox para seleccionar todos
            checkbox_all = resultado.locator('input[name="all"]').first
            if await checkbox_all.count() > 0:
                await checkbox_all.check()
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Seleccionados todos los envíos de la página")
                await asyncio.sleep(1)
                return True
            
            # Si no encuentra "all", buscar checkboxes individuales
            checkboxes = resultado.locator('input[type="checkbox"]')
            n = await checkboxes.count()
            if n > 0:
                for i in range(n):
                    await checkboxes.nth(i).check()
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Seleccionados {n} envíos")
                await asyncio.sleep(1)
                return True
                
            return False
        except Exception as e:
            self.senales.log.emit(f"⚠️ [Nav{nav_idx}] Error seleccionando envíos: {str(e)}")
            return False

    # ============ MÉTODO PARA PROCESAR VIAJE CON CARTA PORTE ============
    async def procesar_viaje_con_carta_porte(self, page, nav_idx):
        """Procesa un viaje usando el número de carta porte con paginación"""
        try:
            guia = self.numero_viaje
            self.senales.log.emit(f"🔍 [Nav{nav_idx}] Procesando carta porte: {guia}")
            
            # Obtener frames iniciales
            menu_frame = page.frame_locator('frame[name="menu"]')
            principal = menu_frame.frame_locator('iframe[name="principal"]')
            resultado = principal.frame_locator('frame[name="resultado"]')
            
            # Verificar si hay resultados
            if await self.detectar_sin_resultados(page):
                error_msg = "Carta porte sin resultados"
                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] {error_msg}")
                return False
            
            # Obtener número total de páginas
            total_paginas = await self.obtener_total_paginas(resultado, nav_idx)
            self.total_paginas = total_paginas   # actualizar inmediatamente para el resumen
            self.senales.log.emit(f"📄 [Nav{nav_idx}] Total de páginas a procesar: {total_paginas}")

            tipo = self.codigo_desviacion
            paginas_procesadas = 0

            # Navegar hasta la página de checkpoint si se reanuda
            pagina_inicio = max(1, self.pagina_inicio)
            if pagina_inicio > 1:
                self.senales.log.emit(f"⏩ [Nav{nav_idx}] Reanudando desde página {pagina_inicio} — navegando...")
                for _p in range(1, pagina_inicio):
                    resultado = await self.reobtener_frames(page)
                    avanzado = await self.ir_a_siguiente_pagina(page, resultado, nav_idx, _p, total_paginas)
                    if not avanzado:
                        self.senales.log.emit(f"⚠️ [Nav{nav_idx}] No se pudo llegar a página {pagina_inicio}, iniciando desde página {_p + 1}")
                        pagina_inicio = _p + 1
                        break
                    await asyncio.sleep(1)
                self.senales.log.emit(f"✅ [Nav{nav_idx}] Posicionado en página {pagina_inicio}")

            # Procesar cada página desde el checkpoint
            for pagina in range(pagina_inicio, total_paginas + 1):
                await self.check_pausa()
                if self.cancelado:
                    return False

                # Progreso proporcional al avance de páginas (ajustado al rango pendiente)
                self.senales.progreso.emit(int(pagina / total_paginas * 90))

                # REOBTENER FRAMES CADA VEZ (importante después de recargas)
                resultado = await self.reobtener_frames(page)

                # Log de página del sistema vs página lógica (#5)
                try:
                    pag_sys = await resultado.locator('input[name="pagina_actual"]').first.get_attribute("value")
                    self.senales.log.emit(f"📄 [Nav{nav_idx}] ===== PÁGINA {pagina} DE {total_paginas} (sistema: {pag_sys}) =====")
                except Exception:
                    self.senales.log.emit(f"📄 [Nav{nav_idx}] ===== PÁGINA {pagina} DE {total_paginas} =====")

                # Detección de fin real: si no hay checkbox no quedan envíos (#4)
                if await resultado.locator('input[name="all"]').count() == 0:
                    self.senales.log.emit(f"✅ [Nav{nav_idx}] Sin envíos pendientes — proceso completo")
                    break

                # 1. Seleccionar todos los envíos de la página
                seleccionados = await self.seleccionar_todos_envios(resultado, nav_idx)

                if seleccionados:
                    # 2. Asignar incidencia a los seleccionados
                    exito = await self.asignar_incidencia(page, resultado, tipo, nav_idx)

                    if exito:
                        paginas_procesadas += 1
                        self.paginas_procesadas = paginas_procesadas  # actualizar en tiempo real
                        self._guardar_checkpoint(pagina)
                        self.senales.log.emit(f"✅ [Nav{nav_idx}] Página {pagina} procesada correctamente")

                        # 3. Si no es la última página, ir a la siguiente
                        if pagina < total_paginas:
                            self.senales.log.emit(f"⏳ [Nav{nav_idx}] Preparando para ir a página {pagina + 1}...")
                            await asyncio.sleep(2)

                            resultado = await self.reobtener_frames(page)
                            siguiente = await self.ir_a_siguiente_pagina(page, resultado, nav_idx, pagina, total_paginas)
                            if not siguiente:
                                self.senales.log.emit(f"⚠️ [Nav{nav_idx}] No se pudo avanzar a la página {pagina + 1}")
                                break

                            await self.esperar_overlay(page)
                            await asyncio.sleep(2)
                            self.senales.log.emit(f"✅ [Nav{nav_idx}] Cargada página {pagina + 1}")
                    else:
                        self.senales.log.emit(f"❌ [Nav{nav_idx}] Error procesando página {pagina}")
                        break
                else:
                    self.senales.log.emit(f"⚠️ [Nav{nav_idx}] No hay envíos para seleccionar en página {pagina}")

                    if pagina < total_paginas:
                        self.senales.log.emit(f"⏳ [Nav{nav_idx}] Intentando avanzar a página {pagina + 1} sin procesar...")
                        await asyncio.sleep(1)
                        resultado = await self.reobtener_frames(page)
                        siguiente = await self.ir_a_siguiente_pagina(page, resultado, nav_idx, pagina, total_paginas)
                        if not siguiente:
                            break

            self.paginas_procesadas = paginas_procesadas
            self.total_paginas = total_paginas
            self.senales.log.emit(f"🎉 [Nav{nav_idx}] Proceso completado - {paginas_procesadas} de {total_paginas} páginas procesadas")
            return paginas_procesadas > 0
            
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error: {str(e)}")
            return False

    # ============ MÉTODOS COMUNES ============
    async def detectar_sin_resultados(self, page):
        """Detecta si la búsqueda no arrojó resultados — busca dentro de los frames."""
        try:
            mensajes = [
                "No se encontraron datos",
                "No hay resultados",
                "No existen registros",
                "0 resultados",
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

    async def _registrar_error(self, guia, error_msg, nav_idx):
        """Registra un error"""
        async with self.lock:
            self.guias_error.append((guia, f"[Nav{nav_idx}] {error_msg}"))
            self.guias_en_error.add(guia)
        fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.senales.guia_procesada.emit(
            guia, "❌ ERROR", error_msg, f"Nav{nav_idx}", fecha
        )

    async def _emitir_tiempo_transcurrido(self):
        """Emite el tiempo transcurrido cada 10 s mientras el proceso está activo."""
        while not self.cancelado and self.procesando:
            if self.tiempo_inicio:
                elapsed = int(time.time() - self.tiempo_inicio)
                elapsed_str = str(timedelta(seconds=elapsed))
                self.senales.tiempo_restante.emit(f"⏱️ Transcurrido: {elapsed_str}")
            await asyncio.sleep(10)

    async def trabajador_navegador(self, nav_idx):
        """Worker para el navegador"""
        try:
            # El viaje es único: solo Nav1 procesa para evitar incidencias duplicadas
            if nav_idx > 1:
                self.senales.log.emit(f"ℹ️ [Nav{nav_idx}] Viaje único — procesamiento asignado a Nav1")
                return

            page = self.pages[nav_idx - 1]

            self.senales.log.emit(f"🌐 [Nav{nav_idx}] Iniciando procesamiento...")
            self.senales.progreso.emit(10)

            # Procesar viaje
            exito = await self.procesar_viaje_con_carta_porte(page, nav_idx)

            if exito:
                self.proceso_viaje_exitoso = True
                self.senales.progreso.emit(100)
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.senales.guia_procesada.emit(
                    self.numero_viaje, "✅ PROCESADO", f"Incidencia {self.codigo_desviacion}",
                    f"Nav{nav_idx}", fecha
                )
            else:
                self.senales.log.emit(f"❌ [Nav{nav_idx}] El viaje {self.numero_viaje} no se procesó correctamente")

            await asyncio.sleep(5)
            
        except Exception as e:
            self.senales.log.emit(f"❌ [Nav{nav_idx}] Error fatal: {str(e)}")

    async def _inicializar_navegadores(self, p):
        """Inicializa los navegadores"""
        for i in range(self.num_navegadores):
            if self.cancelado:
                break
                
            self.senales.log.emit(f"▶️ Iniciando navegador {i+1}/{self.num_navegadores}...")
            
            try:
                launch_args = ['--disable-dev-shm-usage']
                if not self.headless:
                    launch_args.append('--start-maximized')
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=launch_args
                )
                
                context = await browser.new_context(
                    viewport={'width': 1280, 'height': 800},
                    locale="es-ES"
                )
                
                page = await context.new_page()
                page.set_default_timeout(60000)
                
                self.browsers.append(browser)
                self.contexts.append(context)
                self.pages.append(page)
                
                self.senales.log.emit(f"🌐 [Nav{i+1}] Navegando a {URL_ALERTRAN}")
                await page.goto(URL_ALERTRAN, timeout=60000)
                await asyncio.sleep(3)
                
                if not await self.hacer_login(page, i+1):
                    self.senales.error.emit(f"Error login navegador {i+1}")
                    return False
                
                # Navegación a 7.3.2
                menu = await self.navegar_a_funcionalidad_base(page, i+1)
                if not menu:
                    self.senales.error.emit(f"Error navegación base navegador {i+1}")
                    return False
                
                if not await self.navegar_a_7_3_2(page, menu, i+1):
                    self.senales.error.emit(f"Error navegación 7.3.2 navegador {i+1}")
                    return False
                
                # Una vez en 7.3.2, buscar la carta porte
                if not await self.buscar_carta_porte(page, i+1):
                    self.senales.error.emit(f"No se encontró el campo de búsqueda en Nav{i+1}")
                    return False

                self.senales.log.emit(f"✅ [Nav{i+1}] Navegador listo en 7.3.2")
                
            except Exception as e:
                self.senales.log.emit(f"❌ [Nav{i+1}] Error inicializando: {str(e)}")
                return False
        
        return True

    def _finalizar_proceso(self):
        """Finaliza el proceso"""
        if not self.cancelado:
            if self.proceso_viaje_exitoso:
                self._limpiar_checkpoint()
            else:
                self.senales.log.emit("💾 Checkpoint conservado — el proceso no completó todas las páginas")
            tiempo_total = time.time() - self.tiempo_inicio
            tiempo_formateado = str(timedelta(seconds=int(tiempo_total)))

            self.senales.log.emit(f"\n {'='*50}")
            self.senales.log.emit(f" 🕑 Completado en {tiempo_formateado}")
            self.senales.log.emit(f" ✅ Viaje procesado: {self.numero_viaje}")
            self.senales.log.emit(f" 📌 Tipo incidencia: {self.codigo_desviacion}")
            self.senales.log.emit(f" {'='*50}")

            self.senales.finalizado.emit()
        else:
            self.senales.proceso_cancelado.emit()

    @staticmethod
    def _checkpoint_path():
        import json as _json
        from pathlib import Path as _Path
        return _Path.home() / ".alertran" / "checkpoint_viaje.json"

    def _guardar_checkpoint(self, pagina_completada: int):
        """Escribe directamente el checkpoint en un JSON dedicado"""
        import json as _json
        try:
            p = self._checkpoint_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "viaje": str(self.numero_viaje),
                "pagina_completada": pagina_completada,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            with open(p, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _limpiar_checkpoint(self):
        """Elimina el archivo de checkpoint al finalizar correctamente"""
        try:
            p = self._checkpoint_path()
            if p.exists():
                p.unlink()
        except Exception:
            pass

    async def _verificar_latencia_servidor(self):
        """Mide latencia al servidor y advierte si está lento"""
        try:
            inicio = time.time()
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: urllib.request.urlopen(URL_ALERTRAN, timeout=10)
            )
            latencia = int((time.time() - inicio) * 1000)
            if latencia > 3000:
                self.senales.log.emit(f"⚠️ Servidor lento: {latencia}ms — considere reintentar más tarde")
            else:
                self.senales.log.emit(f"🌐 Latencia servidor: {latencia}ms — OK")
        except Exception as e:
            self.senales.log.emit(f"⚠️ No se pudo verificar latencia: {str(e)[:60]}")

    async def proceso_principal(self):
        """Método principal"""
        self.lock = asyncio.Lock()
        try:
            self.tiempo_inicio = time.time()
            self.senales.estado.emit(f"Procesando viaje {self.numero_viaje} en 7.3.2...")
            self.senales.log.emit(f"\n {'='*50}")
            self.senales.log.emit(f" 🚀 INICIANDO PROCESO")
            self.senales.log.emit(f" {'='*50}")
            self.senales.log.emit(f" 👤 Usuario: {self.usuario}")
            self.senales.log.emit(f" 📍 Ciudad: {self.ciudad}")
            self.senales.log.emit(f" 🎫 Viaje: {self.numero_viaje}")
            self.senales.log.emit(f" 📌 Tipo: {self.codigo_desviacion}")
            self.senales.log.emit(f" 📝 Observaciones: {self.observaciones}")
            self.senales.log.emit(f" 🌐 Navegadores: {self.num_navegadores}")
            self.senales.log.emit(f" {'='*50}\n")

            # #6 — Ping al servidor antes de iniciar
            await self._verificar_latencia_servidor()

            async with async_playwright() as p:
                try:
                    inicializado = await self._inicializar_navegadores(p)
                    if inicializado and not self.cancelado:
                        tareas = [self.trabajador_navegador(i+1) for i in range(self.num_navegadores)]
                        timer_task = asyncio.ensure_future(self._emitir_tiempo_transcurrido())
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
                            await browser.close()
                        except Exception:
                            pass

            self._finalizar_proceso()

        except Exception as e:
            self.senales.error.emit(f"Error: {str(e)}")
            import traceback
            self.senales.log.emit(f"🔴 Detalle: {traceback.format_exc()}")

    def cancelar(self):
        """Cancela el proceso"""
        super().cancelar()
        self.senales.log.emit("🛑 Cancelando proceso...")

    def run(self):
        """Ejecuta el thread"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.proceso_principal())
        finally:
            loop.close()