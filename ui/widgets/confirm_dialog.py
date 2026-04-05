# ui/widgets/confirm_dialog.py
"""
Diálogo de confirmación antes de iniciar un proceso
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QSizePolicy, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from utils import theme


class ConfirmDialog(QDialog):
    """
    Diálogo responsive de confirmación de proceso.

    Parámetros
    ----------
    titulo : str
        Tipo de proceso, e.g. "DESVIACIONES"
    emoji : str
        Emoji representativo, e.g. "📦"
    filas : list[tuple[str, str, str | None]]
        Cada tupla: (etiqueta, valor, color_badge_o_None)
    carpeta : str
        Ruta de la carpeta de descargas
    advertencia : dict | None
        {"titulo": str, "texto": str, "tipo": "warning"|"info"}
    header_gradient : tuple[str, str] | None
        Par de colores CSS para gradiente horizontal del header, e.g. ("#007aff", "#bf5af2").
        Si es None se usa el color de fondo estándar del tema.
    """

    def __init__(self, titulo, emoji, filas, carpeta,
                 advertencia=None, header_gradient=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔔 CONFIRMAR PROCESO")
        self.setModal(True)
        self.setMinimumSize(500, 360)
        self.setSizeGripEnabled(True)
        self.resultado = False
        self._header_gradient = header_gradient

        self._build_ui(titulo, emoji, filas, carpeta, advertencia)
        self._apply_styles()
        from utils import theme
        theme.signals.changed.connect(self._apply_styles)

    # ── Construction ─────────────────────────────────────────────────────────

    def _build_ui(self, titulo, emoji, filas, carpeta, advertencia):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Header
        root.addWidget(self._make_header(emoji, titulo))

        # Body (no scroll)
        body_widget = QWidget()
        body = QVBoxLayout(body_widget)
        body.setSpacing(12)
        body.setContentsMargins(24, 20, 24, 20)

        body.addWidget(self._make_table(filas))
        body.addWidget(self._make_carpeta_label(carpeta))

        pregunta = QLabel("¿Desea continuar con el proceso?")
        pregunta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pregunta.setObjectName("lbl_pregunta")
        body.addWidget(pregunta)

        if advertencia:
            body.addWidget(self._make_advertencia(advertencia))

        body.addStretch()
        root.addWidget(body_widget, stretch=1)

        # Buttons
        root.addWidget(self._make_buttons())

    def _make_header(self, emoji, titulo):
        frame = QFrame()
        frame.setObjectName("header_frame")
        frame.setFixedHeight(58)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 16, 20, 16)

        lbl = QLabel(f"{emoji}  RESUMEN DE OPERACIÓN — {titulo}")
        obj = "header_label_gradient" if self._header_gradient else "header_label"
        lbl.setObjectName(obj)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        return frame

    def _make_table(self, filas):
        frame = QFrame()
        frame.setObjectName("table_frame")
        grid = QGridLayout(frame)
        grid.setSpacing(2)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 4)
        grid.setColumnStretch(1, 6)

        for i, (etiqueta, valor, badge_color) in enumerate(filas):
            lbl_key = QLabel(etiqueta)
            lbl_key.setObjectName("cell_key")
            lbl_key.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            if badge_color:
                lbl_val = QLabel(valor)
                lbl_val.setObjectName("cell_badge")
                lbl_val.setStyleSheet(
                    f"background-color: {badge_color}; color: white;"
                    " border-radius: 10px; padding: 3px 14px; font-weight: bold;"
                )
                lbl_val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            else:
                lbl_val = QLabel(valor)
                lbl_val.setObjectName("cell_val")
                lbl_val.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                lbl_val.setWordWrap(True)

            grid.addWidget(lbl_key, i, 0)
            grid.addWidget(lbl_val, i, 1)

        return frame

    def _make_carpeta_label(self, carpeta):
        frame = QFrame()
        frame.setObjectName("carpeta_frame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 8)

        lbl = QLabel(f"📂  {carpeta}")
        lbl.setObjectName("lbl_carpeta")
        lbl.setWordWrap(True)
        layout.addWidget(lbl)
        return frame

    def _make_advertencia(self, adv):
        frame = QFrame()
        obj = "adv_warning" if adv.get("tipo") == "warning" else "adv_info"
        frame.setObjectName(obj)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        titulo_lbl = QLabel(adv["titulo"])
        titulo_lbl.setObjectName("adv_titulo")
        layout.addWidget(titulo_lbl)

        texto_lbl = QLabel(adv["texto"])
        texto_lbl.setObjectName("adv_texto")
        texto_lbl.setWordWrap(True)
        layout.addWidget(texto_lbl)
        return frame

    def _make_buttons(self):
        frame = QFrame()
        frame.setObjectName("btn_frame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(14)

        btn_si = QPushButton("✔  SÍ, INICIAR")
        btn_si.setObjectName("btn_si")
        btn_si.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_si.clicked.connect(self._aceptar)

        btn_no = QPushButton("✖  NO, CANCELAR")
        btn_no.setObjectName("btn_no")
        btn_no.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn_no.clicked.connect(self.reject)

        layout.addWidget(btn_si)
        layout.addWidget(btn_no)
        return frame

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _aceptar(self):
        self.resultado = True
        self.accept()

    # ── Styles ────────────────────────────────────────────────────────────────

    def _apply_styles(self):
        c = theme.colors()

        if self._header_gradient:
            c1, c2 = self._header_gradient
            header_bg_css = (
                f"background: qlineargradient("
                f"x1:0, y1:0, x2:1, y2:0, stop:0 {c1}, stop:1 {c2});"
                f"border-bottom: 2px solid {c1};"
            )
            header_label_color = "white"
        else:
            header_bg_css = (
                f"background-color: {c['header_bg']};"
                f"border-bottom: 1px solid {c['border']};"
            )
            header_label_color = c['text']

        self.setStyleSheet(theme.base_stylesheet() + f"""
            QDialog {{ background-color: {c['bg']}; }}

            /* ── Header ── */
            QFrame#header_frame {{
                {header_bg_css}
            }}
            QLabel#header_label {{
                color: {header_label_color};
                font-size: 11pt;
                font-weight: 700;
                letter-spacing: -0.2px;
            }}
            QLabel#header_label_gradient {{
                color: white;
                font-size: 11pt;
                font-weight: 700;
                letter-spacing: -0.2px;
            }}

            /* ── Data table ── */
            QFrame#table_frame {{
                background-color: {c['surface']};
                border: 1.5px solid {c['border']};
                border-radius: 12px;
            }}
            QLabel#cell_key {{
                background-color: {c['surface2']};
                color: {c['text3']};
                font-size: 9.5pt;
                font-weight: 700;
                padding: 7px 14px;
                border-bottom: 1px solid {c['border']};
                letter-spacing: 0.2px;
            }}
            QLabel#cell_val {{
                background-color: {c['surface']};
                color: {c['text']};
                font-size: 10pt;
                padding: 7px 14px;
                border-bottom: 1px solid {c['border']};
                font-weight: 500;
            }}
            QLabel#cell_badge {{
                font-size: 10pt;
                padding: 7px 14px;
                border-bottom: 1px solid {c['border']};
                background-color: transparent;
            }}

            /* ── Path display ── */
            QFrame#carpeta_frame {{
                background-color: {c['surface2']};
                border: 1.5px solid {c['border']};
                border-radius: 10px;
            }}
            QLabel#lbl_carpeta {{
                color: {c['text3']};
                font-size: 9pt;
                font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
            }}

            /* ── Question ── */
            QLabel#lbl_pregunta {{
                color: {c['text']};
                font-size: 11pt;
                font-weight: 600;
                padding: 4px 0;
            }}

            /* ── Alert warning ── */
            QFrame#adv_warning {{
                background-color: {c['error_bg']};
                border: 1.5px solid {c['error']};
                border-left: 5px solid {c['error']};
                border-radius: 10px;
            }}
            QFrame#adv_warning QLabel#adv_titulo {{
                color: {c['error']};
                font-weight: 700;
                font-size: 10pt;
            }}
            QFrame#adv_warning QLabel#adv_texto {{
                color: {c['error']};
                font-size: 9.5pt;
            }}

            /* ── Alert info ── */
            QFrame#adv_info {{
                background-color: {c['accent_light']};
                border: 1.5px solid {c['accent']};
                border-left: 5px solid {c['accent']};
                border-radius: 10px;
            }}
            QFrame#adv_info QLabel#adv_titulo {{
                color: {c['accent']};
                font-weight: 700;
                font-size: 10pt;
            }}
            QFrame#adv_info QLabel#adv_texto {{
                color: {c['accent']};
                font-size: 9.5pt;
            }}

            /* ── Buttons bar ── */
            QFrame#btn_frame {{
                background-color: {c['action_bg']};
                border-top: 1px solid {c['border']};
            }}
            QPushButton#btn_si {{
                background-color: {c['success']};
                color: white;
                border: none;
                border-radius: 12px;
                font-size: 11pt;
                font-weight: 700;
                min-height: 44px;
                padding: 8px 20px;
            }}
            QPushButton#btn_si:hover {{
                border: 2px solid {c['success']};
                background-color: {c['success']};
            }}
            QPushButton#btn_si:pressed {{
                background-color: {c['success_bg']};
                color: {c['success']};
                border: 2px solid {c['success']};
            }}
            QPushButton#btn_no {{
                background-color: transparent;
                color: {c['error']};
                border: 2px solid {c['error']};
                border-radius: 12px;
                font-size: 11pt;
                font-weight: 700;
                min-height: 44px;
                padding: 8px 20px;
            }}
            QPushButton#btn_no:hover {{
                background-color: {c['error']};
                color: white;
            }}
            QPushButton#btn_no:pressed {{
                background-color: {c['error_bg']};
                color: {c['error']};
            }}
        """)
