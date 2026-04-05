# ui/resumen_window.py
"""
Ventana de resumen final del proceso — Informe ejecutivo macOS Sonoma style
Glassmorphism cards simulado con rgba sobre fondo gris del sistema
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QWidget, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QFont
from datetime import datetime
from utils import theme
from utils.settings_manager import SettingsManager


def _glass_bg(alpha: float = 0.82) -> str:
    """Devuelve el color de fondo glass según el tema."""
    if theme.is_dark():
        a = int(alpha * 255)
        return f"rgba(44, 44, 46, {alpha})"
    else:
        a = int(alpha * 255)
        return f"rgba(255, 255, 255, {alpha})"


def _glass_border() -> str:
    """Borde glass según el tema."""
    if theme.is_dark():
        return "rgba(80, 80, 82, 0.7)"
    else:
        return "rgba(255, 255, 255, 0.95)"


class _StatCard(QWidget):
    """Tarjeta de estadística glass con número grande y etiqueta."""

    def __init__(self, titulo: str, valor: int, accent: str, parent=None):
        super().__init__(parent)
        c = theme.colors()
        dark = theme.is_dark()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(112)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 16, 14, 14)
        root.setSpacing(8)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._num_label = QLabel(str(valor))
        self._num_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._num_label.setFont(QFont("SF Pro Display", 30, QFont.Weight.Bold))
        self._num_label.setStyleSheet(
            f"color: {accent}; background: transparent; border: none;"
        )
        root.addWidget(self._num_label)

        # Separador de color bajo el número
        sep = QFrame()
        sep.setFixedHeight(2)
        sep.setStyleSheet(
            f"background-color: {accent}; border: none; border-radius: 1px;"
        )
        root.addWidget(sep)

        lbl = QLabel(titulo)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(
            f"color: {c['text3']}; font-size: 7.5pt; font-weight: 700;"
            f" letter-spacing: 0.8px; background: transparent; border: none;"
        )
        root.addWidget(lbl)

        # Glass card style
        glass = _glass_bg(0.78)
        rim   = _glass_border()
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {glass};
                border: 1px solid {rim};
                border-top: 4px solid {accent};
                border-radius: 14px;
            }}
        """)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Escala la fuente del número entre 16pt y 30pt según el ancho de la tarjeta
        w = max(event.size().width(), 1)
        pt = max(16, min(30, int(w * 30 / 140)))
        self._num_label.setFont(QFont("SF Pro Display", pt, QFont.Weight.Bold))


class _CardsContainer(QWidget):
    """Contenedor de las 6 tarjetas: 1 fila cuando hay espacio, 2×3 si el ancho es angosto."""

    _THRESHOLD = 660  # px — por debajo de esto usa 2 filas

    def __init__(self, cards_data: list, parent=None):
        super().__init__(parent)
        self.setObjectName("cards_bg")
        self._cards = [_StatCard(t, v, c) for t, v, c in cards_data]
        self._current_cols = 6
        self._grid = QGridLayout(self)
        self._grid.setSpacing(10)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._place(6)

    def _place(self, cols: int):
        for card in self._cards:
            self._grid.removeWidget(card)
        for idx, card in enumerate(self._cards):
            self._grid.addWidget(card, idx // cols, idx % cols)
        self._current_cols = cols

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cols = 3 if event.size().width() < self._THRESHOLD else 6
        if cols != self._current_cols:
            self._place(cols)


class _DetailCard(QFrame):
    """Tarjeta glass para el bloque de detalle."""

    def __init__(self, icon: str, label: str, value: str, color: str, parent=None):
        super().__init__(parent)
        c = theme.colors()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(140)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 12, 16, 12)
        vl.setSpacing(6)

        # Label superior
        lbl_top = QLabel(f"{icon}  {label}")
        lbl_top.setStyleSheet(
            f"color: {c['text3']}; font-size: 8pt; font-weight: 600;"
            f" letter-spacing: 0.3px; background: transparent; border: none;"
        )
        vl.addWidget(lbl_top)

        # Separador
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {c['border']}; border: none;")
        vl.addWidget(sep)

        # Valor
        val_lbl = QLabel(str(value))
        val_lbl.setFont(QFont("SF Pro Display", 12, QFont.Weight.Bold))
        val_lbl.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )
        vl.addWidget(val_lbl)

        # Glass card style
        glass = _glass_bg(0.85)
        rim   = _glass_border()
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {glass};
                border: 1px solid {rim};
                border-radius: 12px;
            }}
        """)


class ResumenWindow(QDialog):
    """Informe final del proceso — diseño glass macOS Sonoma."""

    def __init__(self, total_guias, desviadas, entregadas, errores,
                 advertencias, duplicadas=0, tiempo_total="",
                 usuario="", tipo_proceso="Desviaciones",
                 desviacion="", regional="", ampliacion="",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 INFORME FINAL DEL PROCESO")
        self.setMinimumSize(680, 530)
        self.resize(800, 570)
        self.setSizeGripEnabled(True)
        self.setModal(True)
        _geom = SettingsManager.get_instance().get("resumen_window_geometry", None)
        if _geom:
            self.restoreGeometry(QByteArray.fromBase64(_geom.encode()))

        self._build_ui(total_guias, desviadas, entregadas, errores,
                       advertencias, duplicadas, tiempo_total, usuario, tipo_proceso,
                       desviacion, regional, ampliacion)
        self._apply_styles()
        from utils import theme
        theme.signals.changed.connect(self._apply_styles)

    def _build_ui(self, total, desviadas, entregadas, errores,
                  advertencias, duplicadas, tiempo_total, usuario, tipo_proceso,
                  desviacion, regional, ampliacion):
        c = theme.colors()

        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header stripe ──────────────────────────────────────────────────
        header = QFrame()
        header.setObjectName("report_header")
        header.setFixedHeight(68)
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(24, 0, 24, 0)

        left_h = QVBoxLayout()
        left_h.setSpacing(2)
        lbl_app = QLabel("🔔  ALERTRAN")
        lbl_app.setObjectName("rpt_app")
        lbl_report = QLabel("INFORME FINAL DEL PROCESO")
        lbl_report.setObjectName("rpt_title")
        left_h.addWidget(lbl_app)
        left_h.addWidget(lbl_report)
        h_lay.addLayout(left_h)
        h_lay.addStretch()

        right_h = QVBoxLayout()
        right_h.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        right_h.setSpacing(3)
        fecha = datetime.now().strftime("%d/%m/%Y  %H:%M")
        lbl_fecha = QLabel(f"📅  {fecha}")
        lbl_fecha.setObjectName("rpt_meta")
        lbl_fecha.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_tipo = QLabel(f"📦  {tipo_proceso}")
        lbl_tipo.setObjectName("rpt_meta")
        lbl_tipo.setAlignment(Qt.AlignmentFlag.AlignRight)
        right_h.addWidget(lbl_fecha)
        right_h.addWidget(lbl_tipo)
        h_lay.addLayout(right_h)
        root.addWidget(header)

        # ── Body ───────────────────────────────────────────────────────────
        body_w = QWidget()
        body_w.setObjectName("report_body")
        body = QVBoxLayout(body_w)
        body.setContentsMargins(24, 20, 24, 20)
        body.setSpacing(16)

        # ── Result banner ─────────────────────────────────────────────────
        success_rate = round((desviadas + entregadas) / total * 100, 1) if total > 0 else 0.0
        if errores == 0:
            banner_color = c['success']
            banner_bg    = c['success_bg']
            banner_sym   = "✓"
            banner_text  = "PROCESO COMPLETADO SIN ERRORES"
        elif errores < total * 0.1:
            banner_color = c['warning']
            banner_bg    = c['warning_bg']
            banner_sym   = "!"
            banner_text  = "PROCESO COMPLETADO CON ADVERTENCIAS"
        else:
            banner_color = c['error']
            banner_bg    = c['error_bg']
            banner_sym   = "✕"
            banner_text  = "PROCESO COMPLETADO CON ERRORES"

        banner = QFrame()
        banner.setFixedHeight(56)
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
        circle.setFixedSize(34, 34)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        circle.setStyleSheet(
            f"background-color: {banner_color}; color: white;"
            f" border-radius: 17px; border: none;"
        )
        ban_lay.addWidget(circle)

        ban_msg = QLabel(banner_text)
        ban_msg.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        ban_msg.setStyleSheet(
            f"color: {banner_color}; background: transparent; border: none;"
        )
        ban_lay.addWidget(ban_msg)
        ban_lay.addStretch()

        pill = QLabel(f"  {success_rate}% éxito  ")
        pill.setFixedHeight(30)
        pill.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        pill.setStyleSheet(
            f"background-color: {banner_color}; color: white;"
            f" border-radius: 15px; border: none;"
        )
        ban_lay.addWidget(pill)
        body.addWidget(banner)

        # ── Tiempo total — franja destacada ───────────────────────────────
        if tiempo_total:
            tiempo_frame = QFrame()
            tiempo_frame.setFixedHeight(44)
            tiempo_frame.setStyleSheet(
                f"QFrame {{ background-color: {c['surface2']};"
                f" border: 1.5px solid {c['border']};"
                f" border-left: 5px solid {c['accent']};"
                f" border-radius: 10px; }}"
            )
            t_lay = QHBoxLayout(tiempo_frame)
            t_lay.setContentsMargins(14, 0, 14, 0)
            t_lay.setSpacing(10)

            lbl_clock = QLabel("⏱")
            lbl_clock.setFont(QFont("Segoe UI Emoji", 14))
            lbl_clock.setStyleSheet("background: transparent; border: none;")
            t_lay.addWidget(lbl_clock)

            lbl_tiempo_titulo = QLabel("TIEMPO TOTAL DEL PROCESO")
            lbl_tiempo_titulo.setStyleSheet(
                f"color: {c['text3']}; font-size: 8pt; font-weight: 700;"
                f" letter-spacing: 0.6px; background: transparent; border: none;"
            )
            t_lay.addWidget(lbl_tiempo_titulo)
            t_lay.addStretch()

            lbl_tiempo_val = QLabel(tiempo_total)
            lbl_tiempo_val.setFont(QFont("SF Pro Display", 14, QFont.Weight.Bold))
            lbl_tiempo_val.setStyleSheet(
                f"color: {c['accent']}; background: transparent; border: none;"
            )
            t_lay.addWidget(lbl_tiempo_val)
            body.addWidget(tiempo_frame)

        # ── Info proceso (desviación / regional / ampliación) ─────────────
        if desviacion or regional or ampliacion:
            info_frame = QFrame()
            info_frame.setObjectName("info_proceso_frame")
            info_frame.setMinimumHeight(62)
            info_frame.setMaximumHeight(62)
            info_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            info_frame.setStyleSheet(
                f"QFrame#info_proceso_frame {{"
                f"  background-color: {c['surface2']};"
                f"  border: 1.5px solid {c['border']};"
                f"  border-left: 5px solid {c['purple']};"
                f"  border-radius: 10px;"
                f"}}"
            )
            i_lay = QHBoxLayout(info_frame)
            i_lay.setContentsMargins(16, 0, 16, 0)
            i_lay.setSpacing(0)

            def _info_item(icon: str, lbl: str, val: str):
                """Bloque vertical: etiqueta pequeña arriba + valor bold abajo."""
                w = QWidget()
                w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                w.setStyleSheet(
                    "QWidget { background: transparent; border: none; }"
                    "QLabel  { background: transparent; border: none; }"
                )
                vl = QVBoxLayout(w)
                vl.setContentsMargins(8, 8, 8, 8)
                vl.setSpacing(3)

                top = QLabel(f"{icon}  {lbl}")
                top.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
                top.setStyleSheet(
                    f"color: {c['text3']};"
                    f" font-size: 7pt; font-weight: 700;"
                    f" letter-spacing: 0.5px;"
                    f" background: transparent; border: none;"
                )
                vl.addWidget(top)

                bot = QLabel(val or "—")
                bot.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
                bot.setStyleSheet(
                    f"color: {c['text']};"
                    f" font-size: 10pt; font-weight: 700;"
                    f" background: transparent; border: none;"
                )
                bot.setWordWrap(False)
                vl.addWidget(bot)
                return w

            def _vsep():
                sep = QFrame()
                sep.setFixedWidth(1)
                sep.setMinimumHeight(36)
                sep.setMaximumHeight(36)
                sep.setStyleSheet(
                    f"QFrame {{ background-color: {c['border']}; border: none; }}"
                )
                return sep

            items = []
            if desviacion:
                items.append((_info_item("📌", "DESVIACIÓN", desviacion), 1))
            if regional:
                items.append((_info_item("📍", "REGIONAL", regional), 2))
            if ampliacion:
                amp_val = ampliacion[:60] + "…" if len(ampliacion) > 60 else ampliacion
                items.append((_info_item("📝", "AMPLIACIÓN", amp_val), 4))

            for idx, (widget, stretch) in enumerate(items):
                if idx > 0:
                    sep_w = QWidget()
                    sep_w.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
                    sep_w.setStyleSheet("background: transparent; border: none;")
                    sep_w.setFixedWidth(1)
                    sep_lay = QVBoxLayout(sep_w)
                    sep_lay.setContentsMargins(0, 12, 0, 12)
                    sep_lay.setSpacing(0)
                    sep_lay.addWidget(_vsep())
                    i_lay.addWidget(sep_w)
                i_lay.addWidget(widget, stretch=stretch)

            body.addWidget(info_frame)

        # ── Stat glass cards ──────────────────────────────────────────────
        cards_data = [
            ("TOTAL GUÍAS",  total,        c['accent']),
            ("DESVIACIONES", desviadas,    c['success']),
            ("ENTREGADAS",   entregadas,   c['warning']),
            ("ERRORES",      errores,      c['error']),
            ("ADVERTENCIAS", advertencias, c['purple']),
            ("REPETIDAS",    duplicadas,   "#8e8e93"),
        ]
        body.addWidget(_CardsContainer(cards_data))

        # ── Detail glass cards ────────────────────────────────────────────
        detail_container = QWidget()
        detail_container.setObjectName("detail_container")
        d_lay = QHBoxLayout(detail_container)
        d_lay.setContentsMargins(0, 0, 0, 0)
        d_lay.setSpacing(12)

        if usuario:
            d_lay.addWidget(_DetailCard("👤", "Usuario", usuario, c['accent']))
        d_lay.addWidget(
            _DetailCard(
                "📋", "Procesadas",
                f"{desviadas}/{total}",
                c['success'] if errores == 0 else c['warning']
            )
        )
        # Tasa de éxito card
        d_lay.addWidget(
            _DetailCard("📈", "Tasa de éxito", f"{success_rate}%",
                        c['success'] if success_rate >= 90 else c['warning'])
        )
        d_lay.addStretch()
        body.addWidget(detail_container)

        root.addWidget(body_w, stretch=1)

        # ── Footer / button ────────────────────────────────────────────────
        footer = QFrame()
        footer.setObjectName("report_footer")
        f_lay = QHBoxLayout(footer)
        f_lay.setContentsMargins(24, 14, 24, 14)

        btn_cerrar = QPushButton("✔  ACEPTAR")
        btn_cerrar.setObjectName("btn_cerrar")
        btn_cerrar.setFixedHeight(46)
        btn_cerrar.setMinimumWidth(200)
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

            /* ── Header stripe — blue gradient ── */
            QFrame#report_header {{
                background-color: {c['accent']};
                border-bottom: 2px solid {c['accent_press']};
            }}
            QLabel#rpt_app {{
                color: white;
                font-size: 12pt;
                font-weight: 800;
                letter-spacing: -0.3px;
                background: transparent;
            }}
            QLabel#rpt_title {{
                color: rgba(255,255,255,0.76);
                font-size: 8pt;
                font-weight: 600;
                letter-spacing: 0.8px;
                background: transparent;
            }}
            QLabel#rpt_meta {{
                color: rgba(255,255,255,0.72);
                font-size: 8.5pt;
                font-weight: 500;
                background: transparent;
            }}

            /* ── Body area ── */
            QWidget#report_body {{
                background-color: {c['bg']};
            }}

            /* ── Cards background area ── */
            QWidget#cards_bg {{
                background-color: transparent;
            }}

            /* ── Detail container ── */
            QWidget#detail_container {{
                background-color: transparent;
            }}

            /* ── Footer ── */
            QFrame#report_footer {{
                background-color: {c['action_bg']};
                border-top: 1px solid {c['border']};
            }}

            /* ── Accept button ── */
            QPushButton#btn_cerrar {{
                background-color: {c['accent']};
                color: white;
                font-weight: 700;
                font-size: 11pt;
                border-radius: 14px;
                border: none;
                letter-spacing: 0.3px;
            }}
            QPushButton#btn_cerrar:hover {{
                background-color: {c['accent_hover']};
            }}
            QPushButton#btn_cerrar:pressed {{
                background-color: {c['accent_press']};
            }}
        """)

    def closeEvent(self, event):
        sm = SettingsManager.get_instance()
        sm.set("resumen_window_geometry", self.saveGeometry().toBase64().data().decode())
        sm.save()
        super().closeEvent(event)
