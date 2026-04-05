# ui/main_window.py
"""
Ventana principal de la aplicación
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QTextEdit, QFileDialog,
    QMessageBox, QGroupBox, QFormLayout, QSpinBox, QDialog, QTabWidget,
    QTextEdit as QTextEditWidget, QScrollArea, QFrame, QSizePolicy,
    QSystemTrayIcon, QSplitter
)
from PySide6.QtCore import Qt, QTimer, QUrl, QThread, Signal as _Signal
from PySide6.QtGui import QTextCursor, QFont, QDragEnterEvent, QDropEvent, QFontMetrics, QShortcut, QKeySequence
from ui.widgets.animated_button import AnimatedButton
from ui.widgets.rounded_combo import RoundedComboBox
from utils.win_blur import apply_blur
from datetime import datetime, timedelta
from pathlib import Path
import os
import subprocess
import sys

from ui.login_window import LoginWindow
from ui.resumen_window import ResumenWindow
from ui.resumen_viaje_window import ResumenViajeWindow
from ui.historial_window import HistorialWindow
from ui.widgets.progress_bar import MacProgressBar
from ui.widgets.confirm_dialog import ConfirmDialog
from workers.proceso_thread import ProcesoThread
from workers.desviacion_viajes_thread import DesviacionViajesThread
from ui.widgets.viaje_queue import ViajesQueueWidget
from config.constants import CIUDADES, TIPOS_INCIDENCIA, ERROR_MESSAGES
from utils.file_utils import FileUtils
from utils.history_storage import HistoryStorage
from utils.settings_manager import SettingsManager
from utils.taskbar_progress import TaskbarProgress, TBPF_ERROR, TBPF_PAUSED, TBPF_NORMAL
from utils import theme

try:
    import keyring
    _KEYRING_OK = True
except ImportError:
    _KEYRING_OK = False

class _PingThread(QThread):
    """Mide la latencia HTTP al servidor objetivo sin abrir navegador."""
    resultado = _Signal(int, bool)   # (ms, exitoso)

    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self._url = url

    def run(self):
        import urllib.request, time
        try:
            t0 = time.perf_counter()
            urllib.request.urlopen(self._url, timeout=10)
            ms = int((time.perf_counter() - t0) * 1000)
            self.resultado.emit(ms, True)
        except Exception:
            self.resultado.emit(-1, False)


class VentanaPrincipal(QMainWindow):
    """Ventana principal de la aplicación"""
    
    def __init__(self):
        super().__init__()
        self.excel_path = None
        self.guias_pegadas = []       # Guías ingresadas manualmente por el usuario
        self.proceso_thread = None
        self.sesion_activa = False
        self.usuario_actual = ""
        self.password_actual = ""
        self.historial_datos = []
        self.historial_window = None
        self.tiempo_inicio = None
        self.total_guias = 0
        self.guias_ent = []
        self.guias_error_count = 0
        self.guias_advertencia_count = 0
        self.desviaciones_creadas = 0
        self.guias_duplicadas_count = 0
        self.carpeta_descargas = FileUtils.obtener_carpeta_descargas()
        self._tray_icon = None
        self._log_auto_scroll = True
        self._log_entries = []          # (html, level) para filtrado
        self._log_filter = 'all'        # 'all' | 'success' | 'warning' | 'error'
        self._headless = SettingsManager.get_instance().get("headless_mode", True)
        self._cola_viajes = []          # Cola de viajes pendientes (modo múltiple)
        self._viaje_actual_idx = 0      # Índice del viaje que se está procesando
        self._total_viajes_cola = 0     # Total de viajes en la cola actual

        # Debounce para el área de guías pegadas — evita procesar en cada keypress
        self._debounce_guias = QTimer()
        self._debounce_guias.setSingleShot(True)
        self._debounce_guias.setInterval(300)
        self._debounce_guias.timeout.connect(self._procesar_guias_pegadas)

        # Timer de tiempo transcurrido — se actualiza cada segundo durante el proceso
        self._timer_transcurrido = QTimer()
        self._timer_transcurrido.setInterval(1000)
        self._timer_transcurrido.timeout.connect(self._tick_tiempo_transcurrido)

        self._setup_ui()
        self._setup_styles()
        self._init_tray_icon()
        self._setup_shortcuts()
        # Historial solo de la sesión actual — no se cargan sesiones anteriores
        self.historial_datos = []
        self.setAcceptDrops(True)
        # Restaurar geometría guardada
        _geom = SettingsManager.get_instance().get("main_window_geometry", None)
        if _geom:
            from PySide6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromBase64(_geom.encode()))

    def _setup_ui(self):
        """Configura la interfaz de usuario"""
        self.setWindowTitle("ALERTRAN — Gestión de Operaciones")
        self.setMinimumSize(800, 500)
        self.resize(1200, 700)

        central = QWidget()
        central.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root = QVBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Header bar ────────────────────────────────────────
        root.addWidget(self._crear_header_bar())

        # ── Separador ─────────────────────────────────────────
        sep_top = QFrame()
        sep_top.setFrameShape(QFrame.Shape.HLine)
        sep_top.setObjectName("sep_line")
        root.addWidget(sep_top)

        # ── Main content (splitter horizontal) ────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setChildrenCollapsible(False)
        splitter.setObjectName("main_splitter")

        # Panel izquierdo: configuración
        left = QWidget()
        left.setObjectName("left_panel")
        left.setMinimumWidth(260)
        left.setMaximumWidth(650)
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(12, 12, 6, 8)

        self.tab_widget = QTabWidget()
        self.tab_widget.setObjectName("main_tabs")
        self.tab_widget.tabBar().setExpanding(True)
        self.tab_widget.tabBar().setElideMode(Qt.TextElideMode.ElideRight)

        tab_desviaciones = QWidget()
        ld = QVBoxLayout(tab_desviaciones)
        ld.setContentsMargins(0, 8, 0, 0)
        ld.setSpacing(0)
        ld.addWidget(self._crear_panel_configuracion())
        ld.addStretch()
        self.tab_widget.addTab(tab_desviaciones, "📦 Desviaciones")

        tab_viajes = QWidget()
        lv = QVBoxLayout(tab_viajes)
        lv.setContentsMargins(0, 8, 0, 0)
        lv.setSpacing(0)
        lv.addWidget(self._crear_panel_configuracion_desviacion())
        lv.addStretch()
        self.tab_widget.addTab(tab_viajes, "🚚 Viajes")

        left_layout.addWidget(self.tab_widget)
        self.panel_excel = self._crear_panel_excel()
        left_layout.addWidget(self.panel_excel)
        left_layout.addStretch()

        self.tab_widget.currentChanged.connect(self._on_tab_changed)

        # Panel derecho: progreso + log
        right = QWidget()
        right.setObjectName("right_panel")
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(6, 12, 12, 8)
        right_layout.addWidget(self._crear_panel_progreso())
        right_layout.addWidget(self._crear_panel_log(), stretch=1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        saved_sizes = SettingsManager.get_instance().get("splitter_sizes", [570, 830])
        splitter.setSizes(saved_sizes)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self._splitter = splitter

        root.addWidget(splitter, stretch=1)

        # ── Separador ─────────────────────────────────────────
        sep_bot = QFrame()
        sep_bot.setFrameShape(QFrame.Shape.HLine)
        sep_bot.setObjectName("sep_line")
        root.addWidget(sep_bot)

        # ── Barra de acciones ─────────────────────────────────
        root.addWidget(self._crear_barra_acciones())

        # ── Footer ────────────────────────────────────────────
        root.addWidget(self._crear_footer())

        self.setCentralWidget(central)
        self._apply_shadows()
        self.show()
        self._fade_in()
        QTimer.singleShot(150, self._apply_blur)

    def showEvent(self, event):
        super().showEvent(event)
        if not hasattr(self, '_taskbar'):
            self._taskbar = TaskbarProgress(int(self.winId()))

    def closeEvent(self, event):
        # Si hay un proceso corriendo, pedir confirmación antes de cerrar
        if self.proceso_thread is not None and self.proceso_thread.isRunning():
            reply = QMessageBox.question(
                self,
                "Proceso activo",
                "Hay un proceso en curso.\n\n"
                "¿Desea cancelar el proceso y cerrar la aplicación?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            # Cancelar el proceso y esperar a que termine
            self.proceso_thread.cancelar()
            self.proceso_thread.wait(5000)  # máximo 5 s

        if hasattr(self, '_taskbar'):
            self._taskbar.clear_overlay()
            self._taskbar.destroy()
        sm = SettingsManager.get_instance()
        sm.set("splitter_sizes", self._splitter.sizes())
        sm.set("main_window_geometry", self.saveGeometry().toBase64().data().decode())
        sm.save()
        super().closeEvent(event)

    def _apply_blur(self):
        ok = apply_blur(self, dark=theme.is_dark())
        if not ok:
            pass  # No Windows o versión no soportada — continúa sin blur

    def _fade_in(self):
        from PySide6.QtCore import QPropertyAnimation
        anim = QPropertyAnimation(self, b"windowOpacity")
        anim.setDuration(280)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._fade_anim = anim  # evitar que el GC lo destruya

    def _elide_archivo(self, texto: str) -> str:
        """Devuelve el texto elided si no cabe en el label."""
        fm = QFontMetrics(self.lbl_archivo.font())
        max_w = self.lbl_archivo.width() or 300
        return fm.elidedText(texto, Qt.TextElideMode.ElideRight, max_w)

    def _apply_shadows(self):
        """Agrega sombras drop-shadow a elementos clave."""
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor

        def _shadow(blur=18, dy=3, color="#000000", alpha=40):
            eff = QGraphicsDropShadowEffect()
            eff.setBlurRadius(blur)
            eff.setOffset(0, dy)
            c = QColor(color)
            c.setAlpha(alpha)
            eff.setColor(c)
            return eff

        self.btn_login.setGraphicsEffect(_shadow(14, 2, "#007aff", 60))
        self.btn_logout.setGraphicsEffect(_shadow(10, 2, "#ff3b30", 50))

    def _crear_header_bar(self):
        """Barra de título y sesión fija en la parte superior"""
        frame = QFrame()
        frame.setObjectName("header_bar")
        frame.setMinimumHeight(50)
        frame.setMaximumHeight(70)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 0, 18, 0)
        layout.setSpacing(14)

        # App title
        lbl_app = QLabel("🔔  ALERTRAN Gestión de Desviaciones")
        lbl_app.setObjectName("app_title")
        layout.addWidget(lbl_app)

        layout.addStretch()

        SP = QSizePolicy.Policy

        self.lbl_estado_sesion = QLabel("⛔  Sin sesión")
        self.lbl_estado_sesion.setObjectName("lbl_sesion")
        self.lbl_estado_sesion.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_estado_sesion.setSizePolicy(SP.Expanding, SP.Fixed)
        self.lbl_estado_sesion.setMinimumWidth(120)
        self.lbl_estado_sesion.setMinimumHeight(34)
        layout.addWidget(self.lbl_estado_sesion)

        self.btn_login = QPushButton("🔑  Iniciar sesión")
        self.btn_login.setObjectName("btn_login")
        self.btn_login.setSizePolicy(SP.Expanding, SP.Fixed)
        self.btn_login.setMinimumWidth(120)
        self.btn_login.setMinimumHeight(34)
        self.btn_login.clicked.connect(self.abrir_login)
        layout.addWidget(self.btn_login)

        self.btn_logout = QPushButton("🚪  Cerrar sesión")
        self.btn_logout.setObjectName("btn_logout")
        self.btn_logout.setSizePolicy(SP.Expanding, SP.Fixed)
        self.btn_logout.setMinimumWidth(120)
        self.btn_logout.setMinimumHeight(34)
        self.btn_logout.clicked.connect(self.cerrar_sesion)
        self.btn_logout.setEnabled(False)
        layout.addWidget(self.btn_logout)

        # Toggle tema — esquina superior derecha
        self.btn_theme = QPushButton("🌙" if theme.is_dark() else "☀️")
        self.btn_theme.setObjectName("btn_theme")
        self.btn_theme.setFixedSize(38, 38)
        self.btn_theme.setToolTip("Cambiar tema claro / oscuro")
        self.btn_theme.clicked.connect(self._toggle_theme)
        layout.addWidget(self.btn_theme)

        return frame

    def _crear_panel_configuracion(self):
        """Panel para desviaciones — QFormLayout + fila combinada Tipo/Nav"""
        grupo = QGroupBox("⚙️ CONFIGURACIÓN DESVIACIONES")

        form = QFormLayout(grupo)
        form.setSpacing(8)
        form.setContentsMargins(10, 18, 10, 14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(8)

        SP = QSizePolicy.Policy

        # ── Regional (ancho completo) ────────────────────────
        self.ciudad_combo = RoundedComboBox()
        self.ciudad_combo.addItems(CIUDADES)
        self.ciudad_combo.setCurrentText("ABA BARRANQUILLA AEROPUER")
        self.ciudad_combo.setEditable(True)
        self.ciudad_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ciudad_combo.setSizePolicy(SP.Expanding, SP.Fixed)
        form.addRow("📍 Regional:", self.ciudad_combo)

        # ── Tipo + Navegadores en la misma fila ──────────────
        self.tipo_combo = RoundedComboBox()
        self.tipo_combo.addItems(TIPOS_INCIDENCIA)
        self.tipo_combo.setCurrentText("22")
        self.tipo_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.tipo_combo.setSizePolicy(SP.Expanding, SP.Fixed)
        self.tipo_combo.setMinimumWidth(72)

        self.num_navegadores_spin = QSpinBox()
        self.num_navegadores_spin.setMinimum(1)
        self.num_navegadores_spin.setMaximum(100)
        self.num_navegadores_spin.setValue(1)
        self.num_navegadores_spin.setPrefix("🚀 ")
        self.num_navegadores_spin.setSizePolicy(SP.Expanding, SP.Fixed)
        self.num_navegadores_spin.setMinimumWidth(86)

        self.num_navegadores_spin.setToolTip("Número de navegadores paralelos")

        tipo_nav = QHBoxLayout()
        tipo_nav.setSpacing(6)
        tipo_nav.addWidget(self.tipo_combo, stretch=3)
        tipo_nav.addWidget(self.num_navegadores_spin, stretch=2)
        form.addRow("📌 Tipo / Nav:", tipo_nav)

        # ── Ampliación (ancho completo) — combo con historial ────────────
        self.ampliacion_input = RoundedComboBox()
        self.ampliacion_input.setEditable(True)
        self.ampliacion_input.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.ampliacion_input.lineEdit().setPlaceholderText("Ampliación Desviación")
        self.ampliacion_input.setSizePolicy(SP.Expanding, SP.Fixed)
        self.ampliacion_input.setToolTip("Últimas ampliaciones usadas")
        for amp in SettingsManager.get_instance().get("ampliaciones_recientes", []):
            self.ampliacion_input.addItem(amp)
        self.ampliacion_input.setCurrentIndex(-1)
        form.addRow("📝 Ampliación:", self.ampliacion_input)

        return grupo

    def _crear_panel_configuracion_desviacion(self):
        grupo = QGroupBox("🚚 CONFIGURACIÓN DESVIACIÓN DE VIAJES")

        form = QFormLayout(grupo)
        form.setSpacing(8)
        form.setContentsMargins(10, 18, 10, 14)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setHorizontalSpacing(8)

        SP = QSizePolicy.Policy

        # ── Regional (ancho completo) ────────────────────────
        self.ciudad_combo_desv = RoundedComboBox()
        self.ciudad_combo_desv.addItems(CIUDADES)
        self.ciudad_combo_desv.setCurrentText("ABA BARRANQUILLA AEROPUER")
        self.ciudad_combo_desv.setEditable(True)
        self.ciudad_combo_desv.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.ciudad_combo_desv.setSizePolicy(SP.Expanding, SP.Fixed)
        form.addRow("📍 Regional:", self.ciudad_combo_desv)

        # ── Tipo de desviación ────────────────────────────────
        self.tipo_desviacion_combo = RoundedComboBox()
        self.tipo_desviacion_combo.addItems(TIPOS_INCIDENCIA)
        self.tipo_desviacion_combo.setCurrentText("22")
        self.tipo_desviacion_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.tipo_desviacion_combo.setSizePolicy(SP.Expanding, SP.Fixed)
        self.tipo_desviacion_combo.setMinimumWidth(72)
        self.tipo_desviacion_combo.setToolTip("Tipo de incidencia")
        form.addRow("📌 Tipo Desviación:", self.tipo_desviacion_combo)

        # ── Cola visual de viajes ─────────────────────────────
        self.viaje_queue = ViajesQueueWidget()
        self.viaje_queue.queue_changed.connect(self._sync_global_fields)
        form.addRow("🎫 Viajes:", self.viaje_queue)

        # ── Observaciones (ancho completo) ───────────────────
        self.observaciones_input = QTextEditWidget()
        self.observaciones_input.setPlaceholderText("Ingrese las observaciones para la desviación...")
        self.observaciones_input.setMinimumHeight(72)
        self.observaciones_input.setMaximumHeight(160)
        self.observaciones_input.setSizePolicy(SP.Expanding, SP.Expanding)
        self.observaciones_input.setStyleSheet("""
            QScrollBar:vertical {
                background: transparent; width: 8px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #555; border-radius: 4px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        form.addRow("📝 Observaciones:", self.observaciones_input)

        return grupo

    def _crear_panel_excel(self):
        # Contenedor principal (reemplaza QGroupBox para poder poner botón en el título)
        container = QFrame()
        container.setObjectName("excel_panel_container")
        outer = QVBoxLayout(container)
        outer.setSpacing(0)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Barra de título con botón ✕ en la esquina superior derecha ──
        title_bar = QWidget()
        title_bar.setObjectName("excel_panel_titlebar")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(14, 6, 8, 6)
        title_layout.setSpacing(4)

        title_lbl = QLabel("📁 ARCHIVO DE GUÍAS")
        title_lbl.setObjectName("excel_panel_title")
        title_layout.addWidget(title_lbl)
        title_layout.addStretch()

        self.btn_quitar_excel = QPushButton("✕")
        self.btn_quitar_excel.setObjectName("btn_quitar_excel")
        self.btn_quitar_excel.setFixedSize(22, 22)
        self.btn_quitar_excel.setToolTip("Quitar archivo")
        self.btn_quitar_excel.setEnabled(False)
        self.btn_quitar_excel.clicked.connect(self._quitar_excel)
        title_layout.addWidget(self.btn_quitar_excel)
        outer.addWidget(title_bar)

        # ── Contenido ──────────────────────────────────────────────────
        content = QWidget()
        content.setObjectName("excel_panel_content")
        layout_excel = QVBoxLayout(content)
        layout_excel.setSpacing(6)
        layout_excel.setContentsMargins(10, 4, 10, 10)

        SP = QSizePolicy.Policy

        # Fila 1: botón cargar + label archivo
        layout_boton_excel = QHBoxLayout()
        self.btn_cargar_excel = QPushButton("📂 CARGAR EXCEL")
        self.btn_cargar_excel.setObjectName("btn_cargar_excel")
        self.btn_cargar_excel.clicked.connect(self.cargar_excel)
        self.btn_cargar_excel.setEnabled(False)
        self.btn_cargar_excel.setSizePolicy(SP.Expanding, SP.Fixed)
        self.btn_cargar_excel.setMinimumWidth(80)
        layout_boton_excel.addWidget(self.btn_cargar_excel)

        self.lbl_archivo = QLabel("❌  Sin archivo")
        self.lbl_archivo.setStyleSheet("color: #ff453a; font-style: italic; font-size: 10pt;")
        self.lbl_archivo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.lbl_archivo.setWordWrap(False)
        self.lbl_archivo.setToolTip("❌  Sin archivo")
        layout_boton_excel.addWidget(self.lbl_archivo)
        layout_boton_excel.addStretch()
        layout_excel.addLayout(layout_boton_excel)

        # Indicador de drag & drop
        lbl_dd = QLabel("⬇  o arrastra un .xlsx aquí")
        lbl_dd.setObjectName("lbl_drag_hint")
        lbl_dd.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout_excel.addWidget(lbl_dd)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sep_line")
        layout_excel.addWidget(sep)

        # Fila 2: área de pegado de guías
        self.txt_guias_pegar = QTextEdit()
        self.txt_guias_pegar.setObjectName("txt_guias_pegar")
        self.txt_guias_pegar.setToolTip(
            "Pegue las guías a procesar, una por línea.\n"
            "Solo números (ej: 123456789)\n"
            "Se ignoran duplicados y líneas vacías automáticamente."
        )
        self.txt_guias_pegar.setPlaceholderText(
            "📋  Pega aquí las guías (una por línea)\n"
            "Ej:\n  123456789\n  987654321\n  ..."
        )
        self.txt_guias_pegar.setEnabled(False)
        self.txt_guias_pegar.setMinimumHeight(110)
        self.txt_guias_pegar.setSizePolicy(SP.Expanding, SP.Expanding)
        self.txt_guias_pegar.textChanged.connect(self._on_guias_text_changed)
        layout_excel.addWidget(self.txt_guias_pegar)

        # Fila 3: conteo de guías pegadas
        self.lbl_guias_pegadas = QLabel("📋  0 guías")
        self.lbl_guias_pegadas.setObjectName("lbl_guias_pegadas")
        self.lbl_guias_pegadas.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout_excel.addWidget(self.lbl_guias_pegadas)

        outer.addWidget(content)
        return container

    def _crear_panel_progreso(self):
        grupo = QGroupBox("📊 PROGRESO")

        layout_progreso = QVBoxLayout(grupo)
        layout_progreso.setSpacing(40)
        layout_progreso.setContentsMargins(12, 14, 12, 10)

        self.progress_bar = MacProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.valueChanged.connect(self._sync_taskbar_progress)
        layout_progreso.addWidget(self.progress_bar)

        row = QHBoxLayout()
        self.lbl_estado = QLabel("💤  Listo")
        self.lbl_estado.setObjectName("lbl_estado")
        self.lbl_estado.setStyleSheet("color: #636366; font-weight: 600; font-size: 10pt;")
        row.addWidget(self.lbl_estado)

        row.addStretch()

        self.lbl_tiempo_transcurrido = QLabel("")
        self.lbl_tiempo_transcurrido.setObjectName("lbl_transcurrido")
        self.lbl_tiempo_transcurrido.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_tiempo_transcurrido.setStyleSheet("color: #636366; font-weight: 600; font-size: 10pt;")
        row.addWidget(self.lbl_tiempo_transcurrido)

        self.lbl_tiempo_restante = QLabel("")
        self.lbl_tiempo_restante.setObjectName("lbl_tiempo")
        self.lbl_tiempo_restante.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_tiempo_restante.setStyleSheet("color: #0a84ff; font-weight: 600; font-size: 10pt;")
        row.addWidget(self.lbl_tiempo_restante)

        layout_progreso.addLayout(row)
        return grupo

    def _crear_panel_log(self):
        grupo = QGroupBox("📋 REGISTRO DE ACTIVIDAD")
        layout_log = QVBoxLayout(grupo)
        layout_log.setSpacing(6)

        # ── Toolbar de filtros + auto-scroll ──────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet("background: transparent;")
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(0, 0, 0, 0)
        tb_lay.setSpacing(4)

        _c = theme.colors()

        def _pill(text, level, checked=False):
            b = QPushButton(text)
            b.setObjectName(f"log_filter_{level}")
            b.setCheckable(True)
            b.setChecked(checked)
            b.setFixedHeight(26)
            b.clicked.connect(lambda _, lv=level: self._set_log_filter(lv))
            return b

        self._btn_filter_all     = _pill("Todos",  "all",     True)
        self._btn_filter_ok      = _pill("✅ OK",   "success", False)
        self._btn_filter_warn    = _pill("⚠️ Aviso","warning", False)
        self._btn_filter_error   = _pill("❌ Error","error",   False)

        for b in (self._btn_filter_all, self._btn_filter_ok,
                  self._btn_filter_warn, self._btn_filter_error):
            tb_lay.addWidget(b)

        tb_lay.addStretch()

        # Botón limpiar log
        btn_clear = QPushButton("🗑")
        btn_clear.setObjectName("log_btn_small")
        btn_clear.setFixedSize(28, 26)
        btn_clear.setToolTip("Limpiar log (Ctrl+L)")
        btn_clear.clicked.connect(self._limpiar_log)
        tb_lay.addWidget(btn_clear)

        # Botón auto-scroll
        self.btn_log_scroll = QPushButton("↓ Auto")
        self.btn_log_scroll.setObjectName("log_btn_scroll")
        self.btn_log_scroll.setCheckable(True)
        self.btn_log_scroll.setChecked(True)
        self.btn_log_scroll.setFixedHeight(26)
        self.btn_log_scroll.setToolTip("Pausar/reanudar auto-scroll")
        self.btn_log_scroll.clicked.connect(self._toggle_log_scroll)
        tb_lay.addWidget(self.btn_log_scroll)

        layout_log.addWidget(toolbar)

        # ── Área de texto ─────────────────────────────────────────────────
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(80)
        self.log_text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log_text.setStyleSheet(
            f"QTextEdit {{ background-color: {_c['log_bg']};"
            f" font-family: 'SF Mono', 'Consolas', 'Courier New', monospace;"
            f" font-size: 9.5pt; border: 1px solid {_c['border']};"
            f" border-radius: 10px; color: {_c['log_fg']}; padding: 10px; }}"
        )
        # Auto-detect scroll manual: si el usuario sube, desactiva auto-scroll
        self.log_text.verticalScrollBar().valueChanged.connect(self._on_log_scroll_changed)
        layout_log.addWidget(self.log_text)

        return grupo

    def _crear_barra_acciones(self):
        """Barra inferior con todos los botones de acción"""
        frame = QFrame()
        frame.setObjectName("action_bar")
        frame.setMinimumHeight(50)
        frame.setMaximumHeight(80)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(6)

        # ── Controles de proceso ─────────────────────────────
        self.btn_iniciar = QPushButton("▶  INICIAR")
        self.btn_iniciar.setObjectName("btn_iniciar")
        self.btn_iniciar.clicked.connect(self.iniciar_proceso)
        self.btn_iniciar.setEnabled(False)
        self.btn_iniciar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_iniciar)

        self.btn_pausar = QPushButton("⏸  PAUSAR")
        self.btn_pausar.setObjectName("btn_pausar")
        self.btn_pausar.clicked.connect(self.toggle_pausa)
        self.btn_pausar.setEnabled(False)
        self.btn_pausar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_pausar)

        self.btn_cancelar = QPushButton("⏹  CANCELAR")
        self.btn_cancelar.setObjectName("btn_cancelar")
        self.btn_cancelar.clicked.connect(self.cancelar_proceso)
        self.btn_cancelar.setEnabled(False)
        self.btn_cancelar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_cancelar)

        # Separador vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("sep_line")
        layout.addWidget(sep)

        # ── Herramientas (AnimatedButton — transición de color real) ──────────
        _c = theme.colors()

        self.btn_probar = AnimatedButton(
            "🔌  Probar",
            normal_color=_c['btn_tool_bg'], hover_color=_c['accent'],
            text_color=_c['accent'], hover_text="#ffffff"
        )
        self.btn_probar.setObjectName("btn_probar")
        self.btn_probar.setToolTip("Verifica login y acceso a funcionalidad 7.8\nantes de lanzar el proceso completo")
        self.btn_probar.clicked.connect(self._probar_conexion)
        self.btn_probar.setEnabled(True)   # disponible sin login — solo mide ping
        self.btn_probar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_probar)

        self.btn_historial = AnimatedButton(
            "📋  Historial",
            normal_color=_c['btn_tool_bg'], hover_color=_c['accent'],
            text_color=_c['accent'], hover_text="#ffffff"
        )
        self.btn_historial.setObjectName("btn_historial")
        self.btn_historial.clicked.connect(self.ver_historial)
        self.btn_historial.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_historial)

        self.btn_ver_cola = AnimatedButton(
            "🎫  Cola",
            normal_color=_c['btn_tool_bg'], hover_color=_c['accent'],
            text_color=_c['accent'], hover_text="#ffffff"
        )
        self.btn_ver_cola.setObjectName("btn_ver_cola")
        self.btn_ver_cola.setToolTip("Ver resumen de la cola de viajes")
        self.btn_ver_cola.clicked.connect(self._mostrar_resumen_cola)
        self.btn_ver_cola.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_ver_cola)

        self.btn_reprocesar = AnimatedButton(
            "🔁  Reprocesar",
            normal_color=_c['btn_tool_bg'], hover_color=_c['success'],
            text_color=_c['success'], hover_text="#ffffff"
        )
        self.btn_reprocesar.setObjectName("btn_reprocesar")
        self.btn_reprocesar.clicked.connect(self.reprocesar_errores)
        self.btn_reprocesar.setEnabled(False)
        self.btn_reprocesar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_reprocesar)

        self.btn_errores = AnimatedButton(
            "📥  Errores",
            normal_color=_c['btn_tool_bg'], hover_color=_c['error'],
            text_color=_c['error'], hover_text="#ffffff"
        )
        self.btn_errores.setObjectName("btn_errores")
        self.btn_errores.clicked.connect(self.mostrar_errores)
        self.btn_errores.setEnabled(False)
        self.btn_errores.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_errores)

        self.btn_descargar_log = AnimatedButton(
            "💾  Log",
            normal_color=_c['btn_tool_bg'], hover_color=_c['purple'],
            text_color=_c['purple'], hover_text="#ffffff"
        )
        self.btn_descargar_log.setObjectName("btn_descargar_log")
        self.btn_descargar_log.clicked.connect(self.descargar_log)
        self.btn_descargar_log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_descargar_log)

        layout.addStretch()

        # ── Modo navegador: visible / headless ───────────────────────────
        _hl_text  = "🔒  Oculto"  if self._headless else "👀  Visible"
        _hl_hover = _c['warning'] if self._headless else _c['success']
        self.btn_headless = AnimatedButton(
            _hl_text,
            normal_color=_c['btn_tool_bg'], hover_color=_hl_hover,
            text_color=_hl_hover, hover_text="#ffffff"
        )
        self.btn_headless.setObjectName("btn_headless")
        self.btn_headless.setToolTip(
            "👀 Visible: el navegador se abre en pantalla\n"
            "🔒 Oculto: el navegador corre en segundo plano (headless)"
        )
        self.btn_headless.clicked.connect(self._toggle_headless)
        self.btn_headless.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_headless)

        self.btn_config = AnimatedButton(
            "⚙️  Config",
            normal_color=_c['btn_tool_bg'], hover_color=_c['surface2'],
            text_color=_c['text2'], hover_text=_c['text']
        )
        self.btn_config.setObjectName("btn_config")
        self.btn_config.clicked.connect(self.abrir_configuracion)
        self.btn_config.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.btn_config)

        return frame

    def _crear_footer(self):
        frame = QFrame()
        frame.setObjectName("footer_bar")
        frame.setMinimumHeight(20)
        frame.setMaximumHeight(30)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 12, 0)
        lbl = QLabel("🤖  ALERTRAN  v9.0")
        lbl.setObjectName("footer_label")
        layout.addStretch()
        layout.addWidget(lbl)
        return frame

    def _setup_styles(self):
        c = theme.colors()
        self.setStyleSheet(theme.base_stylesheet() + f"""
            /* ── Layout panels — semi-transparentes para blur visible ── */
            QWidget#right_panel {{
                background-color: {'rgba(28,28,30,0.72)' if theme.is_dark() else 'rgba(242,242,247,0.72)'};
            }}

            /* ── Finder-style sidebar ── */
            QWidget#left_panel {{
                background-color: {'rgba(44,44,46,0.80)' if theme.is_dark() else 'rgba(255,255,255,0.80)'};
                border-right: 1px solid {c['border']};
            }}

            /* ── Header bar — glass toolbar ── */
            QFrame#header_bar {{
                background-color: {'rgba(17,17,19,0.85)' if theme.is_dark() else 'rgba(249,249,251,0.85)'};
                border-bottom: 1.5px solid {c['border']};
            }}
            QLabel#app_title {{
                color: {c['text']};
                font-size: 13pt;
                font-weight: 800;
                letter-spacing: -0.5px;
            }}

            /* ── Session label style ── */
            QLabel#lbl_sesion {{
                background-color: {c['surface2']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                font-weight: 600;
                font-size: 9.5pt;
                padding: 4px 10px;
                color: {c['text2']};
            }}

            /* ── Separadores ── */
            QFrame#sep_line {{
                background-color: {c['sep']};
                max-height: 1px;
                border: none;
            }}

            /* ── Tabs — underline style ── */
            QTabWidget#main_tabs::pane {{
                background-color: {c['surface']};
                border: 1.5px solid {c['border']};
                border-radius: 12px;
                top: -2px;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: {c['text3']};
                padding: 8px 10px;
                min-width: 0;
                border: none;
                border-bottom: 2px solid transparent;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 600;
                font-size: 10pt;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                color: {c['accent']};
                border-bottom: 2.5px solid {c['accent']};
                background-color: {c['surface']};
            }}
            QTabBar::tab:hover:!selected {{
                color: {c['text']};
                background-color: {c['surface2']};
            }}

            /* ── Labels ── */
            QLabel#lbl_estado {{
                color: {c['text3']};
                font-weight: 600;
                font-size: 9pt;
            }}
            QLabel#lbl_tiempo {{
                color: {c['accent']};
                font-weight: 700;
                font-size: 10pt;
            }}
            QLabel#footer_label {{
                color: {c['text4']};
                font-size: 8pt;
            }}

            /* ── Action bar ── */
            QFrame#action_bar {{
                background-color: {c['action_bg']};
                border-top: 1px solid {c['border']};
            }}
            QFrame#footer_bar {{
                background-color: {c['action_bg']};
            }}

            /* ── Session buttons ── */
            QPushButton#btn_login {{
                background-color: {c['accent']};
                color: white;
                border: none;
                padding: 6px 16px;
                min-height: 30px;
                border-radius: 8px;
                font-weight: 600;
            }}
            QPushButton#btn_login:hover {{
                background-color: {c['accent_hover']};
            }}
            QPushButton#btn_login:pressed {{
                background-color: {c['accent_press']};
            }}
            QPushButton#btn_logout {{
                background-color: transparent;
                color: {c['error']};
                border: 1.5px solid {c['error']};
                padding: 6px 16px;
                min-height: 30px;
                border-radius: 8px;
                font-weight: 600;
            }}
            QPushButton#btn_logout:hover {{
                background-color: {c['error']};
                color: white;
                border-color: {c['error']};
            }}

            /* ── Process action buttons ── */
            QPushButton#btn_iniciar {{
                background-color: {c['success']};
                color: white;
                border: none;
                font-size: 10pt;
                font-weight: 700;
                padding: 8px 12px;
                border-radius: 10px;
            }}
            QPushButton#btn_iniciar:hover {{
                background-color: {c['success']};
                border: 2px solid {c['success']};
                color: white;
            }}
            QPushButton#btn_iniciar:pressed {{
                background-color: {c['success_bg']};
                color: {c['success']};
                border: 2px solid {c['success']};
            }}
            QPushButton#btn_pausar {{
                background-color: {c['warning']};
                color: white;
                border: none;
                font-size: 10pt;
                font-weight: 700;
                padding: 8px 12px;
                border-radius: 10px;
            }}
            QPushButton#btn_pausar:hover {{
                background-color: {c['warning']};
                border: 2px solid {c['warning']};
            }}
            QPushButton#btn_cancelar {{
                background-color: {c['error']};
                color: white;
                border: none;
                font-size: 10pt;
                font-weight: 700;
                padding: 8px 12px;
                border-radius: 10px;
            }}
            QPushButton#btn_cancelar:hover {{
                background-color: {c['error']};
                border: 2px solid {c['error']};
            }}

            /* ── Tool buttons ── */
            QPushButton#btn_historial {{
                color: {c['accent']};
                border-color: {c['accent']};
            }}
            QPushButton#btn_historial:hover {{
                background-color: {c['accent_light']};
                border-color: {c['accent']};
            }}
            QPushButton#btn_reprocesar {{
                color: {c['success']};
                border-color: {c['success']};
            }}
            QPushButton#btn_reprocesar:hover {{
                background-color: {c['success_bg']};
                border-color: {c['success']};
                color: {c['success']};
            }}
            QPushButton#btn_errores {{
                color: {c['error']};
                border-color: {c['error']};
            }}
            QPushButton#btn_errores:hover {{
                background-color: {c['error_bg']};
                border-color: {c['error']};
                color: {c['error']};
            }}
            QPushButton#btn_descargar_log {{
                color: {c['purple']};
                border-color: {c['purple']};
            }}
            QPushButton#btn_descargar_log:hover {{
                background-color: rgba(175,82,222,0.1);
                border-color: {c['purple']};
                color: {c['purple']};
            }}
            QPushButton#btn_config {{
                color: {c['text2']};
            }}
            QPushButton#btn_config:hover {{
                color: {c['text']};
                border-color: {c['border_strong']};
            }}

            /* ── Excel button ── */
            QPushButton#btn_cargar_excel {{
                background-color: {c['warning']};
                color: white;
                border: none;
                font-weight: 700;
                border-radius: 10px;
            }}
            QPushButton#btn_cargar_excel:hover {{
                border: 2px solid {c['warning']};
                background-color: {c['warning']};
            }}
            QPushButton#btn_cargar_excel:pressed {{
                background-color: {c['warning_bg']};
                color: {c['warning']};
                border: 2px solid {c['warning']};
            }}

            /* ── Área de guías pegadas ── */
            QTextEdit#txt_guias_pegar {{
                background-color: {c['input_bg']};
                color: {c['text']};
                border: 1.5px solid {c['border']};
                border-radius: 10px;
                padding: 8px 10px;
                font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
                font-size: 9.5pt;
            }}
            QTextEdit#txt_guias_pegar:focus {{
                border: 2px solid {c['accent']};
            }}
            QTextEdit#txt_guias_pegar:disabled {{
                background-color: {c['dis_bg']};
                color: {c['dis_fg']};
            }}
            QLabel#lbl_guias_pegadas {{
                color: {c['text3']};
                font-size: 10pt;
            }}

            /* ── Drag & Drop hint ── */
            QLabel#lbl_drag_hint {{
                color: {c['text3']};
                font-size: 8.5pt;
                padding: 4px 8px;
                border: 1.5px dashed {c['border']};
                border-radius: 8px;
                background-color: {c['surface2']};
            }}

            /* ── Panel Excel personalizado (reemplaza QGroupBox) ── */
            QFrame#excel_panel_container {{
                background-color: {c['group_bg']};
                border: 1.5px solid {c['group_border']};
                border-bottom: 2px solid {c['border_strong']};
                border-radius: 14px;
            }}
            QWidget#excel_panel_titlebar {{
                background-color: transparent;
                border-bottom: 1px solid {c['border']};
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }}
            QLabel#excel_panel_title {{
                color: {c['group_title']};
                font-size: 9pt;
                font-weight: 700;
                letter-spacing: 0.3px;
                background: transparent;
            }}
            QWidget#excel_panel_content {{
                background-color: transparent;
            }}

            /* ── Botón quitar excel ── */
            QPushButton#btn_quitar_excel {{
                background-color: transparent;
                color: {c['error']};
                border: 1px solid {c['error']};
                border-radius: 5px;
                font-weight: 700;
                font-size: 9pt;
                padding: 0px;
                min-height: 0px;
            }}
            QPushButton#btn_quitar_excel:hover {{
                background-color: {c['error_bg']};
            }}
            QPushButton#btn_quitar_excel:disabled {{
                color: {c['border']};
                border-color: {c['border']};
            }}

            /* ── placeholder ── */
            QPushButton#_unused {{
                background-color: transparent;
                border: 1px solid {c['accent']};
                border-radius: 6px;
                color: {c['accent']};
                font-size: 14px;
                padding: 0px;
            }}

            /* ── Toggle tema ── */
            QPushButton#btn_theme {{
                background-color: transparent;
                border: 1px solid {c['border']};
                border-radius: 10px;
                font-size: 16pt;
                padding: 0px;
                min-height: 0px;
            }}
            QPushButton#btn_theme:hover {{
                background-color: {c['surface2']};
            }}

            /* ── Filtros log ── */
            QPushButton[objectName^="log_filter_"] {{
                background-color: transparent;
                border: 1px solid {c['border']};
                border-radius: 8px;
                font-size: 8.5pt;
                font-weight: 600;
                padding: 2px 10px;
                min-height: 0px;
                color: {c['text3']};
            }}
            QPushButton[objectName^="log_filter_"]:checked {{
                background-color: {c['accent']};
                border-color: {c['accent']};
                color: white;
            }}
            QPushButton[objectName^="log_filter_"]:hover:!checked {{
                background-color: {c['surface2']};
                color: {c['text']};
            }}

            /* ── Botones pequeños del log ── */
            QPushButton#log_btn_small {{
                background-color: transparent;
                border: 1px solid {c['border']};
                border-radius: 7px;
                font-size: 11pt;
                padding: 0px;
                min-height: 0px;
            }}
            QPushButton#log_btn_small:hover {{
                background-color: {c['error_bg']};
                border-color: {c['error']};
            }}
            QPushButton#log_btn_scroll {{
                background-color: transparent;
                border: 1px solid {c['border']};
                border-radius: 8px;
                font-size: 8.5pt;
                font-weight: 600;
                padding: 2px 8px;
                min-height: 0px;
                color: {c['text3']};
            }}
            QPushButton#log_btn_scroll:checked {{
                background-color: {c['success_bg']};
                border-color: {c['success']};
                color: {c['success']};
            }}
            QPushButton#log_btn_scroll:hover:!checked {{
                background-color: {c['surface2']};
                color: {c['text']};
            }}
        """)
        
    def abrir_login(self):
        settings = SettingsManager.get_instance()
        login = LoginWindow(self)

        # Pre-rellenar si hay credenciales guardadas
        if settings.get("recordar_usuario"):
            usuario_guardado = settings.get("usuario_guardado", "")
            login.usuario_input.setText(usuario_guardado)
            login.recordar_check.setChecked(True)
            if _KEYRING_OK and usuario_guardado:
                try:
                    pwd = keyring.get_password("alertran_sgd", usuario_guardado)
                    if pwd:
                        login.password_input.setText(pwd)
                except Exception:
                    pass

        if login.exec() == QDialog.DialogCode.Accepted:
            usuario, password = login.get_credentials()
            if usuario and password:
                self.usuario_actual = usuario
                self.password_actual = password
                self.sesion_activa = True
                self.actualizar_estado_sesion()
                self.log(f"✅ Sesión iniciada: {usuario}")
                self.habilitar_controles(True)

                # Guardar credenciales si el checkbox está activo
                if login.recordar_check.isChecked():
                    settings.set("recordar_usuario", True)
                    settings.set("usuario_guardado", usuario)
                    settings.save()
                    if _KEYRING_OK:
                        try:
                            keyring.set_password("alertran_sgd", usuario, password)
                        except Exception:
                            pass
                else:
                    settings.set("recordar_usuario", False)
                    settings.set("usuario_guardado", "")
                    settings.save()

    def cerrar_sesion(self):
        reply = QMessageBox.question(
            self, "Cerrar Sesión", 
            f"¿Cerrar sesión de {self.usuario_actual}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.sesion_activa = False
            self.usuario_actual = ""
            self.password_actual = ""
            self.actualizar_estado_sesion()
            self.log("🔒 Sesión cerrada")
            self.habilitar_controles(False)
            self.historial_datos.clear()

    def actualizar_estado_sesion(self):
        c = theme.colors()
        if self.sesion_activa:
            self.lbl_estado_sesion.setText(f"✅  {self.usuario_actual}")
            self.lbl_estado_sesion.setStyleSheet(
                f"QLabel {{ background-color: {c['success_bg']}; color: {c['success']};"
                f" font-weight: 600; padding: 5px 16px; border-radius: 12px;"
                f" border: 1px solid {c['success']}; font-size: 10pt; }}"
            )
            self.btn_login.setEnabled(False)
            self.btn_logout.setEnabled(True)
        else:
            self.lbl_estado_sesion.setText("⛔  Sesión no iniciada")
            self.lbl_estado_sesion.setStyleSheet(
                f"QLabel {{ background-color: {c['error_bg']}; color: {c['error']};"
                f" font-weight: 600; padding: 5px 16px; border-radius: 12px;"
                f" border: 1px solid {c['error']}; font-size: 10pt; }}"
            )
            self.btn_login.setEnabled(True)
            self.btn_logout.setEnabled(False)

    def _on_tab_changed(self, index):
        """Muestra/oculta el panel de Excel según la pestaña activa."""
        # Tab 0 = Desviaciones (Excel obligatorio), Tab 1 = Viajes (sin Excel)
        self.panel_excel.setVisible(index == 0)
        # Al ir a Viajes limpiar el adjunto — no se usa en ese modo
        if index == 1 and self.excel_path:
            self.log("ℹ️ Archivo Excel removido automáticamente (pestaña Viajes no lo requiere)")
            self._quitar_excel()

    def _on_guias_text_changed(self):
        """Reinicia el debounce al cambiar el texto — evita procesar en cada keypress."""
        self._debounce_guias.start()

    def _procesar_guias_pegadas(self):
        """Parsea el texto pegado y actualiza el conteo de guías (llamado tras debounce)."""
        texto = self.txt_guias_pegar.toPlainText()
        lineas = [l.strip() for l in texto.splitlines() if l.strip()]
        self.guias_pegadas = lineas
        n = len(lineas)
        c = theme.colors()
        if n > 0:
            color = c['success'] if n < 50 else (c['warning'] if n < 100 else c['error'])
            self.lbl_guias_pegadas.setText(f"📋  {n} guías")
            self.lbl_guias_pegadas.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 10pt;")
            self.btn_quitar_excel.setEnabled(True)
        else:
            self.guias_pegadas = []
            self.lbl_guias_pegadas.setText("📋  0 guías")
            self.lbl_guias_pegadas.setStyleSheet(f"color: {c['text3']}; font-size: 10pt;")
            if not self.excel_path:
                self.btn_quitar_excel.setEnabled(False)

    def _quitar_excel(self):
        """Quita el archivo Excel y las guías pegadas manualmente."""
        self.excel_path = None
        self.guias_pegadas = []
        self.total_guias = 0
        self.btn_cargar_excel.setText("📂 CARGAR EXCEL")
        self.lbl_archivo.setText("❌  Sin archivo")
        self.lbl_archivo.setStyleSheet("color: #ff453a; font-style: italic; font-size: 10pt;")
        self.lbl_archivo.setToolTip("❌  Sin archivo")
        self.btn_quitar_excel.setEnabled(False)
        # Limpiar el área de texto sin disparar la señal (evita loop)
        self.txt_guias_pegar.blockSignals(True)
        self.txt_guias_pegar.clear()
        self.txt_guias_pegar.blockSignals(False)
        self.lbl_guias_pegadas.setText("📋  0 guías")
        c = theme.colors()
        self.lbl_guias_pegadas.setStyleSheet(f"color: {c['text3']}; font-size: 10pt;")
        self.log("🗑️ Adjunto y guías pegadas eliminados")

    def habilitar_controles(self, habilitar):
        self.btn_cargar_excel.setEnabled(habilitar)
        self.txt_guias_pegar.setEnabled(habilitar)
        self.btn_iniciar.setEnabled(habilitar)
        # btn_probar siempre habilitado — mide ping sin necesidad de sesión
        if not habilitar:
            self._reset_btn_probar()
        if not habilitar:
            self.excel_path = None
            self.guias_pegadas = []
            self.total_guias = 0
            self.lbl_archivo.setText("❌  Sin archivo")
            self.lbl_archivo.setStyleSheet("color: #ff453a; font-style: italic;")
            self.lbl_archivo.setToolTip("❌  Sin archivo")
            self.btn_quitar_excel.setEnabled(False)
            self.txt_guias_pegar.blockSignals(True)
            self.txt_guias_pegar.clear()
            self.txt_guias_pegar.blockSignals(False)
            self.lbl_guias_pegadas.setText("📋  0 guías")
            self.progress_bar.setValue(0)
            self.lbl_estado.setText("💤  Listo")
            self.lbl_tiempo_restante.setText("")

    # ── Drag & Drop ───────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent):
        """Acepta archivos .xlsx arrastrados sobre la ventana"""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().lower().endswith('.xlsx'):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Carga el primer .xlsx soltado sobre la ventana"""
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local.lower().endswith('.xlsx'):
                self._cargar_excel_desde_ruta(local)
                event.acceptProposedAction()
                return
        event.ignore()

    def cargar_excel(self):
        archivo, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Excel", str(Path.home()), "Excel (*.xlsx)"
        )
        if archivo:
            self._cargar_excel_desde_ruta(archivo)

    def _cargar_excel_desde_ruta(self, archivo: str):
        """Valida y carga un archivo .xlsx (desde botón o Drag & Drop)"""
        if not self.sesion_activa:
            self.log("⚠️ Inicia sesión antes de cargar un archivo")
            return
        try:
            guias_count = len(FileUtils.leer_guias_excel(Path(archivo)))
            if guias_count == 0:
                QMessageBox.warning(self, "⚠️ Sin guías", "El archivo no contiene guías válidas.")
                return

             #Mostrar vista previa antes de aceptar
            from ui.widgets.excel_preview_dialog import ExcelPreviewDialog
            preview = ExcelPreviewDialog(archivo, guias_count, self)
            if preview.exec() != QDialog.DialogCode.Accepted:
                return

            self._set_excel_file(archivo, guias_count)
            self.log(f"✅ Archivo cargado: {Path(archivo).name} — {guias_count} guías")

        except Exception as e:
            self.lbl_archivo.setText("📄  Error al leer el archivo")
            self.lbl_archivo.setStyleSheet("color: #ff453a; font-weight: bold;")
            self.lbl_archivo.setToolTip("📄  Error al leer el archivo")
            self.log(f"⚠️ Error al leer el archivo: {str(e)}")

    def _set_excel_file(self, ruta: str, guias_count: int = None):
        """Establece el archivo Excel activo (usado en cargar y reprocesar)."""
        self.excel_path = ruta
        nombre = Path(ruta).name
        if guias_count is None:
            try:
                guias_count = len(FileUtils.leer_guias_excel(Path(ruta)))
            except Exception:
                guias_count = 0
        self.total_guias = guias_count
        texto_completo = f"📄  {nombre}  ({guias_count} guías)"
        self.lbl_archivo.setText(self._elide_archivo(texto_completo))
        self.lbl_archivo.setStyleSheet("color: #32d74b; font-weight: bold; font-size: 10pt;")
        self.lbl_archivo.setToolTip(str(self.excel_path) if self.excel_path else nombre)
        self.btn_quitar_excel.setEnabled(True)
        self.btn_cargar_excel.setText(f"📂 {guias_count} GUÍAS")

    @staticmethod
    def _level_from_msg(mensaje: str) -> str:
        if "❌" in mensaje or "ERROR" in mensaje or "🔴" in mensaje:
            return 'error'
        if "⚠️" in mensaje or "ADVERTENCIA" in mensaje:
            return 'warning'
        if "✅" in mensaje or "🎉" in mensaje:
            return 'success'
        return 'info'

    def log(self, mensaje):
        from utils import theme as _theme
        c = _theme.colors()
        dark = _theme.is_dark()

        ts = datetime.now().strftime("%H:%M:%S")
        level = self._level_from_msg(mensaje)

        # Semantic colors
        if level == 'error':
            color = c['error']
        elif level == 'warning':
            color = c['warning'] if dark else "#c04000"
        elif level == 'success':
            color = c['success'] if dark else "#248a3d"
        elif "📦" in mensaje or "ENT" in mensaje:
            color = c['warning'] if dark else "#9a5800"
        elif "🔐" in mensaje or "🧭" in mensaje or "▶️" in mensaje:
            color = c['accent']
        elif "🛑" in mensaje or "⏸" in mensaje:
            color = "#e67e22" if dark else "#c04000"
        elif "🚀" in mensaje or "🌐" in mensaje:
            color = c['purple']
        else:
            color = c['log_fg']

        ts_color = c['text2'] if dark else "#8e8e93"
        safe = mensaje.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = (
            f'<span style="color:{ts_color}">[{ts}]</span> '
            f'<span style="color:{color}">{safe}</span>'
        )

        # Almacenar para filtrado
        self._log_entries.append((html, level))

        # Solo mostrar si coincide con el filtro activo
        if self._log_filter == 'all' or self._log_filter == level:
            self.log_text.append(html)
            if self._log_auto_scroll:
                cursor = self.log_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.log_text.setTextCursor(cursor)

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _limpiar_log(self):
        self.log_text.clear()
        self._log_entries.clear()

    def _set_log_filter(self, level: str):
        self._log_filter = level
        # Actualizar estado visual de los botones
        for btn, lvl in (
            (self._btn_filter_all,   'all'),
            (self._btn_filter_ok,    'success'),
            (self._btn_filter_warn,  'warning'),
            (self._btn_filter_error, 'error'),
        ):
            btn.setChecked(lvl == level)
        self._rebuild_log()

    def _rebuild_log(self):
        """Reconstruye el log_text aplicando el filtro activo."""
        self.log_text.clear()
        for html, lvl in self._log_entries:
            if self._log_filter == 'all' or self._log_filter == lvl:
                self.log_text.append(html)
        if self._log_auto_scroll:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_text.setTextCursor(cursor)

    def _toggle_log_scroll(self):
        self._log_auto_scroll = self.btn_log_scroll.isChecked()
        self.btn_log_scroll.setText("↓ Auto" if self._log_auto_scroll else "⏸ Fijo")
        if self._log_auto_scroll:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_text.setTextCursor(cursor)

    def _on_log_scroll_changed(self, value: int):
        """Si el usuario sube manualmente en el scroll, pausa el auto-scroll."""
        sb = self.log_text.verticalScrollBar()
        at_bottom = (value >= sb.maximum() - 4)
        if not at_bottom and self._log_auto_scroll:
            # Solo desactivar si fue un movimiento del usuario (no nuestro append)
            self._log_auto_scroll = False
            self.btn_log_scroll.setChecked(False)
            self.btn_log_scroll.setText("⏸ Fijo")
        elif at_bottom and not self._log_auto_scroll:
            self._log_auto_scroll = True
            self.btn_log_scroll.setChecked(True)
            self.btn_log_scroll.setText("↓ Auto")

    # ── Sincronización campos globales ────────────────────────────────────────

    def _sync_global_fields(self):
        """Deshabilita los campos globales cuando todos los viajes tienen config propia."""
        all_custom = self.viaje_queue.all_have_custom()
        self.ciudad_combo_desv.setEnabled(not all_custom)
        self.tipo_desviacion_combo.setEnabled(not all_custom)
        self.observaciones_input.setEnabled(not all_custom)
        # Hint visual en las observaciones
        if all_custom:
            self.observaciones_input.setPlaceholderText(
                "Todos los viajes tienen configuración propia — campo global desactivado")
        else:
            self.observaciones_input.setPlaceholderText(
                "Ingrese las observaciones para la desviación...")

    # ── Resumen de cola ───────────────────────────────────────────────────────

    def _mostrar_resumen_cola(self):
        """Popup no-modal con estado en tiempo real de la cola de viajes."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QWidget, QScrollArea
        from PySide6.QtCore import QTimer
        from PySide6.QtGui import QFont as _QFont
        c = theme.colors()

        dlg = QDialog(self)
        dlg.setWindowTitle("🎫 Cola de viajes")
        dlg.setMinimumWidth(430)
        dlg.setModal(False)
        dlg.setSizeGripEnabled(True)
        dlg.setStyleSheet(f"""
            QDialog {{ background: {c['bg']}; }}
            QLabel  {{ color: {c['text']}; background: transparent; border: none; }}
            QScrollArea {{ border: none; background: transparent; }}
        """)

        root = QVBoxLayout(dlg)
        root.setSpacing(6)
        root.setContentsMargins(16, 16, 16, 16)

        # ── Helper fila de config ─────────────────────────────────────────
        def _fila_cfg(icon, label, value, value_color=None):
            row = QWidget()
            row.setStyleSheet(f"QWidget {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 8px; }}")
            hl = QHBoxLayout(row)
            hl.setContentsMargins(10, 6, 10, 6)
            hl.setSpacing(8)
            li = QLabel(icon); li.setFixedWidth(18)
            li.setStyleSheet(f"font-size: 11pt; color: {c['text3']};")
            hl.addWidget(li)
            lk = QLabel(label)
            lk.setStyleSheet(f"color: {c['text3']}; font-size: 9pt;")
            lk.setFixedWidth(110)
            hl.addWidget(lk)
            lv = QLabel(str(value) if value else "—")
            lv.setStyleSheet(f"color: {value_color or c['text']}; font-weight: 600; font-size: 10pt;")
            lv.setWordWrap(True)
            hl.addWidget(lv, stretch=1)
            return row

        # ── Config global ─────────────────────────────────────────────────
        usuario   = getattr(self, 'usuario_actual', '') or ''
        regional  = self.ciudad_combo_desv.currentText()   if hasattr(self, 'ciudad_combo_desv')       else ''
        tipo_desv = self.tipo_desviacion_combo.currentText() if hasattr(self, 'tipo_desviacion_combo') else ''
        obs       = self.observaciones_input.toPlainText().strip() if hasattr(self, 'observaciones_input') else ''

        root.addWidget(_fila_cfg("👤", "Usuario",         usuario))
        root.addWidget(_fila_cfg("📍", "Regional",        regional))
        root.addWidget(_fila_cfg("📌", "Tipo Desviación", tipo_desv))
        root.addWidget(_fila_cfg("📝", "Observaciones",   obs[:60] + ("…" if len(obs) > 60 else "")))

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {c['border']}; max-height: 1px; border: none;")
        root.addWidget(sep)

        # ── Header viajes ─────────────────────────────────────────────────
        hdr = QHBoxLayout(); hdr.setContentsMargins(0, 0, 0, 0)
        lbl_titulo = QLabel("🎫  Viajes en cola")
        lbl_titulo.setStyleSheet(f"color: {c['text2']}; font-size: 9pt; font-weight: 700;")
        hdr.addWidget(lbl_titulo)
        hdr.addStretch()
        lbl_stats = QLabel("")
        lbl_stats.setStyleSheet(f"color: {c['text3']}; font-size: 8pt;")
        hdr.addWidget(lbl_stats)
        root.addLayout(hdr)

        # ── Contenedor dinámico de tarjetas ───────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(280)
        cards_wrap = QWidget()
        cards_wrap.setStyleSheet("background: transparent;")
        cards_layout = QVBoxLayout(cards_wrap)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(4)
        scroll.setWidget(cards_wrap)
        root.addWidget(scroll)

        # ── Botón reintentar fallidos ──────────────────────────────────────
        btn_retry = QPushButton("🔄  Reintentar fallidos")
        btn_retry.setFixedHeight(32)
        btn_retry.setVisible(False)
        btn_retry.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,149,0,0.15); color: #ff9500;
                border: 1px solid rgba(255,149,0,0.45); border-radius: 8px;
                font-size: 9pt; font-weight: 700;
            }}
            QPushButton:hover {{ background: rgba(255,149,0,0.30); }}
        """)
        root.addWidget(btn_retry)

        # ── Botón cerrar ──────────────────────────────────────────────────
        btn_cerrar = QPushButton("Cerrar")
        btn_cerrar.setFixedHeight(32)
        btn_cerrar.clicked.connect(dlg.accept)
        btn_cerrar.setStyleSheet(f"""
            QPushButton {{
                background: {c['surface2']}; color: {c['text']};
                border: 1px solid {c['border']}; border-radius: 8px;
                font-size: 9pt; font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {c['accent']}; color: {c['accent']}; }}
        """)
        root.addWidget(btn_cerrar)

        # ── Badges de estado ──────────────────────────────────────────────
        _BADGE = {
            'pending':    ('⏳', '#8a8a9a', 'rgba(90,90,114,0.12)',   'rgba(90,90,114,0.35)',  'Pendiente'),
            'processing': ('🔄', '#4da6ff', 'rgba(77,166,255,0.12)',  'rgba(77,166,255,0.40)', 'Procesando…'),
            'error':      ('❌', '#e05252', 'rgba(224,82,82,0.12)',   'rgba(224,82,82,0.40)',  'Error'),
            'done':       ('✅', '#52c08a', 'rgba(82,192,138,0.12)',  'rgba(82,192,138,0.40)', 'Listo'),
            'cancelled':  ('⚠️', '#ff9500', 'rgba(255,149,0,0.12)',   'rgba(255,149,0,0.40)',  'Cancelado'),
        }

        def _fmt_time(secs):
            m, s = divmod(int(secs), 60)
            h, m = divmod(m, 60)
            return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

        def _refresh():
            # Vaciar layout dinámico
            while cards_layout.count():
                item = cards_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            cards = list(getattr(self.viaje_queue, '_cards', []))
            done_n      = sum(1 for cd in cards if cd.state == 'done')
            error_n     = sum(1 for cd in cards if cd.state == 'error')
            cancelled_n = sum(1 for cd in cards if cd.state == 'cancelled')
            failed_n    = error_n + cancelled_n
            total_n     = len(cards)

            if cards:
                for card in cards:
                    emoji, col, bg, border_col, badge_txt = _BADGE.get(
                        card.state, ('○', c['text3'], 'transparent', c['border'], card.state))

                    row = QWidget()
                    row.setStyleSheet(
                        f"QWidget {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 8px; }}")
                    hl = QHBoxLayout(row)
                    hl.setContentsMargins(10, 7, 10, 7)
                    hl.setSpacing(8)

                    # Badge estado
                    badge = QLabel(f"{emoji}  {badge_txt}")
                    badge.setFixedWidth(112)
                    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    badge.setStyleSheet(
                        f"color: {col}; font-weight: 700; font-size: 8pt;"
                        f"background: {bg}; border: 1px solid {border_col}; border-radius: 6px; padding: 2px 4px;")
                    hl.addWidget(badge)

                    # Número
                    lbl_num = QLabel(card.numero)
                    lbl_num.setStyleSheet(
                        f"color: {c['text']}; font-weight: 600; font-size: 10pt; font-family: Consolas;")
                    hl.addWidget(lbl_num, stretch=1)

                    # Ícono ⚙ con tooltip si tiene config propia (E)
                    cfg = self.viaje_queue.get_viaje_config(card.numero)
                    if cfg and any(cfg.values()):
                        lbl_cfg = QLabel("⚙")
                        lbl_cfg.setFont(_QFont("Segoe UI Symbol", 9))
                        _cc = cfg.get('ciudad') or '(global)'
                        _ct = cfg.get('tipo')   or '(global)'
                        _co = cfg.get('observaciones') or '(global)'
                        lbl_cfg.setToolTip(
                            f"📍 Regional: {_cc}\n"
                            f"📌 Tipo: {_ct}\n"
                            f"📝 Obs: {_co[:60]}")
                        lbl_cfg.setStyleSheet("color: #4da6ff; background: transparent; border: none;")
                        hl.addWidget(lbl_cfg)

                    # Tiempo transcurrido (B)
                    elapsed = getattr(card, '_elapsed_sec', 0)
                    if elapsed > 0:
                        lbl_t = QLabel(_fmt_time(elapsed))
                        lbl_t.setStyleSheet(
                            f"color: {c['text3']}; font-size: 8.5pt; font-family: Consolas;")
                        hl.addWidget(lbl_t)

                    cards_layout.addWidget(row)
            else:
                lbl_empty = QLabel("Sin viajes en cola")
                lbl_empty.setStyleSheet(f"color: {c['text3']}; font-size: 9pt; padding: 8px 4px;")
                cards_layout.addWidget(lbl_empty)

            # Stats header
            if total_n > 0:
                parts = [f"{done_n}/{total_n} listos"]
                if error_n:     parts.append(f"{error_n} error(es)")
                if cancelled_n: parts.append(f"{cancelled_n} cancelado(s)")
                lbl_stats.setText("  ·  ".join(parts))

            # Botón reintentar (F)
            btn_retry.setVisible(failed_n > 0)

        def _do_retry():
            self.viaje_queue.retry_all_failed()
            _refresh()

        btn_retry.clicked.connect(_do_retry)

        _refresh()
        dlg.adjustSize()

        # ── Timer tiempo real (D) ─────────────────────────────────────────
        timer = QTimer(dlg)
        timer.setInterval(1000)
        timer.timeout.connect(_refresh)
        timer.start()
        dlg.finished.connect(timer.stop)

        dlg.move(
            self.x() + (self.width()  - dlg.width())  // 2,
            self.y() + (self.height() - dlg.height()) // 2,
        )
        dlg.exec()

    # ── Tema ──────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        theme.toggle()
        self._setup_styles()
        # Actualizar icono del botón
        self.btn_theme.setText("🌙" if theme.is_dark() else "☀️")
        # Actualizar el log_text inline style
        _c = theme.colors()
        self.log_text.setStyleSheet(
            f"QTextEdit {{ background-color: {_c['log_bg']};"
            f" font-family: 'SF Mono', 'Consolas', 'Courier New', monospace;"
            f" font-size: 9.5pt; border: 1px solid {_c['border']};"
            f" border-radius: 10px; color: {_c['log_fg']}; padding: 10px; }}"
        )
        apply_blur(self, dark=theme.is_dark())
        # Notificar a todos los widgets registrados para que actualicen estilos inline
        theme.signals.changed.emit()

    # ── Modo headless ─────────────────────────────────────────────────────────

    def _toggle_headless(self):
        self._headless = not self._headless
        SettingsManager.get_instance().set("headless_mode", self._headless)
        _c = theme.colors()
        if self._headless:
            self.btn_headless.set_colors(
                normal_color=_c['btn_tool_bg'], hover_color=_c['warning'],
                text_color=_c['warning'], hover_text="#ffffff"
            )
            self.btn_headless.setText("🔒  Oculto")
            self.log("🔒 Modo oculto activado — el navegador correrá en segundo plano")
        else:
            self.btn_headless.set_colors(
                normal_color=_c['btn_tool_bg'], hover_color=_c['success'],
                text_color=_c['success'], hover_text="#ffffff"
            )
            self.btn_headless.setText("👀  Visible")
            self.log("👀 Modo visible activado — el navegador se abrirá en pantalla")

    # ── Ampliaciones recientes ────────────────────────────────────────────────

    def _guardar_ampliacion(self):
        texto = self.ampliacion_input.currentText().strip()
        if not texto:
            return
        settings = SettingsManager.get_instance()
        recientes = settings.get("ampliaciones_recientes", [])
        if texto in recientes:
            recientes.remove(texto)
        recientes.insert(0, texto)
        recientes = recientes[:5]
        settings.set("ampliaciones_recientes", recientes)
        # Sincronizar el combo sin disparar eventos
        self.ampliacion_input.blockSignals(True)
        self.ampliacion_input.clear()
        self.ampliacion_input.addItems(recientes)
        self.ampliacion_input.setCurrentText(texto)
        self.ampliacion_input.blockSignals(False)

    # ── Atajos de teclado ─────────────────────────────────────────────────────

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(
            lambda: self.iniciar_proceso() if self.btn_iniciar.isEnabled() else None
        )
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self._limpiar_log)
        QShortcut(QKeySequence("Escape"), self).activated.connect(
            lambda: self.cancelar_proceso() if self.btn_cancelar.isEnabled() else None
        )

    def descargar_log(self):
        try:
            contenido_log = self.log_text.toPlainText()
            ruta = FileUtils.guardar_log(contenido_log, self.carpeta_descargas)
            
            QMessageBox.information(
                self, "✅ Éxito", 
                f"📄 Log guardado en:\n{ruta}\n\n📁 Carpeta: Descargas"
            )
            
            self.log(f"✅ Log guardado en: {ruta}")
            
        except Exception as e:
            QMessageBox.critical(self, "❌ Error", f"No se pudo guardar el log:\n{str(e)}")

    def ver_historial(self):
        if not self.historial_window:
            self.historial_window = HistorialWindow(self)
            self.historial_window.reprocesar_guia.connect(self._reprocesar_guia_individual)

        tipo_activo = (
            self.tipo_combo.currentText() if self.tab_widget.currentIndex() == 0
            else self.tipo_desviacion_combo.currentText()
        )
        self.historial_window.actualizar_historial(self.historial_datos, tipo_activo)
        self.historial_window.set_total_esperado(self.total_guias)
        self.historial_window.show()

    def _reprocesar_guia_individual(self, guia: str):
        """Reprocesa una sola guía con la configuración actual."""
        if not self.sesion_activa:
            QMessageBox.warning(self, "⚠️ Sin sesión",
                                "Inicia sesión antes de reprocesar una guía.")
            return
        if not self.ampliacion_input.currentText().strip():
            QMessageBox.warning(self, "⚠️ Ampliación vacía",
                                "Completa el campo Ampliación antes de reprocesar.")
            return
        if self.proceso_thread and self.proceso_thread.isRunning():
            QMessageBox.warning(self, "⚠️ Proceso activo",
                                "Espera a que el proceso actual finalice.")
            return

        resp = QMessageBox.question(
            self, "🔄 Reprocesar guía",
            f"¿Reprocesar la guía <b>{guia}</b> con la configuración actual?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if resp != QMessageBox.StandardButton.Yes:
            return

        self.log(f"🔄 Reprocesando guía individual: {guia}")
        self.tiempo_inicio = datetime.now()
        self.guias_ent = []
        self.guias_error_count = 0
        self.guias_advertencia_count = 0
        self.desviaciones_creadas = 0
        self.guias_duplicadas_count = 0
        self.total_guias = 1

        self.btn_iniciar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        self.btn_cargar_excel.setEnabled(False)
        self.btn_quitar_excel.setEnabled(False)
        self.btn_login.setEnabled(False)
        self.btn_logout.setEnabled(False)
        self.tab_widget.setEnabled(False)
        self.progress_bar.setValue(0)

        self.proceso_thread = ProcesoThread(
            self.usuario_actual,
            self.password_actual,
            self.ciudad_combo.currentText(),
            self.tipo_combo.currentText(),
            self.ampliacion_input.currentText(),
            None,
            1,
            guias_list=[guia],
            headless=self._headless
        )
        self.proceso_thread.senales.log.connect(self.log)
        self.proceso_thread.senales.progreso.connect(self.progress_bar.setValue)
        self.proceso_thread.senales.estado.connect(self.lbl_estado.setText)
        self.proceso_thread.senales.guia_procesada.connect(self.agregar_al_historial)
        self.proceso_thread.senales.finalizado.connect(self.proceso_finalizado)
        self.proceso_thread.senales.proceso_cancelado.connect(self.proceso_cancelado)
        self.proceso_thread.senales.archivo_errores.connect(self.archivo_errores_generado)
        self.proceso_thread.senales.tiempo_restante.connect(self.actualizar_tiempo_restante)
        self.proceso_thread.senales.error.connect(self.mostrar_error)
        self.proceso_thread.start()

    def agregar_al_historial(self, guia, estado, resultado, navegador, fecha):
        self.historial_datos.append((guia, estado, resultado, navegador, fecha))
        # Reiniciar el cronómetro del historial en la primera guía procesada
        if len(self.historial_datos) == 1 and self.historial_window:
            self.historial_window.tiempo_inicio = datetime.now()
        if self.historial_window and self.historial_window.isVisible():
            self.historial_window.set_total_esperado(self.total_guias)

        if "📦" in estado:
            self.guias_ent.append(guia)
        elif "❌" in estado:
            self.guias_error_count += 1
        elif "⚠️" in estado:
            self.guias_advertencia_count += 1
        elif "✅" in estado:
            self.desviaciones_creadas += 1

    def actualizar_tiempo_restante(self, tiempo):
        self.lbl_tiempo_restante.setText(tiempo)

    def _sync_taskbar_progress(self, value: int):
        """Sincroniza el ícono de la barra de tareas con el progress bar.
        En modo cola, mapea el valor al segmento global del viaje actual."""
        if not hasattr(self, '_taskbar'):
            return
        if value <= 0:
            self._taskbar.clear()
            return
        if value >= 100:
            self._taskbar.set_value(100)
            return
        if getattr(self, '_total_viajes_cola', 1) > 1:
            total = self._total_viajes_cola
            idx   = getattr(self, '_viaje_actual_idx', 0)
            seg   = 100.0 / total
            global_val = int(idx * seg + value * seg / 100.0)
            self._taskbar.set_value(max(1, min(global_val, 99)))
        else:
            self._taskbar.set_value(value)

    def _tick_tiempo_transcurrido(self):
        if self.tiempo_inicio:
            _secs = int((datetime.now() - self.tiempo_inicio).total_seconds())
            _h, _rem = divmod(_secs, 3600)
            _m, _s = divmod(_rem, 60)
            if _h:
                txt = f"⏱ {_h:02d}:{_m:02d}:{_s:02d}"
            else:
                txt = f"⏱ {_m:02d}:{_s:02d}"
            self.lbl_tiempo_transcurrido.setText(txt)

    def _set_duplicadas(self, count):
        self.guias_duplicadas_count = count
        # Ajustar el total al conteo único para sincronizar barra de historial
        self.total_guias = max(self.total_guias - count, 0)
        if self.historial_window:
            self.historial_window.set_total_esperado(self.total_guias)

    @staticmethod
    def _formatear_tiempo(td) -> str:
        """Convierte un timedelta a formato legible: '1h 23m 45s'"""
        total = int(td.total_seconds())
        h, rem = divmod(total, 3600)
        m, s   = divmod(rem, 60)
        if h > 0:
            return f"{h}h {m:02d}m {s:02d}s"
        elif m > 0:
            return f"{m}m {s:02d}s"
        else:
            return f"{s}s"

    def mostrar_resumen(self):
        tiempo_total = datetime.now() - self.tiempo_inicio if self.tiempo_inicio else timedelta(0)
        tiempo_formateado = self._formatear_tiempo(tiempo_total)

        tab_idx = self.tab_widget.currentIndex() if hasattr(self, 'tab_widget') else 0

        if tab_idx == 1 and self.proceso_thread is not None:
            # ── Resumen especializado para Desviación de Viajes ──────────
            hilo = self.proceso_thread
            resumen = ResumenViajeWindow(
                numero_viaje=getattr(hilo, 'numero_viaje', '—'),
                tipo_incidencia=getattr(hilo, 'codigo_desviacion', '—'),
                observaciones=getattr(hilo, 'observaciones', ''),
                ciudad=getattr(hilo, 'ciudad', ''),
                procesado=self.desviaciones_creadas > 0,
                cancelado=getattr(hilo, 'cancelado', False),
                tiempo_total=tiempo_formateado,
                usuario=self.usuario_actual,
                paginas_procesadas=getattr(hilo, 'paginas_procesadas', 0),
                total_paginas=getattr(hilo, 'total_paginas', 0),
                parent=self
            )
        else:
            # ── Resumen genérico para Desviaciones (Excel) ───────────────
            resumen = ResumenWindow(
                total_guias=self.total_guias,
                desviadas=self.desviaciones_creadas,
                entregadas=len(self.guias_ent),
                errores=self.guias_error_count,
                advertencias=self.guias_advertencia_count,
                duplicadas=self.guias_duplicadas_count,
                tiempo_total=tiempo_formateado,
                usuario=self.usuario_actual,
                tipo_proceso="Desviaciones",
                desviacion=self.tipo_combo.currentText(),
                regional=self.ciudad_combo.currentText(),
                ampliacion=self.ampliacion_input.currentText().strip(),
                parent=self
            )
        resumen.exec()

    def iniciar_proceso(self):
        """Inicia el proceso según la pestaña activa"""
        if not self.sesion_activa:
            self._mostrar_error_validacion(ERROR_MESSAGES['NO_SESSION'])
            return
        
        # Determinar qué pestaña está activa
        pestania_actual = self.tab_widget.currentIndex()
        
        if pestania_actual == 0:  # Pestaña de Desviaciones
            self._iniciar_proceso_desviaciones()
        else:  # Pestaña de Desviación de Viajes
            self._iniciar_proceso_viajes()

    def _iniciar_proceso_desviaciones(self):
        """Inicia el proceso de desviaciones — Excel o guías pegadas (al menos uno requerido)"""
        if not self.ampliacion_input.currentText().strip():
            self.ampliacion_input.setStyleSheet("QComboBox { border: 2px solid red; }")
            self._mostrar_error_validacion(ERROR_MESSAGES['NO_AMPLIACION'])
            self.ampliacion_input.setFocus()
            return
        else:
            self.ampliacion_input.setStyleSheet("")

        # Se necesita Excel O guías pegadas
        usar_pegadas = not self.excel_path and bool(self.guias_pegadas)
        if not self.excel_path and not self.guias_pegadas:
            self._mostrar_error_validacion(
                "Carga un archivo Excel o pega las guías en el área de texto."
            )
            return
        if self.excel_path and not Path(self.excel_path).exists():
            self._mostrar_error_validacion(
                f"El archivo Excel ya no existe en el sistema:\n{self.excel_path}\n\n"
                "Vuelve a cargarlo."
            )
            self._quitar_excel()
            return

        # Total a procesar (Excel ya lo tiene; pegadas lo calculamos aquí)
        if usar_pegadas:
            self.total_guias = len(self.guias_pegadas)

        num_nav = self.num_navegadores_spin.value()

        if not self._confirmar_inicio_proceso(num_nav, es_viajes=False):
            return

        self._guardar_ampliacion()
        self.tiempo_inicio = datetime.now()
        self.guias_ent = []
        self.guias_error_count = 0
        self.guias_advertencia_count = 0
        self.desviaciones_creadas = 0
        self.guias_duplicadas_count = 0
        self.lbl_tiempo_transcurrido.setText("⏱ 00:00")
        self._timer_transcurrido.start()

        self.btn_iniciar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        self.btn_cargar_excel.setEnabled(False)
        self.btn_quitar_excel.setEnabled(False)
        self.txt_guias_pegar.setEnabled(False)
        self.btn_errores.setEnabled(False)
        self.btn_login.setEnabled(False)
        self.btn_logout.setEnabled(False)
        self.tab_widget.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_tiempo_restante.setText("⏱️ Iniciando proceso...")
        if hasattr(self, '_taskbar'):
            self._taskbar.indeterminate()
            self._taskbar.set_overlay('processing')
        self.log_text.clear()
        self.historial_datos.clear()

        self.log(f"🚀 Iniciando DESVIACIONES con {num_nav} navegador(es)...")
        self.log(f"👤 Usuario: {self.usuario_actual}")
        if self._headless:
            self.log("═" * 45)
            self.log("🔒  MODO OCULTO ACTIVO — Los navegadores NO son visibles")
            self.log("═" * 45)
        else:
            self.log("👀 Modo visible — Los navegadores son visibles")
        self.log(f"📌 Tipo Incidencia: {self.tipo_combo.currentText()}")
        self.log(f"📝 Ampliación: {self.ampliacion_input.currentText()}")
        if usar_pegadas:
            self.log(f"📋 Fuente: {self.total_guias} guías pegadas manualmente")
        else:
            self.log(f"📊 Total guías a procesar: {self.total_guias}")
        self.log(f"📁 Los archivos se guardarán en: {self.carpeta_descargas}")

        self.proceso_thread = ProcesoThread(
            self.usuario_actual,
            self.password_actual,
            self.ciudad_combo.currentText(),
            self.tipo_combo.currentText(),
            self.ampliacion_input.currentText(),
            self.excel_path,
            num_nav,
            guias_list=self.guias_pegadas if usar_pegadas else None,
            headless=self._headless
        )

        self._conectar_senales_thread()

    def _iniciar_proceso_viajes(self, skip_confirm: bool = False):
        """Inicia el proceso de desviación de viajes - Excel OPCIONAL"""
        # Leer viajes pendientes de la cola visual
        viajes_lista = self.viaje_queue.get_pending_viajes()
        if not viajes_lista:
            self._mostrar_error_validacion("Agregue al menos un número de viaje a la cola")
            self.viaje_queue.focus_input()
            return

        self._cola_viajes        = list(viajes_lista[1:])
        self._total_viajes_cola  = len(viajes_lista)
        self._viaje_actual_idx   = 0
        numero_viaje_actual      = viajes_lista[0]

        # Marcar primera tarjeta como procesando
        self.viaje_queue.hide_retry_banner()
        self.viaje_queue.set_card_state(numero_viaje_actual, 'processing')
        self.viaje_queue.set_controls_enabled(False)

        # Validar observaciones (solo en el primer viaje de la cola)
        if not skip_confirm and not self.viaje_queue.all_have_custom():
            if not self.observaciones_input.toPlainText().strip():
                self.observaciones_input.setStyleSheet("border: 2px solid red;")
                self._mostrar_error_validacion("Debe ingresar observaciones para la desviación")
                self.observaciones_input.setFocus()
                return
            else:
                self.observaciones_input.setStyleSheet("")

        # Confirmación: solo al iniciar manualmente, no entre viajes de la cola
        if not skip_confirm:
            if not self._confirmar_inicio_proceso(1, es_viajes=True):
                # Usuario canceló el diálogo: devolver tarjeta a pending
                self.viaje_queue.set_card_state(numero_viaje_actual, 'pending')
                self.viaje_queue.set_controls_enabled(True)
                return

        self.tiempo_inicio = datetime.now()
        self.guias_ent = []
        self.guias_error_count = 0
        self.guias_advertencia_count = 0
        self.desviaciones_creadas = 0
        self.guias_duplicadas_count = 0
        self.lbl_tiempo_transcurrido.setText("⏱ 00:00")
        self._timer_transcurrido.start()

        self.btn_iniciar.setEnabled(False)
        self.btn_cancelar.setEnabled(True)
        self.btn_cargar_excel.setEnabled(False)
        self.btn_errores.setEnabled(False)
        self.btn_login.setEnabled(False)
        self.btn_logout.setEnabled(False)
        self.tab_widget.setEnabled(False)
        self.progress_bar.setValue(0)
        self.lbl_tiempo_restante.setText("⏱️ Procesando viaje...")
        if hasattr(self, '_taskbar'):
            self._taskbar.indeterminate()
            self._taskbar.set_overlay('processing')
        self.log_text.clear()
        self.historial_datos.clear()

        numero_viaje = numero_viaje_actual
        num_nav = 1

        # Config propia del viaje (sobreescribe global si está definida)
        _vcfg = self.viaje_queue.get_viaje_config(numero_viaje)
        _ciudad_viaje = _vcfg.get('ciudad', '').strip()
        _tipo_viaje   = _vcfg.get('tipo', '').strip()
        _obs_viaje    = _vcfg.get('observaciones', '').strip()

        ciudad_final      = _ciudad_viaje or self.ciudad_combo_desv.currentText()
        codigo_desviacion = _tipo_viaje   or self.tipo_desviacion_combo.currentText()
        observaciones     = _obs_viaje    or self.observaciones_input.toPlainText().strip()

        # Verificar checkpoint (solo en modo viaje único o primer viaje de la cola)
        pagina_inicio = 1
        if not self._cola_viajes or self._viaje_actual_idx == 0:
            _chk_path = Path.home() / ".alertran" / "checkpoint_viaje.json"
            if _chk_path.exists():
                try:
                    import json as _json
                    with open(_chk_path, "r", encoding="utf-8") as _f:
                        _checkpoint = _json.load(_f)
                    _viaje_chk = str(_checkpoint.get("viaje", ""))
                    _pagina_chk = int(_checkpoint.get("pagina_completada", 0))
                    if _viaje_chk == numero_viaje and _pagina_chk > 0:
                        resp = QMessageBox.question(
                            self,
                            "Checkpoint detectado",
                            f"Se encontró un proceso anterior del viaje {numero_viaje} "
                            f"interrumpido en la página {_pagina_chk}.\n\n"
                            f"¿Desea continuar desde la página {_pagina_chk + 1}?",
                            QMessageBox.Yes | QMessageBox.No,
                            QMessageBox.Yes
                        )
                        if resp == QMessageBox.Yes:
                            pagina_inicio = _pagina_chk + 1
                except Exception:
                    pass

        # Log de inicio
        if self._total_viajes_cola > 1:
            self.log(f"🚚 Viaje {self._viaje_actual_idx + 1} de {self._total_viajes_cola}: {numero_viaje}")
        else:
            self.log(f"🚚 Iniciando DESVIACIÓN DE VIAJES con 1 navegador...")
        self.log(f"👤 Usuario: {self.usuario_actual}")
        if self._headless:
            self.log("═" * 45)
            self.log("🔒  MODO OCULTO ACTIVO — Los navegadores NO son visibles")
            self.log("═" * 45)
        self.log(f"🎫 Número de Viaje: {numero_viaje}")
        self.log(f"📌 Tipo Desviación: {codigo_desviacion}")
        self.log(f"📝 Observaciones: {observaciones[:50]}...")
        
        # Mostrar si se cargó o no un Excel
        if self.excel_path:
            self.log(f"📊 Excel cargado: {Path(self.excel_path).name} - {self.total_guias} guías")
        else:
            self.log(f"📊 Sin archivo Excel - Modo manual")
        
        self.log(f"📁 Los archivos se guardarán en: {self.carpeta_descargas}")

        self.proceso_thread = DesviacionViajesThread(
            self.usuario_actual,
            self.password_actual,
            ciudad_final,
            numero_viaje,
            codigo_desviacion,
            observaciones,
            num_nav,
            headless=self._headless,
            pagina_inicio=pagina_inicio,
        )

        self._conectar_senales_thread()
        # Arrancar cronómetro de la tarjeta ahora que el proceso realmente inicia
        self.viaje_queue.start_card_clock(numero_viaje)

    def _conectar_senales_thread(self):
        """Conecta las señales del thread"""
        senales = self.proceso_thread.senales
        senales.progreso.connect(self.progress_bar.setValue)
        senales.estado.connect(self.lbl_estado.setText)
        senales.log.connect(self.log)
        senales.error.connect(self.mostrar_error)
        senales.finalizado.connect(self.proceso_finalizado)
        senales.archivo_errores.connect(self.archivo_errores_generado)
        senales.guia_procesada.connect(self.agregar_al_historial)
        senales.proceso_cancelado.connect(self.proceso_cancelado)
        senales.tiempo_restante.connect(self.actualizar_tiempo_restante)
        senales.duplicadas_detectadas.connect(self._set_duplicadas)
        senales.navegador_inicializado.connect(self._actualizar_progreso_init)

        self.btn_pausar.setEnabled(True)
        self.proceso_thread.start()

    def _actualizar_progreso_init(self, listos, total):
        """Actualiza el estado durante la inicialización de navegadores"""
        self.lbl_estado.setText(f"Inicializando navegadores: {listos}/{total} listos...")

    def _reset_btn_probar(self):
        """Resetea el botón Probar a su estado neutro."""
        c = theme.colors()
        self.btn_probar.setText("🔌  Probar")
        self.btn_probar.setToolTip("Mide la latencia al servidor antes de iniciar el proceso")
        self.btn_probar.set_colors(
            c['btn_tool_bg'], c['accent'], c['accent'], "#ffffff")
        self.btn_probar.setEnabled(True)

    def _probar_conexion(self):
        """Mide la latencia al servidor y notifica el resultado vía Windows notification."""
        from config.settings import URL_ALERTRAN
        self.btn_probar.setEnabled(False)
        self.btn_probar.setText("⏳  Midiendo…")
        self.log("🔌 Probando conexión con el servidor...")
        self._ping_thread = _PingThread(URL_ALERTRAN, parent=self)
        self._ping_thread.resultado.connect(self._on_ping_result)
        self._ping_thread.start()

    def _on_ping_result(self, ms: int, exitoso: bool):
        """Actualiza el botón y lanza notificación Windows con la calidad de red."""
        c = theme.colors()
        if not exitoso:
            titulo  = "❌ Sin acceso al servidor"
            mensaje = "No se pudo conectar.\n🔌 Verifique su red o active la VPN."
            btn_txt = "❌  Sin red"
            bg, hover, tc = "#e05252", "#b93b3b", "#ffffff"
            tip = "Sin conexión al servidor"
        elif ms <= 250:
            titulo  = "✅ Conexión buena"
            mensaje = f"📶 Ping: {ms} ms\nPuede iniciar el proceso sin inconvenientes."
            btn_txt = f"🟢  {ms} ms"
            bg, hover, tc = "#30d158", "#248a3d", "#ffffff"
            tip = f"Última medición: {ms} ms — Buena"
        elif ms <= 350:
            titulo  = "⚠️ Conexión media"
            mensaje = (f"📶 Ping: {ms} ms\n"
                       "💡 Se recomienda activar la VPN\n"
                       "para mejorar la estabilidad del proceso.")
            btn_txt = f"🟡  {ms} ms"
            bg, hover, tc = "#ff9f0a", "#b96800", "#ffffff"
            tip = f"Última medición: {ms} ms — Media. Recomendado: activar VPN"
        elif ms <= 650:
            titulo  = "🔴 Conexión muy lenta"
            mensaje = (f"📶 Ping: {ms} ms\n"
                       "🔌 Active la VPN o conecte un cable Ethernet\n"
                       "antes de iniciar el proceso.")
            btn_txt = f"🔴  {ms} ms"
            bg, hover, tc = "#ff453a", "#b92b22", "#ffffff"
            tip = f"Última medición: {ms} ms — Muy lenta. Use VPN o red cableada"
        else:
            titulo  = "🚫 Conexión crítica"
            mensaje = (f"📶 Ping: {ms} ms\n"
                       "⚠️ La conexión es demasiado lenta para operar.\n"
                       "🔌 Use red cableada y active la VPN.")
            btn_txt = f"🚫  {ms} ms"
            bg, hover, tc = "#9d00d0", "#6a0099", "#ffffff"
            tip = f"Última medición: {ms} ms — Crítica. No recomendado iniciar"

        self.btn_probar.setText(btn_txt)
        self.btn_probar.setToolTip(tip)
        self.btn_probar.set_colors(bg, hover, tc, "#ffffff")
        self.btn_probar.setEnabled(True)
        self.log(f"🔌 Ping al servidor: {ms} ms" if exitoso else "🔌 Sin conexión al servidor")
        self._mostrar_notificacion(titulo, mensaje)

    def _mostrar_error_validacion(self, mensaje):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("⚠️ Validación")
        msg.setText(f"<b>{mensaje}</b>")
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def _confirmar_inicio_proceso(self, num_nav, es_viajes=False):
        """Muestra confirmación antes de iniciar el proceso"""
        titulo, emoji, filas, advertencia = self._get_confirmacion_data(num_nav, es_viajes)
        _c = theme.colors()
        gradient = (_c['accent'], _c['purple']) if es_viajes else (_c['success'], _c['accent'])

        dlg = ConfirmDialog(
            titulo=titulo,
            emoji=emoji,
            filas=filas,
            carpeta=str(self.carpeta_descargas),
            advertencia=advertencia,
            header_gradient=gradient,
            parent=self
        )
        dlg.exec()
        return dlg.resultado

    def _get_confirmacion_data(self, num_nav, es_viajes=False):
        """Devuelve (titulo, emoji, filas, advertencia) para ConfirmDialog"""
        color_guias = (
            "#27ae60" if self.total_guias < 50
            else "#e67e22" if self.total_guias < 100
            else "#e74c3c"
        )
        emoji_guias = (
            "✅" if self.total_guias < 50
            else "⚠️" if self.total_guias < 100
            else "🔴"
        )

        if es_viajes:
            titulo = "DESVIACIÓN DE VIAJES"
            emoji = "🚚"
            if self.excel_path and self.total_guias > 0:
                guias_val = f"{emoji_guias}  {self.total_guias} guías"
                guias_color = color_guias
            else:
                guias_val = "ℹ️  Modo manual (sin Excel)"
                guias_color = "#2980b9"

            _global_obs    = self.observaciones_input.toPlainText().strip()
            _global_ciudad = self.ciudad_combo_desv.currentText()
            _global_tipo   = self.tipo_desviacion_combo.currentText()
            _all_custom    = self.viaje_queue.all_have_custom()
            _viajes        = self.viaje_queue.get_queued_viajes()

            # Construir resumen por viaje si hay config custom
            if _all_custom:
                _viaje_lines = []
                for v in _viajes[:3]:
                    cfg = self.viaje_queue.get_viaje_config(v)
                    _c_ciudad = cfg.get('ciudad') or _global_ciudad
                    _c_tipo   = cfg.get('tipo')   or _global_tipo
                    _viaje_lines.append(f"{v}  [{_c_ciudad[:12]} · T{_c_tipo}]")
                if len(_viajes) > 3:
                    _viaje_lines.append(f"… y {len(_viajes)-3} más")
                viajes_str = "\n".join(_viaje_lines)
                regional_val = "⚙️  Configuración por viaje"
                tipo_val     = "⚙️  Configuración por viaje"
                obs_val      = "⚙️  Configuración por viaje"
            else:
                viajes_str  = ", ".join(_viajes[:3]) or "—"
                if len(_viajes) > 3:
                    viajes_str += f" … +{len(_viajes)-3}"
                regional_val = _global_ciudad
                tipo_val     = _global_tipo
                obs_val      = (_global_obs[:60] + "…") if len(_global_obs) > 60 else _global_obs

            filas = [
                ("👤  Usuario",         self.usuario_actual, None),
                ("📍  Regional",        regional_val,        "#bf5af2" if _all_custom else None),
                ("🎫  Número de Viaje", viajes_str,          None),
                ("📌  Tipo Desviación", tipo_val,            "#bf5af2" if _all_custom else None),
                ("📝  Observaciones",   obs_val,             "#bf5af2" if _all_custom else None),
            ]
            if self.excel_path and self.total_guias > 0:
                filas.insert(2, ("📋  Guías", guias_val, guias_color))
                filas.append(("📁  Archivo Excel", Path(self.excel_path).name, None))

            advertencia = (
                {"titulo": "ℹ️  MODO MANUAL", "texto": "Sin archivo Excel. El flujo continuará normalmente.", "tipo": "info"}
                if not self.excel_path else None
            )

        else:  # Desviaciones originales
            titulo = "DESVIACIONES"
            emoji = "📦"
            guias_val = f"{emoji_guias}  {self.total_guias} guías"

            if self.excel_path:
                fuente_label = "📁  Archivo Excel"
                fuente_valor = Path(self.excel_path).name
            else:
                fuente_label = "📋  Guías pegadas"
                fuente_valor = f"{len(self.guias_pegadas)} guías ingresadas manualmente"

            filas = [
                ("🌐  Navegadores", f"{num_nav} navegador(es) simultáneo(s)", None),
                ("👤  Usuario", self.usuario_actual, None),
                ("📋  Guías", guias_val, color_guias),
                ("📌  Tipo Incidencia", self.tipo_combo.currentText(), None),
                ("📝  Ampliación N°", self.ampliacion_input.currentText().strip(), None),
                (fuente_label, fuente_valor, None),
            ]
            advertencia = (
                {"titulo": "⚠️  PROCESO EXTENSO", "texto": "Espere sin interrumpir.", "tipo": "warning"}
                if self.total_guias > 50 else None
            )

        return titulo, emoji, filas, advertencia

    def cancelar_proceso(self):
        reply = QMessageBox.question(
            self, "Cancelar Proceso",
            "¿Está seguro que desea cancelar el proceso?\n\nLas guías no procesadas quedarán pendientes.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes and self.proceso_thread:
            self.log("🛑 Cancelando proceso...")
            self.proceso_thread.cancelar()
            self.btn_cancelar.setEnabled(False)
            self.btn_cancelar.setText("⏹ CANCELANDO...")

    def proceso_cancelado(self):
        _viaje = getattr(self.proceso_thread, 'numero_viaje', '') if self.proceso_thread else ''
        self._cola_viajes.clear()
        # Marcar la tarjeta como cancelada (no como done ni pending)
        if _viaje:
            self.viaje_queue.set_card_state(_viaje, 'cancelled')
        self.viaje_queue.set_controls_enabled(True)
        if hasattr(self, '_taskbar'):
            self._taskbar.clear()
            self._taskbar.clear_overlay()
        self.log("✅ Proceso cancelado por usuario")
        self.btn_cancelar.setText("⏹ CANCELAR PROCESO")
        self.lbl_tiempo_restante.setText("")
        self.proceso_finalizado()

    def mostrar_error(self, mensaje):
        if hasattr(self, '_taskbar'):
            self._taskbar.set_state(TBPF_ERROR)
            self._taskbar.set_overlay('error')
            self._taskbar.flash(count=3)
        QMessageBox.critical(self, "Error", mensaje)
        self.log(f"🔴 ERROR: {mensaje}")
        self.lbl_tiempo_restante.setText("")
        self.proceso_finalizado()

    def _restaurar_cola_con_fallo(self, viaje_fallido: str):
        """Al fallar un viaje, marca la tarjeta como error y restaura controles."""
        self._cola_viajes.clear()
        self.viaje_queue.set_card_state(viaje_fallido, 'error')
        self.viaje_queue.set_controls_enabled(True)

    def _lanzar_siguiente_viaje(self):
        """Marca el viaje actual como done y lanza el siguiente de la cola."""
        if not self._cola_viajes:
            return
        _viaje_actual = getattr(self.proceso_thread, 'numero_viaje', '') if self.proceso_thread else ''
        if _viaje_actual:
            self.viaje_queue.set_card_state(_viaje_actual, 'done')

        self._viaje_actual_idx += 1
        # Restaurar estado mínimo de UI para que _iniciar_proceso_viajes pueda correr
        self.btn_iniciar.setEnabled(True)
        self.tab_widget.setEnabled(True)
        self._iniciar_proceso_viajes(skip_confirm=True)

    def proceso_finalizado(self):
        """Limpia después de finalizar el proceso"""
        self._timer_transcurrido.stop()
        self.lbl_tiempo_transcurrido.setText("")
        self.progress_bar.setValue(100)
        self.btn_iniciar.setEnabled(True)
        self.btn_cancelar.setEnabled(False)
        self.btn_cancelar.setText("⏹ CANCELAR")
        self.btn_cargar_excel.setEnabled(True)
        self.btn_quitar_excel.setEnabled(bool(self.excel_path))
        self.txt_guias_pegar.setEnabled(True)
        self.btn_login.setEnabled(False)
        self.btn_logout.setEnabled(True)
        self.tab_widget.setEnabled(True)
        self.btn_pausar.setEnabled(False)
        self.btn_pausar.setText("⏸ PAUSAR")
        self.lbl_estado.setText("✅ Finalizado")

        # Persistir historial completo
        HistoryStorage.guardar(self.historial_datos)

        # Notificación del sistema
        _segundos = int((datetime.now() - self.tiempo_inicio).total_seconds()) if self.tiempo_inicio else 0
        _h_n, _rem_n = divmod(_segundos, 3600)
        _m_n, _s_n = divmod(_rem_n, 60)
        _tiempo_str = (f"{_h_n}h {_m_n}m {_s_n}s" if _h_n else
                       f"{_m_n}m {_s_n}s" if _m_n else f"{_s_n}s")

        _tab_idx = self.tab_widget.currentIndex() if hasattr(self, 'tab_widget') else 0
        if _tab_idx == 1 and self.proceso_thread is not None:
            # Notificación especializada para Desviación de Viajes
            _hilo = self.proceso_thread
            _viaje   = getattr(_hilo, 'numero_viaje', '—')
            _ciudad  = getattr(_hilo, 'ciudad', '—')
            _desv    = getattr(_hilo, 'codigo_desviacion', '—')
            _pags_ok = getattr(_hilo, 'paginas_procesadas', 0)
            _pags_tot= getattr(_hilo, 'total_paginas', 0)
            self._mostrar_notificacion(
                "✅ ALERTRAN — Viaje procesado",
                f"🌎 Regional: {_ciudad[:3]}\n"
                f"🎫 Carta porte: {_viaje}"
                f"📄 Páginas: {_pags_ok}/{_pags_tot}\n"
                f"📌 Desviación: {_desv}\n"
                f"⏱ Tiempo total: {_tiempo_str}"
            )
        else:
            # Notificación para Desviaciones (Excel/guías)
            _procesadas = self.desviaciones_creadas + len(self.guias_ent) + self.guias_error_count
            _velocidad  = round(_procesadas / _segundos * 60, 1) if _segundos > 0 else 0
            _tipo = self.tipo_combo.currentText() if hasattr(self, 'tipo_combo') else ""
            self._mostrar_notificacion(
                "✅ ALERTRAN — Proceso finalizado",
                f"✅ {self.desviaciones_creadas} DESV | 📦 {len(self.guias_ent)} ENT | "
                f"❌ {self.guias_error_count} errores\n"
                f"📊 {self.total_guias} guías | 🏷️ Tipo {_tipo} | "
                f"|⏱ {_tiempo_str}"
            )

        # Si hay más viajes en la cola, evaluar si el actual fue exitoso
        if self._cola_viajes:
            _hilo = self.proceso_thread
            _exitoso = getattr(_hilo, 'proceso_viaje_exitoso', False)
            _cancelado = getattr(_hilo, 'cancelado', False)
            _viaje_actual = getattr(_hilo, 'numero_viaje', '')
            if _exitoso and not _cancelado:
                self.log(f"⏭ Cola: {len(self._cola_viajes)} viaje(s) restantes — lanzando siguiente...")
                self.viaje_queue.set_card_state(_viaje_actual, 'done')
                QTimer.singleShot(1500, self._lanzar_siguiente_viaje)
                return
            else:
                # Falló o canceló: devolver viaje fallido + pendientes al textarea
                self._restaurar_cola_con_fallo(_viaje_actual)

        # Marcar tarjeta como completada solo si el proceso fue exitoso (no cancelado/error)
        _viaje_fin      = getattr(self.proceso_thread, 'numero_viaje', '') if self.proceso_thread else ''
        _fue_cancelado  = getattr(self.proceso_thread, 'cancelado', False) if self.proceso_thread else False
        _fue_exitoso    = getattr(self.proceso_thread, 'proceso_viaje_exitoso', False) if self.proceso_thread else False
        if _viaje_fin and _fue_exitoso and not _fue_cancelado:
            self.viaje_queue.set_card_state(_viaje_fin, 'done')
        elif _viaje_fin and not _fue_exitoso and not _fue_cancelado:
            # Error: si la tarjeta quedó en 'processing', marcarla como error
            _cur = next((c.state for c in self.viaje_queue._cards if c.numero == _viaje_fin), '')
            if _cur == 'processing':
                self.viaje_queue.set_card_state(_viaje_fin, 'error')
        self.viaje_queue.set_controls_enabled(True)

        # Notificación de cola completa
        _done      = [c for c in self.viaje_queue._cards if c.state == 'done']
        _errors    = [c for c in self.viaje_queue._cards if c.state == 'error']
        _cancelled = [c for c in self.viaje_queue._cards if c.state == 'cancelled']
        _total     = len(self.viaje_queue._cards)
        _failed    = len(_errors) + len(_cancelled)
        if _total > 0:
            _partes_err = []
            if _errors:    _partes_err.append(f"{len(_errors)} con error")
            if _cancelled: _partes_err.append(f"{len(_cancelled)} cancelado(s)")
            _linea_err = (" · " + ", ".join(_partes_err)) if _partes_err else ""
            self._mostrar_notificacion(
                "✅ ALERTRAN — Cola finalizada",
                f"{len(_done)}/{_total} viaje(s) completados{_linea_err}"
            )
        # Banner de reintentar si hay fallos
        if _failed > 0:
            self.viaje_queue.show_retry_banner(_failed)

        # Taskbar: overlay de éxito + flash si la ventana está en segundo plano
        if hasattr(self, '_taskbar'):
            self._taskbar.set_overlay('ok' if not _failed else 'error')
            self._taskbar.clear()
            if not self.isActiveWindow():
                self._taskbar.flash(count=4)

        self.mostrar_resumen()

    def archivo_errores_generado(self, ruta):
        self.btn_errores.setEnabled(True)
        self.btn_reprocesar.setEnabled(True)
        self.error_path = ruta
        
        QMessageBox.information(
            self, "✅ Archivo Generado", 
            f"📊 Archivo de errores y advertencias guardado en:\n{ruta}\n\n📁 Carpeta: Descargas"
        )
        
        self.log(f"✅ Archivo de errores guardado en: {ruta}")

    def mostrar_errores(self):
        if hasattr(self, 'error_path') and self.error_path:
            reply = QMessageBox.question(
                self, "📂 Archivo de Errores",
                f"📊 Archivo guardado en:\n{self.error_path}\n\n"
                f"¿Desea abrir la carpeta que contiene el archivo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                carpeta = Path(self.error_path).parent
                if os.name == 'nt':
                    os.startfile(carpeta)
                else:
                    subprocess.run(['open' if sys.platform == 'darwin' else 'xdg-open', str(carpeta)])

    # ── Pausa ────────────────────────────────────────────────────────────────

    def toggle_pausa(self):
        """Alterna entre pausar y reanudar el proceso activo."""
        if not self.proceso_thread or self.proceso_thread.cancelado:
            return
        if self.proceso_thread.pausado:
            self.proceso_thread.reanudar()
            self.btn_pausar.setText("⏸ PAUSAR")
            self.lbl_estado.setText("▶️ Proceso reanudado")
            self.log("▶️ Proceso reanudado")
            if hasattr(self, '_taskbar'):
                self._taskbar.set_state(TBPF_NORMAL)
                self._taskbar.set_overlay('processing')
        else:
            self.proceso_thread.pausar()
            self.btn_pausar.setText("▶ REANUDAR")
            self.lbl_estado.setText("⏸ Proceso en pausa")
            self.log("⏸ Proceso pausado — haz clic en REANUDAR para continuar")
            if hasattr(self, '_taskbar'):
                self._taskbar.set_state(TBPF_PAUSED)
                self._taskbar.set_overlay('paused')

    # ── Reprocesar errores ────────────────────────────────────────────────────

    def reprocesar_errores(self):
        """Reprocesa las guías del archivo de errores: directamente o cargando el Excel."""
        if not hasattr(self, 'error_path') or not self.error_path:
            QMessageBox.warning(self, "⚠️", "No hay archivo de errores para reprocesar.")
            return
        if not Path(self.error_path).exists():
            QMessageBox.warning(self, "⚠️", f"El archivo de errores ya no existe:\n{self.error_path}")
            return

        msg = QMessageBox(self)
        msg.setWindowTitle("🔁 Reprocesar errores")
        msg.setText(f"<b>{Path(self.error_path).name}</b>")
        msg.setInformativeText("¿Qué deseas hacer con las guías que fallaron?")
        btn_ahora  = msg.addButton("🚀  Reprocesar ahora",    QMessageBox.ButtonRole.AcceptRole)
        btn_cargar = msg.addButton("📂  Solo cargar archivo", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_ahora:
            self._reprocesar_errores_en_lote()
        elif clicked == btn_cargar:
            self._set_excel_file(self.error_path)
            self.log(f"🔁 Cargado para reprocesar: {Path(self.error_path).name}")

    def _reprocesar_errores_en_lote(self):
        """Lee las guías del archivo de errores y lanza el proceso directamente."""
        if not self.sesion_activa:
            QMessageBox.warning(self, "⚠️ Sin sesión", "Inicia sesión antes de reprocesar.")
            return
        if not self.ampliacion_input.currentText().strip():
            QMessageBox.warning(self, "⚠️ Ampliación vacía",
                                "Completa el campo Ampliación antes de reprocesar.")
            return
        if self.proceso_thread and self.proceso_thread.isRunning():
            QMessageBox.warning(self, "⚠️ Proceso activo",
                                "Espera a que el proceso actual finalice.")
            return

        try:
            guias = FileUtils().leer_guias_excel(Path(self.error_path))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer el archivo de errores:\n{e}")
            return

        if not guias:
            QMessageBox.information(self, "ℹ️", "El archivo de errores no contiene guías.")
            return

        guias_unicas = list(dict.fromkeys(guias))
        self.guias_pegadas  = guias_unicas
        self.excel_path     = None
        self.total_guias    = len(guias_unicas)
        self.log(f"🔁 Reprocesando {self.total_guias} guías con error...")
        self._iniciar_proceso_desviaciones()

    # ── Configuración avanzada ────────────────────────────────────────────────

    def abrir_configuracion(self):
        """Abre el diálogo de configuración avanzada de tiempos."""
        from ui.widgets.settings_dialog import SettingsDialog
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.log("⚙️ Configuración guardada — se aplicará en el próximo proceso")

    # ── Notificaciones ────────────────────────────────────────────────────────

    def _init_tray_icon(self):
        """Inicializa el ícono de bandeja para notificaciones del sistema."""
        try:
            self._tray_icon = QSystemTrayIcon(self)
            self._tray_icon.setIcon(
                self.style().standardIcon(
                    self.style().StandardPixmap.SP_MessageBoxInformation
                )
            )
            self._tray_icon.show()
        except Exception:
            self._tray_icon = None

    def _mostrar_notificacion(self, titulo: str, mensaje: str):
        """Muestra notificación de escritorio si el tray está disponible."""
        try:
            if self._tray_icon:
                self._tray_icon.showMessage(
                    titulo, mensaje,
                    QSystemTrayIcon.MessageIcon.Information,
                    5000
                )
        except Exception:
            pass

    # ── Historial ─────────────────────────────────────────────────────────────

    def obtener_datos_historial(self):
        """Retorna los datos actuales del historial para actualización en tiempo real"""
        return self.historial_datos.copy() if hasattr(self, 'historial_datos') else []