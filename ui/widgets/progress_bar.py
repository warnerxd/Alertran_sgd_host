# ui/widgets/progress_bar.py
"""
Barra de progreso personalizada estilo Mac
"""
from PySide6.QtWidgets import QProgressBar
from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Property, Qt
from PySide6.QtGui import QPainter, QLinearGradient, QBrush, QPen, QColor, QFont

class MacProgressBar(QProgressBar):
    """Barra de progreso con animación estilo Mac"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(25)
        self.setMaximumHeight(25)
        self.setTextVisible(False)
        self._animation = QPropertyAnimation(self, b"value")
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.setDuration(300)
        
    def setValue(self, value):
        if self._animation.state() == QPropertyAnimation.State.Running:
            self._animation.stop()
        
        self._animation.setStartValue(self.value())
        self._animation.setEndValue(value)
        self._animation.start()
        super().setValue(value)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        rect_width = rect.width()
        rect_height = rect.height()
        
        # Fondo
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(220, 220, 220)))
        painter.drawRoundedRect(rect, 8, 8)
        
        # Progreso
        progress = self.value() / 100.0
        progress_width = int(rect_width * progress)
        
        if progress_width > 0:
            gradient = QLinearGradient(0, 0, progress_width, 0)
            gradient.setColorAt(0, QColor(10, 132, 255))
            gradient.setColorAt(0.7, QColor(0, 100, 255))
            gradient.setColorAt(1, QColor(0, 85, 255))
            
            progress_rect = rect.adjusted(0, 0, -(rect_width - progress_width), 0)
            painter.setBrush(QBrush(gradient))
            painter.drawRoundedRect(progress_rect, 8, 8)
            
            # Highlight
            highlight_rect = progress_rect.adjusted(0, 0, 0, -rect_height//2)
            highlight_gradient = QLinearGradient(0, 0, 0, highlight_rect.height())
            highlight_gradient.setColorAt(0, QColor(255, 255, 255, 70))
            highlight_gradient.setColorAt(1, QColor(255, 255, 255, 20))
            painter.setBrush(QBrush(highlight_gradient))
            painter.drawRoundedRect(highlight_rect, 8, 8)
            
            # Sombra
            shadow_rect = progress_rect.adjusted(0, rect_height//2, 0, 0)
            shadow_gradient = QLinearGradient(0, 0, 0, shadow_rect.height())
            shadow_gradient.setColorAt(0, QColor(0, 0, 0, 20))
            shadow_gradient.setColorAt(1, QColor(0, 0, 0, 5))
            painter.setBrush(QBrush(shadow_gradient))
            painter.drawRoundedRect(shadow_rect, 8, 8)
        
        # Borde
        painter.setPen(QPen(QColor(150, 150, 150), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 8, 8)
        
        # Texto
        if self.value() > 0:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
            text = f"{self.value()}%"
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)