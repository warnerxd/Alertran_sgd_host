# ui/resumen_viaje_window.py
"""
Ventana de resumen final del proceso de Desviación de Viajes.
Diseño glass macOS Sonoma — enfocado en un único viaje / carta porte.
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QWidget, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from datetime import datetime
from utils import theme


# ── Helpers glass ────────────────────────────────────────────────────────────

def _glass_bg(alpha: float = 0.82) -> str:
    if theme.is_dark():
        return f"rgba(44, 44, 46, {alpha})"
    return f"rgba(255, 255, 255, {alpha})"


def _glass_border() -> str:
    if theme.is_dark():
        return "rgba(80, 80, 82, 0.7)"
    return "rgba(255, 255, 255, 0.95)"


# ── Subwidgets ────────────────────────────────────────────────────────────────

class _InfoCard(QFrame):
    """Tarjeta glass pequeña: ícono + etiqueta + valor."""

    def __init__(self, icon: str, label: str, value: str, color: str, parent=None):
        super().__init__(parent)
        c = theme.colors()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(120)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(14, 10, 14, 10)
        vl.setSpacing(5)

        lbl_top = QLabel(f"{icon}  {label}")
        lbl_top.setStyleSheet(
            f"color: {c['text3']}; font-size: 7.5pt; font-weight: 600;"
            f" letter-spacing: 0.3px; background: transparent; border: none;"
        )
        vl.addWidget(lbl_top)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {c['border']}; border: none;")
        vl.addWidget(sep)

        val_lbl = QLabel(str(value))
        val_lbl.setFont(QFont("SF Pro Display", 11, QFont.Weight.Bold))
        val_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )
        val_lbl.setWordWrap(False)
        vl.addWidget(val_lbl)

        glass = _glass_bg(0.85)
        rim   = _glass_border()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {glass};
                border: 1px solid {rim};
                border-radius: 12px;
            }}
        """)


class _ViajeHero(QWidget):
    """Bloque central con el número de carta porte en grande."""

    def __init__(self, numero_viaje: str, procesado: bool, parent=None):
        super().__init__(parent)
        c = theme.colors()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(6)
        vl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        accent = c['success'] if procesado else c['error']

        lbl_icon = QLabel("🚚")
        lbl_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_icon.setFont(QFont("Segoe UI Emoji", 26))
        lbl_icon.setStyleSheet("background: transparent; border: none;")
        vl.addWidget(lbl_icon)

        lbl_num = QLabel(numero_viaje)
        lbl_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_num.setFont(QFont("SF Pro Display", 22, QFont.Weight.Bold))
        lbl_num.setStyleSheet(
            f"color: {accent}; background: transparent; border: none; letter-spacing: -0.5px;"
        )
        vl.addWidget(lbl_num)

        sep = QFrame()
        sep.setFixedHeight(2)
        sep.setStyleSheet(
            f"background-color: {accent}; border: none; border-radius: 1px;"
        )
        vl.addWidget(sep)

        lbl_sub = QLabel("CARTA PORTE / Nº VIAJE")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sub.setStyleSheet(
            f"color: {c['text3']}; font-size: 7pt; font-weight: 700;"
            f" letter-spacing: 1.2px; background: transparent; border: none;"
        )
        vl.addWidget(lbl_sub)

        glass = _glass_bg(0.78)
        rim   = _glass_border()
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {glass};
                border: 1px solid {rim};
                border-top: 4px solid {accent};
                border-radius: 16px;
            }}
        """)


class _ObsCard(QFrame):
    """Tarjeta glass para el texto de observaciones."""

    def __init__(self, texto: str, parent=None):
        super().__init__(parent)
        c = theme.colors()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(14, 10, 14, 10)
        vl.setSpacing(5)

        lbl_top = QLabel("📝  Observaciones")
        lbl_top.setStyleSheet(
            f"color: {c['text3']}; font-size: 7.5pt; font-weight: 600;"
            f" letter-spacing: 0.3px; background: transparent; border: none;"
        )
        vl.addWidget(lbl_top)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {c['border']}; border: none;")
        vl.addWidget(sep)

        # Truncar si es muy largo
        preview = texto if len(texto) <= 120 else texto[:117] + "…"
        lbl_obs = QLabel(preview)
        lbl_obs.setStyleSheet(
            f"color: {c['text2']}; font-size: 9.5pt; font-style: italic;"
            f" background: transparent; border: none;"
        )
        lbl_obs.setWordWrap(True)
        vl.addWidget(lbl_obs)

        glass = _glass_bg(0.85)
        rim   = _glass_border()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {glass};
                border: 1px solid {rim};
                border-radius: 12px;
            }}
        """)


# ── Ventana principal ─────────────────────────────────────────────────────────

class ResumenViajeWindow(QDialog):
    """Informe final del proceso de Desviación de Viajes — diseño glass macOS Sonoma."""

    def __init__(self, numero_viaje: str, tipo_incidencia: str, observaciones: str,
                 ciudad: str, procesado: bool, cancelado: bool = False,
                 tiempo_total: str = "", usuario: str = "",
                 paginas_procesadas: int = 0, total_paginas: int = 0,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚚 INFORME — DESVIACIÓN DE VIAJES")
        self.setMinimumSize(560, 480)
        self.resize(660, 540)
        self.setSizeGripEnabled(True)
        self.setModal(True)

        self._build_ui(numero_viaje, tipo_incidencia, observaciones,
                       ciudad, procesado, cancelado, tiempo_total, usuario,
                       paginas_procesadas, total_paginas)
        self._apply_styles()
        from utils import theme
        theme.signals.changed.connect(self._apply_styles)

    def _build_ui(self, numero_viaje, tipo_incidencia, observaciones,
                  ciudad, procesado, cancelado, tiempo_total, usuario,
                  paginas_procesadas=0, total_paginas=0):
        c = theme.colors()

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header stripe ───────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("rviaje_header")
        header.setFixedHeight(68)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(24, 0, 24, 0)

        left_h = QVBoxLayout()
        left_h.setSpacing(2)
        lbl_app = QLabel("🔔  ALERTRAN")
        lbl_app.setObjectName("rvj_app")
        lbl_report = QLabel("INFORME — DESVIACIÓN DE VIAJES")
        lbl_report.setObjectName("rvj_title")
        left_h.addWidget(lbl_app)
        left_h.addWidget(lbl_report)
        h_lay.addLayout(left_h)
        h_lay.addStretch()

        right_h = QVBoxLayout()
        right_h.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right_h.setSpacing(3)
        fecha = datetime.now().strftime("%d/%m/%Y  %H:%M")
        lbl_fecha = QLabel(f"📅  {fecha}")
        lbl_fecha.setObjectName("rvj_meta")
        lbl_fecha.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_nav = QLabel("🚚  Desviación de Viajes")
        lbl_nav.setObjectName("rvj_meta")
        lbl_nav.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_h.addWidget(lbl_fecha)
        right_h.addWidget(lbl_nav)
        h_lay.addLayout(right_h)
        root.addWidget(header)

        # ── Body ────────────────────────────────────────────────────────
        body_w = QWidget()
        body_w.setObjectName("rvj_body")
        body = QVBoxLayout(body_w)
        body.setContentsMargins(24, 18, 24, 18)
        body.setSpacing(14)

        # ── Banner de resultado ─────────────────────────────────────────
        if cancelado:
            banner_color = c['text3']
            banner_bg    = c['surface2']
            banner_sym   = "○"
            banner_text  = "PROCESO CANCELADO POR EL USUARIO"
        elif procesado:
            banner_color = c['success']
            banner_bg    = c['success_bg']
            banner_sym   = "✓"
            banner_text  = "VIAJE PROCESADO CORRECTAMENTE"
        else:
            banner_color = c['error']
            banner_bg    = c['error_bg']
            banner_sym   = "✕"
            banner_text  = "EL VIAJE NO PUDO PROCESARSE"

        banner = QFrame()
        banner.setFixedHeight(54)
        banner.setStyleSheet(
            f"QFrame {{ background-color: {banner_bg};"
            f" border: 1.5px solid {banner_color};"
            f" border-left: 6px solid {banner_color};"
            f" border-radius: 12px; }}"
        )
        ban_lay = QHBoxLayout(banner)
        ban_lay.setContentsMargins(14, 0, 14, 0)
        ban_lay.setSpacing(12)

        circle = QLabel(banner_sym)
        circle.setFixedSize(32, 32)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setFont(QFont("Arial", 13, QFont.Weight.Bold))
        circle.setStyleSheet(
            f"background-color: {banner_color}; color: white;"
            f" border-radius: 16px; border: none;"
        )
        ban_lay.addWidget(circle)

        ban_msg = QLabel(banner_text)
        ban_msg.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        ban_msg.setStyleSheet(
            f"color: {banner_color}; background: transparent; border: none;"
        )
        ban_lay.addWidget(ban_msg)
        ban_lay.addStretch()
        body.addWidget(banner)

        # ── Hero — número de viaje ──────────────────────────────────────
        hero = _ViajeHero(numero_viaje or "—", procesado and not cancelado)
        body.addWidget(hero)

        # ── Tarjetas de detalle ─────────────────────────────────────────
        cards_row = QWidget()
        cards_row.setObjectName("rvj_cards")
        cr_lay = QHBoxLayout(cards_row)
        cr_lay.setContentsMargins(0, 0, 0, 0)
        cr_lay.setSpacing(10)

        if usuario:
            cr_lay.addWidget(_InfoCard("👤", "Usuario", usuario, c['accent']))
        cr_lay.addWidget(_InfoCard("📌", "Tipo incidencia", tipo_incidencia, c['purple']))
        cr_lay.addWidget(_InfoCard("📍", "Regional", ciudad[:20] if ciudad else "—", c['text']))
        if total_paginas > 0:
            pag_color = c['success'] if paginas_procesadas == total_paginas else c['warning']
            cr_lay.addWidget(_InfoCard(
                "📄", "Páginas",
                f"{paginas_procesadas} / {total_paginas}",
                pag_color
            ))
        cr_lay.addStretch()
        body.addWidget(cards_row)

        # ── Tiempo total — franja destacada ─────────────────────────────
        if tiempo_total:
            tiempo_frame = QFrame()
            tiempo_frame.setFixedHeight(44)
            tiempo_frame.setStyleSheet(
                f"QFrame {{ background-color: {c['surface2']};"
                f" border: 1.5px solid {c['border']};"
                f" border-left: 5px solid {c['purple']};"
                f" border-radius: 10px; }}"
            )
            t_lay = QHBoxLayout(tiempo_frame)
            t_lay.setContentsMargins(14, 0, 14, 0)
            t_lay.setSpacing(10)

            lbl_clock = QLabel("⏱")
            lbl_clock.setFont(QFont("Segoe UI Emoji", 14))
            lbl_clock.setStyleSheet("background: transparent; border: none;")
            t_lay.addWidget(lbl_clock)

            lbl_t_titulo = QLabel("TIEMPO TOTAL DEL PROCESO")
            lbl_t_titulo.setStyleSheet(
                f"color: {c['text3']}; font-size: 8pt; font-weight: 700;"
                f" letter-spacing: 0.6px; background: transparent; border: none;"
            )
            t_lay.addWidget(lbl_t_titulo)
            t_lay.addStretch()

            lbl_t_val = QLabel(tiempo_total)
            lbl_t_val.setFont(QFont("SF Pro Display", 14, QFont.Weight.Bold))
            lbl_t_val.setStyleSheet(
                f"color: {c['purple']}; background: transparent; border: none;"
            )
            t_lay.addWidget(lbl_t_val)
            body.addWidget(tiempo_frame)

        # ── Observaciones ───────────────────────────────────────────────
        if observaciones:
            body.addWidget(_ObsCard(observaciones))

        root.addWidget(body_w, stretch=1)

        # ── Footer / botón ──────────────────────────────────────────────
        footer = QFrame()
        footer.setObjectName("rvj_footer")
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(24, 14, 24, 14)

        btn_cerrar = QPushButton("✔  ACEPTAR")
        btn_cerrar.setObjectName("rvj_btn_cerrar")
        btn_cerrar.setFixedHeight(44)
        btn_cerrar.setMinimumWidth(180)
        btn_cerrar.clicked.connect(self.accept)
        f_lay.addStretch()
        f_lay.addWidget(btn_cerrar)
        f_lay.addStretch()
        root.addWidget(footer)

    def _apply_styles(self):
        c = theme.colors()
        self.setStyleSheet(theme.base_stylesheet() + f"""
            QDialog {{
                background-color: {c['bg']};
            }}

            /* ── Header stripe ── */
            QFrame#rviaje_header {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['accent']},
                    stop:1 {c['purple']}
                );
                border-bottom: 2px solid {c['accent_press']};
            }}
            QLabel#rvj_app {{
                color: white;
                font-size: 12pt;
                font-weight: 800;
                letter-spacing: -0.3px;
                background: transparent;
            }}
            QLabel#rvj_title {{
                color: rgba(255,255,255,0.78);
                font-size: 7.5pt;
                font-weight: 600;
                letter-spacing: 0.9px;
                background: transparent;
            }}
            QLabel#rvj_meta {{
                color: rgba(255,255,255,0.72);
                font-size: 8.5pt;
                font-weight: 500;
                background: transparent;
            }}

            /* ── Body ── */
            QWidget#rvj_body {{
                background-color: {c['bg']};
            }}
            QWidget#rvj_cards {{
                background-color: transparent;
            }}

            /* ── Footer ── */
            QFrame#rvj_footer {{
                background-color: {c['action_bg']};
                border-top: 1px solid {c['border']};
            }}

            /* ── Botón aceptar ── */
            QPushButton#rvj_btn_cerrar {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['accent']},
                    stop:1 {c['purple']}
                );
                color: white;
                font-weight: 700;
                font-size: 10.5pt;
                border-radius: 13px;
                border: none;
                letter-spacing: 0.3px;
            }}
            QPushButton#rvj_btn_cerrar:hover {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['accent_hover']},
                    stop:1 {c['purple']}
                );
            }}
            QPushButton#rvj_btn_cerrar:pressed {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['accent_press']},
                    stop:1 {c['purple']}
                );
            }}
        """)
