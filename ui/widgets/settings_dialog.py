# ui/widgets/settings_dialog.py
"""
Diálogo de configuración avanzada de tiempos y parámetros de proceso.
Los cambios se persisten en ~/.alertran/settings.json y se leen al
siguiente arranque de la aplicación (config/settings.py los carga en import).
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QSpinBox, QScrollArea, QWidget, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from utils.settings_manager import SettingsManager, _DEFAULTS
from utils import theme


# Definición de campos: (clave, etiqueta, mínimo, máximo, step)
_CAMPOS = [
    ("TIEMPO_ESPERA_RECUPERACION",   "⏳ Espera recuperación",       500,  30_000, 500),
    ("TIEMPO_ESPERA_NAVEGACION",     "🧭 Espera navegación",         500,  20_000, 500),
    ("TIEMPO_ESPERA_CLICK",          "🖱️  Espera click",             200,  10_000, 100),
    ("TIEMPO_ESPERA_CARGA",          "📄 Espera carga de página",  1_000,  60_000, 500),
    ("TIEMPO_ESPERA_ENTRE_GUIAS",    "📦 Espera entre guías",        200,  15_000, 200),
    ("TIEMPO_ESPERA_INGRESO_CODIGOS","⌨️  Espera ingreso de códigos", 200,  10_000, 100),
    ("TIEMPO_ESPERA_VOLVER",         "↩️  Espera botón Volver",       500,  30_000, 500),
    ("MAX_REINTENTOS",               "🔄 Máx. reintentos por guía",    1,      10,   1),
]


class SettingsDialog(QDialog):
    """Diálogo para ajustar tiempos y límites del proceso."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Configuración Avanzada")
        self.setMinimumSize(500, 520)
        self.setSizeGripEnabled(True)
        self.setModal(True)

        self._settings  = SettingsManager.get_instance()
        self._spinboxes: dict[str, QSpinBox] = {}

        self._setup_ui()
        self._setup_styles()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setObjectName("cfg_header")
        header.setFixedHeight(58)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        titulo = QLabel("⚙️  CONFIGURACIÓN AVANZADA")
        titulo.setObjectName("cfg_titulo")
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(titulo)
        root.addWidget(header)

        # Body
        body = QFrame()
        body.setObjectName("cfg_body")
        body_layout = QVBoxLayout(body)
        body_layout.setSpacing(12)
        body_layout.setContentsMargins(22, 16, 22, 16)

        nota = QLabel("Los cambios se aplican al próximo proceso iniciado")
        nota.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nota.setObjectName("cfg_nota")
        body_layout.addWidget(nota)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("cfg_sep")
        body_layout.addWidget(sep)

        # Scroll con spinboxes
        scroll = QScrollArea()
        scroll.setObjectName("cfg_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        contenido = QWidget()
        contenido.setObjectName("cfg_contenido")
        form = QFormLayout(contenido)
        form.setSpacing(11)
        form.setContentsMargins(8, 8, 8, 8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        for key, label, mn, mx, step in _CAMPOS:
            lbl_widget = QLabel(label)
            lbl_widget.setObjectName("cfg_lbl_campo")

            sufijo = " ms" if "TIEMPO" in key else ""

            spin = QSpinBox()
            spin.setObjectName("cfg_spin")
            spin.setMinimum(mn)
            spin.setMaximum(mx)
            spin.setSingleStep(step)
            spin.setSuffix(sufijo)
            spin.setValue(int(self._settings.get(key)))
            spin.setMinimumHeight(32)
            self._spinboxes[key] = spin
            form.addRow(lbl_widget, spin)

        scroll.setWidget(contenido)
        body_layout.addWidget(scroll)

        root.addWidget(body, stretch=1)

        # Botones
        btn_bar = QFrame()
        btn_bar.setObjectName("cfg_btn_bar")
        btn_row = QHBoxLayout(btn_bar)
        btn_row.setContentsMargins(20, 12, 20, 12)
        btn_row.setSpacing(10)

        btn_reset = QPushButton("🔄 Restaurar defaults")
        btn_reset.setObjectName("btn_cfg_reset")
        btn_reset.clicked.connect(self._reset_defaults)
        btn_row.addWidget(btn_reset)

        btn_row.addStretch()

        btn_cancel = QPushButton("❌  Cancelar")
        btn_cancel.setObjectName("btn_cfg_cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("✅  Guardar")
        btn_save.setObjectName("btn_cfg_save")
        btn_save.clicked.connect(self._guardar)
        btn_row.addWidget(btn_save)

        root.addWidget(btn_bar)

    def _setup_styles(self):
        c = theme.colors()
        self.setStyleSheet(theme.base_stylesheet() + f"""
            QDialog {{ background-color: {c['bg']}; }}

            /* ── Header ── */
            QFrame#cfg_header {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {c['surface2']}, stop:1 {c['surface']});
                border-bottom: 1.5px solid {c['border']};
            }}
            QLabel#cfg_titulo {{
                color: {c['text']};
                font-size: 13pt;
                font-weight: 800;
                letter-spacing: -0.3px;
            }}

            /* ── Body ── */
            QFrame#cfg_body {{ background-color: {c['bg']}; }}

            QLabel#cfg_nota {{
                color: {c['text3']};
                font-size: 9pt;
                font-style: italic;
            }}
            QFrame#cfg_sep {{
                background-color: {c['border']};
                max-height: 1px;
            }}

            /* ── Scroll / form ── */
            QScrollArea#cfg_scroll {{ background: transparent; border: none; }}
            QWidget#cfg_contenido  {{ background-color: {c['bg']}; }}

            QLabel#cfg_lbl_campo {{
                color: {c['text2']};
                font-size: 10pt;
            }}

            QSpinBox#cfg_spin {{
                background-color: {c['surface']};
                color: {c['text']};
                border: 1.5px solid {c['border']};
                border-radius: 8px;
                padding: 4px 10px;
                font-size: 10pt;
                min-height: 30px;
            }}
            QSpinBox#cfg_spin:focus {{ border-color: {c['accent']}; }}

            /* ── Botones ── */
            QFrame#cfg_btn_bar {{
                background-color: {c['action_bg']};
                border-top: 1px solid {c['border']};
            }}
            QPushButton {{
                padding: 9px 22px;
                border-radius: 10px;
                font-weight: bold;
                font-size: 10pt;
                min-height: 36px;
            }}
            QPushButton#btn_cfg_save {{
                background-color: {c['success']};
                color: white;
                border: none;
            }}
            QPushButton#btn_cfg_save:hover {{
                border: 2px solid {c['success']};
            }}
            QPushButton#btn_cfg_save:pressed {{
                background-color: {c['success_bg']};
                color: {c['success']};
                border: 2px solid {c['success']};
            }}
            QPushButton#btn_cfg_cancel {{
                background-color: transparent;
                color: {c['text2']};
                border: 1.5px solid {c['border']};
            }}
            QPushButton#btn_cfg_cancel:hover {{
                background-color: {c['surface2']};
                border-color: {c['border_strong']};
            }}
            QPushButton#btn_cfg_reset {{
                background-color: transparent;
                color: {c['warning']};
                border: 1.5px solid {c['warning']};
            }}
            QPushButton#btn_cfg_reset:hover {{
                background-color: {c['warning_bg']};
            }}
        """)

    # ── Lógica ───────────────────────────────────────────────────────────────

    def _reset_defaults(self):
        for key, spin in self._spinboxes.items():
            spin.setValue(int(_DEFAULTS.get(key, spin.value())))

    def _guardar(self):
        for key, spin in self._spinboxes.items():
            self._settings.set(key, spin.value())
        self._settings.save()
        self.accept()
