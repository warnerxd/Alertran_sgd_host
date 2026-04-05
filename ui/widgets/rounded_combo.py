# ui/widgets/rounded_combo.py
"""
QComboBox con popup sin frame nativo y border-radius real en Windows.
Estrategia:
  1. FramelessWindowHint  → elimina el borde nativo del SO
  2. setMask() con QRegion redondeado → recorta las esquinas físicamente
     (sin WA_TranslucentBackground → sin artefactos negros/blancos)
  3. QAbstractItemView: fondo sólido + border-radius en CSS (refuerzo visual)
  Resultado: esquinas redondeadas sin artefactos en ningún tema.
"""
from PySide6.QtWidgets import QComboBox, QFrame
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QRegion, QPainterPath, QTransform


RADIUS = 12


def _apply_mask(popup, radius: int):
    """Aplica una máscara redondeada al popup según su tamaño actual."""
    w, h = popup.width(), popup.height()
    if w <= 0 or h <= 0:
        return
    path = QPainterPath()
    path.addRoundedRect(0, 0, w, h, radius, radius)
    polygon = path.toFillPolygon(QTransform()).toPolygon()
    popup.setMask(QRegion(polygon))


class RoundedComboBox(QComboBox):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view().setFrameShape(QFrame.Shape.NoFrame)

    def showPopup(self):
        super().showPopup()
        popup = self.view().window()
        if popup is None or popup is self:
            return

        # ── 1. Quitar frame nativo (sin transparencia → sin artefactos) ───
        popup.setWindowFlags(
            Qt.WindowType.Popup |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.NoDropShadowWindowHint
        )
        # Aseguramos que NO tenga WA_TranslucentBackground
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # ── 2. Contenedor del popup: fondo sólido sin borde ───────────────
        from utils import theme as _t
        c = _t.colors()

        popup.setStyleSheet(
            f"background-color: {c['surface']}; border: none;"
        )
        if popup.layout():
            popup.layout().setContentsMargins(0, 0, 0, 0)
            popup.layout().setSpacing(0)

        # ── 3. Vista: estilo completo ──────────────────────────────────────
        self.view().setStyleSheet(f"""
            QAbstractItemView {{
                background-color: {c['surface']};
                border: 1.5px solid {c['border_strong']};
                border-radius: {RADIUS}px;
                outline: none;
                padding: 5px 4px;
            }}
            QAbstractItemView::item {{
                padding: 7px 16px;
                border-radius: 7px;
                min-height: 28px;
                color: {c['text']};
                font-size: 10pt;
                font-weight: 500;
            }}
            QAbstractItemView::item:selected,
            QAbstractItemView::item:focus {{
                background-color: {c['accent']};
                color: white;
                font-weight: 700;
                border-radius: 7px;
            }}
            QAbstractItemView::item:hover:!selected {{
                background-color: {c['surface2']};
                color: {c['accent']};
                border-radius: 7px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 5px;
                border-radius: 3px;
                margin: 6px 3px;
            }}
            QScrollBar::handle:vertical {{
                background: {c['sb_handle']};
                border-radius: 3px;
                min-height: 24px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        # ── 4. Re-mostrar y aplicar máscara redondeada ────────────────────
        popup.show()
        # La máscara se aplica con un pequeño delay para que Qt
        # haya calculado el tamaño definitivo del popup.
        QTimer.singleShot(0, lambda: _apply_mask(popup, RADIUS))
