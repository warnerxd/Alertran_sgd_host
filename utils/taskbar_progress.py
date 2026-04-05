# utils/taskbar_progress.py
"""
Windows 7+ taskbar progress indicator via ITaskbarList3 COM (pure ctypes).
Sin dependencias externas — solo ctypes estándar de Python.

Opciones implementadas:
  1. SetProgressValue / SetProgressState  — barra de progreso + color
  2. SetOverlayIcon                       — badge circular de estado
  3. FlashWindowEx                        — parpadeo de alerta al terminar
"""
import sys
import math
import struct
import ctypes
import ctypes.wintypes

# ── Estados de progreso ──────────────────────────────────────────────────────
TBPF_NOPROGRESS    = 0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL        = 0x2    # verde
TBPF_ERROR         = 0x4    # rojo
TBPF_PAUSED        = 0x8    # amarillo

# ── Flags de flash ───────────────────────────────────────────────────────────
FLASHW_STOP      = 0
FLASHW_CAPTION   = 1
FLASHW_TRAY      = 2
FLASHW_ALL       = 3
FLASHW_TIMERNOFG = 12   # parpadea hasta que la ventana recibe el foco

# ── Colores de overlay (R, G, B) ─────────────────────────────────────────────
_OVERLAY_COLORS = {
    'processing': ( 76, 175,  80),   # #4CAF50  verde
    'ok':         ( 76, 175,  80),   # #4CAF50  verde
    'paused':     (255, 193,   7),   # #FFC107  ámbar
    'error':      (244,  67,  54),   # #F44336  rojo
}


# ── Helpers internos ─────────────────────────────────────────────────────────

def _make_guid(s: str):
    class _GUID(ctypes.Structure):
        _fields_ = [
            ('Data1', ctypes.c_ulong),
            ('Data2', ctypes.c_ushort),
            ('Data3', ctypes.c_ushort),
            ('Data4', ctypes.c_ubyte * 8),
        ]
    s = s.strip('{}').replace('-', '')
    g = _GUID()
    g.Data1 = int(s[0:8],  16)
    g.Data2 = int(s[8:12], 16)
    g.Data3 = int(s[12:16], 16)
    raw = bytes.fromhex(s[16:])
    for i, v in enumerate(raw):
        g.Data4[i] = v
    return g


def _make_circle_hicon(r: int, g: int, b: int, size: int = 16) -> int:
    """
    Crea un HICON circular de 32 bpp con alpha usando GDI + ctypes.
    El fondo es completamente transparente; el círculo tiene anti-aliasing.
    No requiere PIL ni dependencias externas.
    """
    if sys.platform != 'win32':
        return 0
    try:
        gdi32  = ctypes.windll.gdi32
        user32 = ctypes.windll.user32

        # Generar píxeles BGRA (orden de bytes en DIB Windows)
        cx = cy = size / 2.0
        radius = size / 2.0 - 1.5
        pixels = bytearray(size * size * 4)
        for py in range(size):
            for px_ in range(size):
                dx   = px_ + 0.5 - cx
                dy   = py  + 0.5 - cy
                dist = math.sqrt(dx * dx + dy * dy)
                if dist <= radius:
                    alpha = 255 if dist <= radius - 1.0 else int((radius - dist) * 255)
                    idx = (py * size + px_) * 4
                    pixels[idx]     = b
                    pixels[idx + 1] = g
                    pixels[idx + 2] = r
                    pixels[idx + 3] = alpha
                # else: 0,0,0,0 → transparente

        # BITMAPINFOHEADER para DIB 32 bpp top-down
        bih = struct.pack('<IiiHHIIiiII',
                          40, size, -size, 1, 32, 0, 0, 0, 0, 0, 0)

        class _BMPINFO(ctypes.Structure):
            _fields_ = [('hdr', ctypes.c_byte * 40), ('clr', ctypes.c_byte * 4)]

        bmi = _BMPINFO()
        ctypes.memmove(bmi.hdr, bih, 40)

        hdc = user32.GetDC(None)
        pv  = ctypes.c_void_p()
        hbm_color = gdi32.CreateDIBSection(
            hdc, ctypes.byref(bmi), 0, ctypes.byref(pv), None, 0)
        user32.ReleaseDC(None, hdc)

        if not hbm_color or not pv:
            return 0

        ctypes.memmove(pv, bytes(pixels), len(pixels))

        # Máscara monochrome a ceros — el alpha del DIB controla la transparencia
        stride   = ((size + 15) // 16) * 2
        hbm_mask = gdi32.CreateBitmap(
            size, size, 1, 1,
            ctypes.create_string_buffer(stride * size))

        class _ICONINFO(ctypes.Structure):
            _fields_ = [
                ('fIcon',    ctypes.wintypes.BOOL),
                ('xHotspot', ctypes.wintypes.DWORD),
                ('yHotspot', ctypes.wintypes.DWORD),
                ('hbmMask',  ctypes.wintypes.HANDLE),
                ('hbmColor', ctypes.wintypes.HANDLE),
            ]

        ii = _ICONINFO(fIcon=True, xHotspot=0, yHotspot=0,
                       hbmMask=hbm_mask, hbmColor=hbm_color)
        hicon = user32.CreateIconIndirect(ctypes.byref(ii))
        gdi32.DeleteObject(hbm_color)
        gdi32.DeleteObject(hbm_mask)
        return int(hicon) if hicon else 0
    except Exception:
        return 0


# ── Clase principal ───────────────────────────────────────────────────────────

class TaskbarProgress:
    """
    Controla el ícono de la barra de tareas de Windows.

    Uso:
        tb = TaskbarProgress(int(self.winId()))

        # Progreso
        tb.set_value(50)             # 50 % — barra verde
        tb.set_state(TBPF_PAUSED)   # amarillo
        tb.set_state(TBPF_ERROR)    # rojo
        tb.indeterminate()           # animación pulsante
        tb.clear()                   # quitar indicador

        # Overlay badge
        tb.set_overlay('processing') # círculo verde
        tb.set_overlay('paused')     # círculo ámbar
        tb.set_overlay('error')      # círculo rojo
        tb.set_overlay(None)         # quitar badge

        # Flash de alerta
        tb.flash(count=3)            # parpadea 3 veces
    """

    _CLSID = '{56FDF344-FD6D-11D0-958A-006097C9A090}'
    _IID   = '{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}'

    def __init__(self, hwnd: int):
        self._hwnd = hwnd
        self._ptr  = None
        self._SetProgressValue = None
        self._SetProgressState = None
        self._SetOverlayIcon   = None
        self._overlay_icons    = {}   # name → HICON handle

        if sys.platform != 'win32':
            return
        try:
            ole32 = ctypes.windll.ole32
            ole32.CoInitialize(None)

            clsid = _make_guid(self._CLSID)
            iid   = _make_guid(self._IID)

            ptr = ctypes.c_void_p()
            hr  = ole32.CoCreateInstance(
                ctypes.byref(clsid), None, 1 | 4,
                ctypes.byref(iid), ctypes.byref(ptr))
            if hr != 0:
                return

            vt = ctypes.cast(
                ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0],
                ctypes.POINTER(ctypes.c_void_p))

            # HrInit — activa la interfaz (slot 3)
            _HrInit = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p)(vt[3])
            _HrInit(ptr)

            self._ptr = ptr

            # Slot 9: SetProgressValue
            self._SetProgressValue = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p,
                ctypes.wintypes.HWND,
                ctypes.c_ulonglong, ctypes.c_ulonglong,
            )(vt[9])

            # Slot 10: SetProgressState
            self._SetProgressState = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p,
                ctypes.wintypes.HWND, ctypes.c_int,
            )(vt[10])

            # Slot 18: SetOverlayIcon
            self._SetOverlayIcon = ctypes.WINFUNCTYPE(
                ctypes.HRESULT, ctypes.c_void_p,
                ctypes.wintypes.HWND,
                ctypes.wintypes.HANDLE,
                ctypes.c_wchar_p,
            )(vt[18])

            # Pre-crear íconos de overlay
            for name, (ri, gi, bi) in _OVERLAY_COLORS.items():
                h = _make_circle_hicon(ri, gi, bi, 16)
                if h:
                    self._overlay_icons[name] = h

        except Exception:
            self._ptr = None

    # ── Barra de progreso ────────────────────────────────────────────────────

    def set_value(self, value: int, total: int = 100):
        """Establece el porcentaje (barra verde). value y total deben ser > 0."""
        if not self._ptr or total <= 0:
            return
        try:
            self._SetProgressState(self._ptr, self._hwnd, TBPF_NORMAL)
            self._SetProgressValue(self._ptr, self._hwnd,
                                   max(0, min(value, total)), total)
        except Exception:
            pass

    def set_state(self, state: int):
        """Cambia el color/estado sin modificar el valor actual."""
        if not self._ptr:
            return
        try:
            self._SetProgressState(self._ptr, self._hwnd, state)
        except Exception:
            pass

    def indeterminate(self):
        """Animación pulsante — útil durante la inicialización."""
        self.set_state(TBPF_INDETERMINATE)

    def clear(self):
        """Quita el indicador de progreso del ícono."""
        self.set_state(TBPF_NOPROGRESS)

    # ── Overlay badge ────────────────────────────────────────────────────────

    def set_overlay(self, state=None):
        """
        Muestra un círculo de color sobre el ícono de la barra de tareas.

        state: 'processing' | 'ok' | 'paused' | 'error' | None (quitar)
        """
        if not self._ptr or not self._SetOverlayIcon:
            return
        try:
            hicon = self._overlay_icons.get(state, 0) if state else 0
            self._SetOverlayIcon(self._ptr, self._hwnd, hicon, state or '')
        except Exception:
            pass

    def clear_overlay(self):
        """Quita el badge del ícono."""
        self.set_overlay(None)

    # ── Flash de alerta ──────────────────────────────────────────────────────

    def flash(self, count: int = 3, flags: int = FLASHW_ALL):
        """
        Hace parpadear el botón de la barra de tareas para alertar al usuario.
        Útil cuando el proceso termina con la ventana en segundo plano.

        count=0 + flags=FLASHW_TIMERNOFG → parpadea hasta que la ventana recibe el foco.
        """
        if sys.platform != 'win32':
            return
        try:
            class _FLASHWINFO(ctypes.Structure):
                _fields_ = [
                    ('cbSize',    ctypes.wintypes.UINT),
                    ('hwnd',      ctypes.wintypes.HWND),
                    ('dwFlags',   ctypes.wintypes.DWORD),
                    ('uCount',    ctypes.wintypes.UINT),
                    ('dwTimeout', ctypes.wintypes.DWORD),
                ]
            fi = _FLASHWINFO()
            fi.cbSize    = ctypes.sizeof(_FLASHWINFO)
            fi.hwnd      = self._hwnd
            fi.dwFlags   = flags
            fi.uCount    = count
            fi.dwTimeout = 0  # usa el cursor blink rate del sistema
            ctypes.windll.user32.FlashWindowEx(ctypes.byref(fi))
        except Exception:
            pass

    # ── Limpieza ─────────────────────────────────────────────────────────────

    def destroy(self):
        """Libera los HICONs creados. Llamar al cerrar la ventana."""
        if sys.platform != 'win32':
            return
        for h in self._overlay_icons.values():
            try:
                ctypes.windll.user32.DestroyIcon(h)
            except Exception:
                pass
        self._overlay_icons.clear()
