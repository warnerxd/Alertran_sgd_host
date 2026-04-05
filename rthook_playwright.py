# rthook_playwright.py
# Runtime hook: ajusta rutas de Playwright en el ejecutable congelado.
import os
import sys

if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS

    # ── Driver (node.exe + CLI JS) ────────────────────────────────────────────
    _driver_dir = os.path.join(_base, 'playwright', 'driver')
    _node_exe   = os.path.join(_driver_dir, 'node.exe')
    if os.path.isfile(_node_exe):
        os.environ['PLAYWRIGHT_DRIVER_PATH'] = _node_exe

    # ── Navegadores ───────────────────────────────────────────────────────────
    # Forzar que Playwright busque los navegadores en la ubicación estándar
    # del usuario (%LOCALAPPDATA%\ms-playwright) y NO dentro del directorio
    # temporal de extracción del exe (_MEI*).
    _local = os.environ.get('LOCALAPPDATA', '')
    if _local:
        _browsers = os.path.join(_local, 'ms-playwright')
        os.environ['PLAYWRIGHT_BROWSERS_PATH'] = _browsers
