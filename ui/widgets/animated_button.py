# ui/widgets/animated_button.py
"""
QPushButton con animación suave de color en hover/leave — usa QPropertyAnimation
sobre una Q_PROPERTY de QColor para transiciones reales (no solo QSS).
"""
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QColor


class AnimatedButton(QPushButton):
    """Botón con transición de color animada en hover/leave."""

    def __init__(self, text="", normal_color: str = "#ffffff",
                 hover_color: str = "#007aff", text_color: str = "#1c1c1e",
                 hover_text: str = "#ffffff", border_radius: int = 10,
                 parent=None):
        super().__init__(text, parent)
        self._normal = QColor(normal_color)
        self._hover  = QColor(hover_color)
        self._text_normal = QColor(text_color)
        self._text_hover  = QColor(hover_text)
        self._radius = border_radius

        self._bg = QColor(normal_color)
        self._tc = QColor(text_color)

        self._anim_bg = QPropertyAnimation(self, b"bgColor")
        self._anim_bg.setDuration(160)
        self._anim_bg.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._anim_tc = QPropertyAnimation(self, b"textColor")
        self._anim_tc.setDuration(160)
        self._anim_tc.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._refresh()

    # ── Q_PROPERTY: bgColor ──────────────────────────────────────────────────

    def _get_bg(self) -> QColor:
        return self._bg

    def _set_bg(self, color: QColor):
        self._bg = color
        self._refresh()

    bgColor = Property(QColor, _get_bg, _set_bg)

    # ── Q_PROPERTY: textColor ────────────────────────────────────────────────

    def _get_tc(self) -> QColor:
        return self._tc

    def _set_tc(self, color: QColor):
        self._tc = color
        self._refresh()

    textColor = Property(QColor, _get_tc, _set_tc)

    # ── Style refresh ────────────────────────────────────────────────────────

    def _refresh(self):
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {self._bg.name()};"
            f"  color: {self._tc.name()};"
            f"  border-radius: {self._radius}px;"
            f"  border: 1.5px solid rgba(0,0,0,0.08);"
            f"  padding: 7px 18px;"
            f"  font-weight: 600;"
            f"  font-size: 10pt;"
            f"}}"
            f"QPushButton:disabled {{"
            f"  background-color: #e5e5ea; color: #c7c7cc; border-color: #e5e5ea;"
            f"}}"
        )

    def set_colors(self, normal_color: str, hover_color: str,
                   text_color: str, hover_text: str):
        """Actualiza los colores del botón en caliente."""
        self._normal      = QColor(normal_color)
        self._hover       = QColor(hover_color)
        self._text_normal = QColor(text_color)
        self._text_hover  = QColor(hover_text)
        self._bg = QColor(normal_color)
        self._tc = QColor(text_color)
        self._refresh()

    # ── Hover events ─────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._anim_bg.stop()
        self._anim_bg.setStartValue(self._bg)
        self._anim_bg.setEndValue(self._hover)
        self._anim_bg.start()

        self._anim_tc.stop()
        self._anim_tc.setStartValue(self._tc)
        self._anim_tc.setEndValue(self._text_hover)
        self._anim_tc.start()

        super().enterEvent(event)

    def leaveEvent(self, event):
        self._anim_bg.stop()
        self._anim_bg.setStartValue(self._bg)
        self._anim_bg.setEndValue(self._normal)
        self._anim_bg.start()

        self._anim_tc.stop()
        self._anim_tc.setStartValue(self._tc)
        self._anim_tc.setEndValue(self._text_normal)
        self._anim_tc.start()

        super().leaveEvent(event)
