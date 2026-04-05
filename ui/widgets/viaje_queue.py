# ui/widgets/viaje_queue.py
"""
Cola visual de viajes — estilo Timeline vertical con nodos.
Cada entrada es un nodo conectado por una línea continua (stepper).
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QSizePolicy,
    QDialog, QFormLayout, QComboBox, QTextEdit, QDialogButtonBox, QFrame,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QTimer, QEvent
from PySide6.QtGui import QFont, QPainter, QColor, QPen, QBrush
from utils import theme


# ── Paleta de nodos ───────────────────────────────────────────────────────────

_NODE_COLOR = {
    'pending':    QColor('#5a5a72'),
    'processing': QColor('#4da6ff'),
    'error':      QColor('#e05252'),
    'done':       QColor('#52c08a'),
    'cancelled':  QColor('#ff9500'),
    'custom':     QColor('#bf5af2'),   # púrpura — config personalizada
}

_STATE_LABEL = {
    'pending':    ('Pendiente',   '#5a5a72'),
    'processing': ('Procesando…', '#4da6ff'),
    'error':      ('Error',       '#e05252'),
    'done':       ('Listo',       '#52c08a'),
    'cancelled':  ('Cancelado',   '#ff9500'),
}

_NODE_X = 10
_NODE_R = 4
_LINE_W = 1


# ── Label clickeable (evita el QSS global de QPushButton) ────────────────────

class _IconLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str, size: int = 20, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(QFont("Segoe UI Symbol", 9))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── Dialog de configuración por viaje ────────────────────────────────────────

class ViajeConfigDialog(QDialog):
    """Mini-popup para configurar Regional, Tipo Desviación y Observaciones de un viaje."""

    def __init__(self, numero: str, current: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"⚙️  Config — viaje {numero}")
        self.setMinimumWidth(340)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowCloseButtonHint
        )
        self._build_ui(current)
        self._apply_styles()
        theme.signals.changed.connect(self._apply_styles)

    def _build_ui(self, current: dict):
        from config.constants import CIUDADES, TIPOS_INCIDENCIA

        c    = theme.colors()
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 14)

        # Encabezado
        lbl_head = QLabel("Configuración específica para este viaje.\nSi dejas un campo vacío, se usa el valor global.")
        lbl_head.setWordWrap(True)
        lbl_head.setStyleSheet(f"color: {c.get('text3','#888')}; font-size: 8.5pt;")
        root.addWidget(lbl_head)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Regional
        self._combo_ciudad = QComboBox()
        self._combo_ciudad.addItem("")           # vacío = heredar global
        self._combo_ciudad.addItems(CIUDADES)
        self._combo_ciudad.setEditable(True)
        if current.get('ciudad'):
            self._combo_ciudad.setCurrentText(current['ciudad'])
        form.addRow("📍 Regional:", self._combo_ciudad)

        # Tipo desviación
        self._combo_tipo = QComboBox()
        self._combo_tipo.addItem("")             # vacío = heredar global
        self._combo_tipo.addItems(TIPOS_INCIDENCIA)
        if current.get('tipo'):
            self._combo_tipo.setCurrentText(current['tipo'])
        form.addRow("📌 Tipo Desv.:", self._combo_tipo)

        # Observaciones
        self._txt_obs = QTextEdit()
        self._txt_obs.setPlaceholderText("Dejar vacío para usar la observación global…")
        self._txt_obs.setFixedHeight(72)
        self._txt_obs.setPlainText(current.get('observaciones', ''))
        form.addRow("📝 Obs.:", self._txt_obs)

        root.addLayout(form)

        # Botones
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _apply_styles(self):
        c = theme.colors()
        self.setStyleSheet(f"""
            QDialog {{
                background: {c['bg']};
            }}
            QLabel {{
                color: {c['text']}; background: transparent; border: none;
            }}
            QComboBox, QTextEdit {{
                background: {c['surface2']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 4px 8px;
            }}
            QComboBox:focus, QTextEdit:focus {{
                border: 1px solid {c['accent']};
            }}
            QPushButton {{
                background: {c['surface2']};
                color: {c['text']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 5px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {c['accent']}; color: {c['accent']};
            }}
        """)

    def get_config(self) -> dict:
        """Retorna dict con los valores; vacíos = heredar global."""
        return {
            'ciudad':        self._combo_ciudad.currentText().strip(),
            'tipo':          self._combo_tipo.currentText().strip(),
            'observaciones': self._txt_obs.toPlainText().strip(),
        }


# ── Nodo / tarjeta ────────────────────────────────────────────────────────────

class ViajeCard(QWidget):
    """Fila de timeline para un viaje."""

    sig_remove     = Signal(str)
    sig_retry      = Signal(str)
    sig_config_req = Signal(str)
    sig_drag_start = Signal(str)   # emitido cuando inicia arrastre

    def __init__(self, numero: str, parent=None):
        super().__init__(parent)
        self._numero          = numero
        self._state           = 'pending'
        self._is_last         = True
        self._has_custom      = False
        self._anim            = None
        self._drag_start_pos  = None   # posición global al presionar handle

        self._pulse_phase = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(30)
        self._pulse_timer.timeout.connect(self._pulse_tick)

        self._elapsed_sec = 0
        self._clock = QTimer(self)
        self._clock.setInterval(1000)
        self._clock.timeout.connect(self._clock_tick)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(38)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._build_ui()
        self._apply_style()
        theme.signals.changed.connect(self._apply_style)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(_NODE_X * 2 + _NODE_R + 8, 0, 6, 0)
        lay.setSpacing(4)

        # Handle de arrastre
        self._drag_handle = _IconLabel("⠿", 16)
        self._drag_handle.setFont(QFont("Segoe UI Symbol", 10))
        self._drag_handle.setCursor(Qt.CursorShape.OpenHandCursor)
        self._drag_handle.setToolTip("Arrastrar para cambiar orden")
        self._drag_handle.installEventFilter(self)
        lay.addWidget(self._drag_handle)

        self._lbl_num = QLabel(self._numero)
        self._lbl_num.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self._lbl_num.setSizePolicy(QSizePolicy.Policy.Expanding,
                                    QSizePolicy.Policy.Preferred)
        lay.addWidget(self._lbl_num)

        self._lbl_timer = QLabel("")
        self._lbl_timer.setFont(QFont("Consolas", 8))
        self._lbl_timer.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lbl_timer.setVisible(False)
        lay.addWidget(self._lbl_timer)

        self._lbl_state = QLabel("Pendiente")
        self._lbl_state.setFont(QFont("Segoe UI", 8))
        self._lbl_state.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addWidget(self._lbl_state)

        # ── Botón config ⚙ ───────────────────────────────────────────────
        self._btn_config = _IconLabel("⚙", 20)
        self._btn_config.setToolTip("Configuración específica de este viaje")
        self._btn_config.clicked.connect(lambda: self.sig_config_req.emit(self._numero))
        lay.addWidget(self._btn_config)

        # ── Botón reintentar ↩ ───────────────────────────────────────────
        self._btn_retry = _IconLabel("↩", 22)
        self._btn_retry.setVisible(False)
        self._btn_retry.setToolTip("Reintentar")
        self._btn_retry.clicked.connect(lambda: self.sig_retry.emit(self._numero))
        lay.addWidget(self._btn_retry)

        # ── Botón quitar ✕ ───────────────────────────────────────────────
        self._btn_remove = _IconLabel("✕", 20)
        self._btn_remove.setToolTip("Quitar de la cola")
        self._btn_remove.clicked.connect(self._animate_remove)
        lay.addWidget(self._btn_remove)

    # ── Config custom ─────────────────────────────────────────────────────────

    def set_has_custom(self, v: bool):
        if self._has_custom != v:
            self._has_custom = v
            self._apply_style()
            self.update()

    # ── Pintado del timeline ──────────────────────────────────────────────────

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = _NODE_X
        cy = self.height() // 2
        r  = _NODE_R

        # Color del nodo: azul brillante si tiene config custom y está pendiente
        if self._has_custom and self._state == 'pending':
            node_col = _NODE_COLOR['processing']   # mismo azul que el botón ⚙
        else:
            node_col = _NODE_COLOR.get(self._state, _NODE_COLOR['pending'])

        # Línea de conexión
        line_col = QColor(node_col)
        line_col.setAlpha(45)
        pen = QPen(line_col, _LINE_W)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(pen)
        p.drawLine(cx, 0, cx, cy - r - 2)
        if not self._is_last:
            p.drawLine(cx, cy + r + 2, cx, self.height())

        # Halo de pulso
        if self._state == 'processing' and self._pulse_phase > 0.01:
            halo = QColor(node_col)
            halo.setAlpha(int(55 * (1.0 - self._pulse_phase)))
            halo_r = int(r + self._pulse_phase * 7)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo))
            p.drawEllipse(cx - halo_r, cy - halo_r, halo_r * 2, halo_r * 2)

        p.setPen(Qt.PenStyle.NoPen)

        if self._state == 'pending':
            ring_col = QColor(node_col)
            ring_col.setAlpha(160)
            p.setPen(QPen(ring_col, 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
            dot_col = QColor(node_col)
            dot_col.setAlpha(90)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(dot_col))
            p.drawEllipse(cx - 2, cy - 2, 4, 4)
        else:
            filled = QColor(node_col)
            filled.setAlpha(220)
            p.setBrush(QBrush(filled))
            p.drawEllipse(cx - r, cy - r, r * 2, r * 2)
            inner = QColor(255, 255, 255, 35)
            p.setBrush(QBrush(inner))
            p.drawEllipse(cx - r + 2, cy - r + 1, r, r - 1)

        p.end()

    # ── Pulso / Cronómetro ────────────────────────────────────────────────────

    def _pulse_tick(self):
        self._pulse_phase += 0.04
        if self._pulse_phase >= 1.0:
            self._pulse_phase = 0.0
        self.update()

    def _clock_tick(self):
        self._elapsed_sec += 1
        m, s = divmod(self._elapsed_sec, 60)
        h, m = divmod(m, 60)
        txt = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        self._lbl_timer.setText(txt)

    def start_clock(self):
        """Arranca el cronómetro — llamar solo cuando el proceso realmente inicia."""
        self._elapsed_sec = 0
        self._lbl_timer.setText("00:00")
        self._lbl_timer.setStyleSheet(
            "color: #4da6ff; background: transparent; border: none;")
        self._lbl_timer.setVisible(True)
        self._clock.start()

    # ── Estado ────────────────────────────────────────────────────────────────

    def set_state(self, state: str):
        if state == self._state:
            return
        self._state = state
        label, color = _STATE_LABEL.get(state, ('Pendiente', '#5a5a72'))
        self._lbl_state.setText(label)
        self._lbl_state.setStyleSheet(
            f"color: {color}; background: transparent; border: none;")
        self._btn_retry.setVisible(state in ('error', 'cancelled'))
        self._btn_remove.setVisible(state != 'processing')
        self._btn_config.setVisible(state in ('pending', 'error', 'cancelled'))
        self._drag_handle.setVisible(state in ('pending', 'error', 'cancelled'))
        self._apply_style()

        if state == 'processing':
            self._elapsed_sec = 0
            self._lbl_timer.setText("")
            self._lbl_timer.setVisible(False)
            self._pulse_timer.start()
        else:
            self._clock.stop()
            self._pulse_timer.stop()
            self._pulse_phase = 0.0
            if self._lbl_timer.isVisible():
                self._lbl_timer.setStyleSheet(
                    "color: #5a5a72; background: transparent; border: none;")
            self.update()

    def set_is_last(self, v: bool):
        if self._is_last != v:
            self._is_last = v
            self.update()

    # ── Drag handle ───────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._drag_handle and self._state not in ('processing', 'done'):
            if event.type() == QEvent.Type.MouseButtonPress:
                if event.button() == Qt.MouseButton.LeftButton:
                    self._drag_start_pos = event.globalPosition().toPoint()
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                if (self._drag_start_pos is not None and
                        (event.globalPosition().toPoint() - self._drag_start_pos)
                        .manhattanLength() > 6):
                    self._drag_start_pos = None
                    self.sig_drag_start.emit(self._numero)
                return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self._drag_start_pos = None
        return super().eventFilter(obj, event)

    # ── Estilos ───────────────────────────────────────────────────────────────

    def _apply_style(self):
        c   = theme.colors()
        txt = '#e05252' if self._state == 'error' else c.get('text', '#ddd')

        self._lbl_num.setStyleSheet(
            f"color: {txt}; background: transparent; border: none;")

        # ⠿ drag handle: sutil
        self._drag_handle.setStyleSheet(
            "color: rgba(150,150,165,0.55); background: transparent; border: none;")

        # ⚙ config: azul fuerte si tiene config propia, azul sutil si no
        if self._has_custom:
            self._btn_config.setStyleSheet("""
                background: #4da6ff; color: white;
                border: 1px solid #4da6ff; border-radius: 4px;
            """)
        else:
            self._btn_config.setStyleSheet("""
                background: rgba(77,166,255,0.15); color: #4da6ff;
                border: 1px solid rgba(77,166,255,0.30); border-radius: 4px;
            """)

        # ✕ quitar: rojo sutil
        self._btn_remove.setStyleSheet("""
            background: rgba(224,82,82,0.15); color: #e05252;
            border: 1px solid rgba(224,82,82,0.30); border-radius: 3px;
        """)

        # ↩ reintentar: naranja si cancelado, rojo si error
        if self._state == 'cancelled':
            self._btn_retry.setStyleSheet("""
                background: rgba(255,149,0,0.18); color: #ff9500;
                border: 1px solid rgba(255,149,0,0.45); border-radius: 4px;
            """)
        else:
            self._btn_retry.setStyleSheet("""
                background: rgba(224,82,82,0.20); color: #e05252;
                border: 1px solid rgba(224,82,82,0.45); border-radius: 4px;
            """)

    # ── Animación de salida ───────────────────────────────────────────────────

    def _animate_remove(self):
        self._pulse_timer.stop()
        self._anim = QPropertyAnimation(self, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setStartValue(self.height())
        self._anim.setEndValue(0)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.finished.connect(self._on_remove_done)
        self._anim.start()

    def _on_remove_done(self):
        self.sig_remove.emit(self._numero)
        self.setParent(None)
        self.deleteLater()

    # ── Acceso ────────────────────────────────────────────────────────────────

    @property
    def numero(self) -> str:
        return self._numero

    @property
    def state(self) -> str:
        return self._state


# ── Contenedor timeline ───────────────────────────────────────────────────────

class ViajesQueueWidget(QWidget):
    """Cola visual de viajes en estilo timeline vertical."""

    queue_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cards: list[ViajeCard] = []
        self._custom_configs: dict[str, dict] = {}
        self._drag_card: ViajeCard = None
        self._drop_idx: int = -1
        self._build_ui()
        theme.signals.changed.connect(self._apply_theme)

    # ── Construcción ─────────────────────────────────────────────────────────

    def _build_ui(self):
        c    = theme.colors()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        self._cards_container = QWidget()
        self._cards_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 2, 0, 2)
        self._cards_layout.setSpacing(0)
        root.addWidget(self._cards_container)

        # Banner de reintentar (oculto por defecto)
        self._banner = QFrame()
        self._banner.setObjectName("retry_banner")
        self._banner.setVisible(False)
        banner_lay = QHBoxLayout(self._banner)
        banner_lay.setContentsMargins(10, 6, 10, 6)
        banner_lay.setSpacing(8)
        self._lbl_banner = QLabel("")
        banner_lay.addWidget(self._lbl_banner, stretch=1)
        self._btn_retry_all = QPushButton("🔄  Reintentar todos")
        self._btn_retry_all.setFixedHeight(26)
        self._btn_retry_all.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_retry_all.clicked.connect(self._retry_all_failed)
        banner_lay.addWidget(self._btn_retry_all)
        root.addWidget(self._banner)
        self._apply_banner_style()

        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        add_row.setContentsMargins(0, 0, 0, 0)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Nº de viaje  (Enter para agregar)")
        self._input.setFixedHeight(32)
        self._input.returnPressed.connect(self._on_add)
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {c.get('surface2', 'rgba(60,60,62,0.9)')};
                color: {c.get('text', '#ddd')};
                border: 1px solid {c.get('border', '#444')};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 10pt;
            }}
            QLineEdit:focus {{ border: 1px solid {c.get('accent', '#0a84ff')}; }}
        """)
        add_row.addWidget(self._input, stretch=1)

        self._btn_add = QPushButton("＋  Agregar")
        self._btn_add.setFixedHeight(32)
        self._btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_add.clicked.connect(self._on_add)
        self._btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {c.get('accent', '#0a84ff')};
                color: white; border: none; border-radius: 8px;
                font-size: 9pt; font-weight: 700; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {c.get('accent_hover', '#0070e0')}; }}
            QPushButton:disabled {{
                background: {c.get('surface2', '#444')};
                color: {c.get('text3', '#888')};
            }}
        """)
        add_row.addWidget(self._btn_add)
        root.addLayout(add_row)

        self._lbl_hint = QLabel("Sin viajes en cola")
        self._lbl_hint.setStyleSheet(
            f"color: {c.get('text3', '#888')}; font-size: 8pt; padding: 0 2px;")
        root.addWidget(self._lbl_hint)

        # Indicador flotante de posición de drop (no está en el layout)
        self._drop_indicator = QFrame(self)
        self._drop_indicator.setFixedHeight(2)
        self._drop_indicator.setStyleSheet(
            "background: #4da6ff; border-radius: 1px;")
        self._drop_indicator.setVisible(False)

    # ── Acciones ──────────────────────────────────────────────────────────────

    def _on_add(self):
        numero = self._input.text().strip()
        if not numero:
            return
        existentes = [c.numero for c in self._cards if c.state in ('pending', 'error', 'cancelled')]
        if numero in existentes:
            self._input.setStyleSheet(self._input.styleSheet() +
                                      " border: 1px solid #e05252;")
            QTimer.singleShot(800, self._reset_input_style)
            return
        self.add_viaje(numero)
        self._input.clear()

    def _reset_input_style(self):
        c = theme.colors()
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {c.get('surface2', 'rgba(60,60,62,0.9)')};
                color: {c.get('text', '#ddd')};
                border: 1px solid {c.get('border', '#444')};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 10pt;
            }}
            QLineEdit:focus {{ border: 1px solid {c.get('accent', '#0a84ff')}; }}
        """)

    def _on_config_req(self, numero: str):
        """Abre el dialog de configuración para el viaje dado."""
        current = self._custom_configs.get(numero, {})
        dlg = ViajeConfigDialog(numero, current, parent=self.window())
        if dlg.exec() == QDialog.DialogCode.Accepted:
            cfg = dlg.get_config()
            has_any = any(cfg.values())
            if has_any:
                self._custom_configs[numero] = cfg
            else:
                self._custom_configs.pop(numero, None)
            # Actualizar nodo de la tarjeta
            for card in self._cards:
                if card.numero == numero:
                    card.set_has_custom(has_any)
                    break
            self.queue_changed.emit()

    # ── Drag & drop para reordenar ────────────────────────────────────────────

    def _on_drag_start(self, numero: str):
        if self._drag_card is not None:
            return
        for card in self._cards:
            if card.numero == numero and card.state not in ('processing', 'done'):
                self._drag_card = card
                self._drop_idx = self._cards.index(card)
                break
        if self._drag_card:
            self._drop_indicator.setGeometry(0, 0, self.width(), 2)
            self._drop_indicator.setVisible(True)
            self._drop_indicator.raise_()
            self.grabMouse()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_card is not None:
            self._drop_idx = self._find_drop_idx(event.pos().y())
            self._position_indicator(self._drop_idx)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag_card is not None:
            self.releaseMouse()
            self.unsetCursor()
            old_idx = self._cards.index(self._drag_card)
            new_idx = self._drop_idx
            self._drop_indicator.setVisible(False)
            self._drag_card = None
            # Ajustar índice de inserción tras la eliminación de la posición original
            if new_idx > old_idx:
                new_idx -= 1
            if old_idx != new_idx:
                self._do_reorder(old_idx, new_idx)
        super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        if self._drop_indicator.isVisible():
            self._drop_indicator.setFixedWidth(self.width())
        super().resizeEvent(event)

    def _find_drop_idx(self, y: int) -> int:
        """Índice de inserción para la posición y (coords de self)."""
        for i, card in enumerate(self._cards):
            card_top = self._cards_container.mapTo(self, card.pos()).y()
            card_mid = card_top + card.height() // 2
            if y < card_mid:
                return i
        return len(self._cards)

    def _position_indicator(self, idx: int):
        if not self._cards:
            return
        if idx == 0:
            iy = self._cards_container.mapTo(self, self._cards[0].pos()).y()
        elif idx >= len(self._cards):
            last = self._cards[-1]
            iy = self._cards_container.mapTo(self, last.pos()).y() + last.height()
        else:
            iy = self._cards_container.mapTo(self, self._cards[idx].pos()).y()
        self._drop_indicator.setGeometry(0, iy - 1, self.width(), 2)

    def _do_reorder(self, old_idx: int, new_idx: int):
        card = self._cards.pop(old_idx)
        self._cards.insert(new_idx, card)
        for c in self._cards:
            self._cards_layout.removeWidget(c)
        for c in self._cards:
            self._cards_layout.addWidget(c)
        self._update_last_flags()
        self.queue_changed.emit()

    # ── API pública ───────────────────────────────────────────────────────────

    def add_viaje(self, numero: str, state: str = 'pending'):
        card = ViajeCard(numero, self)
        if state != 'pending':
            card.set_state(state)
        card.sig_remove.connect(self._on_card_removed)
        card.sig_retry.connect(self._on_card_retry)
        card.sig_config_req.connect(self._on_config_req)
        card.sig_drag_start.connect(self._on_drag_start)
        self._cards_layout.addWidget(card)
        self._cards.append(card)
        self._update_last_flags()
        self._update_hint()
        self.queue_changed.emit()

    def _on_card_removed(self, numero: str):
        self._cards = [c for c in self._cards
                       if c.numero != numero or c.state == 'processing']
        self._custom_configs.pop(numero, None)
        self._update_last_flags()
        self._update_hint()
        self.queue_changed.emit()

    def _on_card_retry(self, numero: str):
        for card in self._cards:
            if card.numero == numero:
                card.set_state('pending')
                break
        # Ocultar banner si ya no quedan fallos
        remaining_failed = [c for c in self._cards if c.state in ('error', 'cancelled')]
        if not remaining_failed:
            self._banner.setVisible(False)
        self._update_hint()
        self.queue_changed.emit()

    def set_card_state(self, numero: str, state: str):
        for card in self._cards:
            if card.numero == numero:
                card.set_state(state)
                return

    def start_card_clock(self, numero: str):
        """Arranca el cronómetro de la tarjeta indicada."""
        for card in self._cards:
            if card.numero == numero:
                card.start_clock()
                return

    def get_pending_viajes(self) -> list:
        return [c.numero for c in self._cards if c.state == 'pending']

    def get_all_active(self) -> list:
        return [c.numero for c in self._cards if c.state in ('pending', 'error', 'cancelled')]

    def get_queued_viajes(self) -> list:
        """Todos los viajes que aún no están completados (incluye el que está procesando)."""
        return [c.numero for c in self._cards if c.state != 'done']

    def get_viaje_config(self, numero: str) -> dict:
        """Retorna la config propia del viaje (vacío = usar global)."""
        return self._custom_configs.get(numero, {})

    def all_have_custom(self) -> bool:
        """True si todos los viajes activos tienen configuración propia completa."""
        active = [c for c in self._cards if c.state in ('pending', 'error', 'cancelled')]
        if not active:
            return False
        return all(c.numero in self._custom_configs for c in active)

    def retry_all_failed(self):
        """API pública para reintentar todos los viajes fallidos/cancelados."""
        self._retry_all_failed()

    def show_retry_banner(self, count: int):
        """Muestra el banner de reintentar al final de la cola."""
        self._lbl_banner.setText(f"⚠️  {count} viaje(s) no completado(s)")
        self._banner.setVisible(True)

    def hide_retry_banner(self):
        self._banner.setVisible(False)

    def _retry_all_failed(self):
        """Resetea todos los viajes cancelados/con error a pendiente."""
        for card in self._cards:
            if card.state in ('error', 'cancelled'):
                card.set_state('pending')
        self._banner.setVisible(False)
        self._update_hint()
        self.queue_changed.emit()

    def set_controls_enabled(self, enabled: bool):
        self._input.setEnabled(enabled)
        self._btn_add.setEnabled(enabled)

    def focus_input(self):
        self._input.setFocus()

    # ── Helpers internos ──────────────────────────────────────────────────────

    def _apply_banner_style(self):
        c = theme.colors()
        self._banner.setStyleSheet(f"""
            QFrame#retry_banner {{
                background: rgba(255,149,0,0.10);
                border: 1px solid rgba(255,149,0,0.40);
                border-radius: 8px;
            }}
            QLabel {{
                color: #ff9500; font-size: 9pt; font-weight: bold;
                background: transparent; border: none;
            }}
            QPushButton {{
                background: rgba(255,149,0,0.18); color: #ff9500;
                border: 1px solid rgba(255,149,0,0.50); border-radius: 6px;
                font-size: 9pt; font-weight: 700; padding: 0 12px;
            }}
            QPushButton:hover {{ background: rgba(255,149,0,0.32); }}
            QPushButton:pressed {{ background: rgba(255,149,0,0.45); }}
        """)

    def _apply_theme(self):
        c = theme.colors()
        self._apply_banner_style()
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: {c.get('surface2', 'rgba(60,60,62,0.9)')};
                color: {c.get('text', '#ddd')};
                border: 1px solid {c.get('border', '#444')};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 10pt;
            }}
            QLineEdit:focus {{ border: 1px solid {c.get('accent', '#0a84ff')}; }}
        """)
        self._btn_add.setStyleSheet(f"""
            QPushButton {{
                background: {c.get('accent', '#0a84ff')};
                color: white; border: none; border-radius: 8px;
                font-size: 9pt; font-weight: 700; padding: 0 14px;
            }}
            QPushButton:hover {{ background: {c.get('accent_hover', '#0070e0')}; }}
            QPushButton:disabled {{
                background: {c.get('surface2', '#444')};
                color: {c.get('text3', '#888')};
            }}
        """)
        self._lbl_hint.setStyleSheet(
            f"color: {c.get('text3', '#888')}; font-size: 8pt; padding: 0 2px;")

    def _update_last_flags(self):
        for i, card in enumerate(self._cards):
            card.set_is_last(i == len(self._cards) - 1)

    def _update_hint(self):
        pending   = self.get_pending_viajes()
        errors    = [c for c in self._cards if c.state == 'error']
        cancelled = [c for c in self._cards if c.state == 'cancelled']
        done      = [c for c in self._cards if c.state == 'done']
        if not self._cards:
            self._lbl_hint.setText("Sin viajes en cola")
        elif not pending and not errors and not cancelled:
            self._lbl_hint.setText(f"{len(done)} viaje(s) completado(s)")
        else:
            parts = []
            if pending:   parts.append(f"{len(pending)} pendiente(s)")
            if errors:    parts.append(f"{len(errors)} con error")
            if cancelled: parts.append(f"{len(cancelled)} cancelado(s)")
            self._lbl_hint.setText(" · ".join(parts))
