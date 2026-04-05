# utils/win_blur.py
"""
Blur/Acrylic real en Windows 10/11 usando Win32 API vía ctypes.

Win10  → SetWindowCompositionAttribute  (ACCENT_ENABLE_BLURBEHIND)
Win11  → DwmSetWindowAttribute          (DWMWA_SYSTEMBACKDROP_TYPE = Acrylic/Mica)
"""
import sys
import ctypes
import ctypes.wintypes


def _win11_major() -> bool:
    """True si la build de Windows es 22000+ (Win11)."""
    try:
        ver = sys.getwindowsversion()
        return ver.major >= 10 and ver.build >= 22000
    except Exception:
        return False


# ── Win10: SetWindowCompositionAttribute ────────────────────────────────────

class _ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState",  ctypes.c_int),
        ("AccentFlags",  ctypes.c_int),
        ("GradientColor", ctypes.c_int),
        ("AnimationId",  ctypes.c_int),
    ]


class _WINCOMPATTRDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data",      ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


_ACCENT_ENABLE_BLURBEHIND  = 3   # blur semi-transparente
_ACCENT_ENABLE_ACRYLICBLUR = 4   # acrylic (Win10 1803+)
_WCA_ACCENT_POLICY         = 19


def _apply_win10_blur(hwnd: int, acrylic: bool = True, color: int = 0xCCFFFFFF):
    """Aplica blur (o acrylic) en Windows 10 vía SetWindowCompositionAttribute."""
    try:
        user32 = ctypes.windll.user32
        accent = _ACCENT_POLICY()
        accent.AccentState   = _ACCENT_ENABLE_ACRYLICBLUR if acrylic else _ACCENT_ENABLE_BLURBEHIND
        accent.AccentFlags   = 2
        accent.GradientColor = color  # AABBGGRR — alpha controla opacidad del blur

        data = _WINCOMPATTRDATA()
        data.Attribute   = _WCA_ACCENT_POLICY
        data.Data        = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData  = ctypes.sizeof(accent)

        user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return True
    except Exception:
        return False


# ── Win11: DwmSetWindowAttribute ────────────────────────────────────────────

_DWMWA_SYSTEMBACKDROP_TYPE      = 38
_DWMWA_USE_IMMERSIVE_DARK_MODE  = 20

_DWM_BACKDROP_NONE    = 1
_DWM_BACKDROP_MICA    = 2
_DWM_BACKDROP_ACRYLIC = 3
_DWM_BACKDROP_TABBED  = 4


def _apply_win11_acrylic(hwnd: int, dark: bool = False):
    """Aplica Acrylic Backdrop en Windows 11."""
    try:
        dwmapi = ctypes.windll.dwmapi
        # Habilitar dark mode si corresponde
        dark_val = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark_val), ctypes.sizeof(dark_val)
        )
        # Aplicar Acrylic
        backdrop = ctypes.c_int(_DWM_BACKDROP_ACRYLIC)
        dwmapi.DwmSetWindowAttribute(
            hwnd, _DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(backdrop), ctypes.sizeof(backdrop)
        )
        return True
    except Exception:
        return False


# ── Interfaz pública ─────────────────────────────────────────────────────────

def apply_blur(window, dark: bool = False) -> bool:
    """
    Aplica el mejor efecto de blur disponible para la versión de Windows.
    Debe llamarse DESPUÉS de show() — con QTimer.singleShot(150, ...).
    Devuelve True si tuvo éxito, False si no está en Windows o falló.
    """
    if sys.platform != "win32":
        return False
    try:
        hwnd = int(window.winId())
        if not hwnd:
            return False
        # Seleccionar color según tema: claro/oscuro
        blur_color = 0x88000000 if dark else 0xCCFFFFFF
        if _win11_major():
            return _apply_win11_acrylic(hwnd, dark=dark)
        else:
            return _apply_win10_blur(hwnd, acrylic=True, color=blur_color)
    except Exception:
        return False
