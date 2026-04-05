# ui/login_window.py
"""
Ventana de inicio de sesión
"""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout, QWidget, QCheckBox, QFrame
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt
from utils import theme

class LoginWindow(QDialog):
    """Ventana de login de ALERTRAN"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🔐 Iniciar Sesión - ALERTRAN")
        self.setMinimumWidth(400)
        self.setModal(True)
        
        self._setup_ui()
        self._setup_styles()
        from utils import theme
        theme.signals.changed.connect(self._setup_styles)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)
        
        titulo = QLabel("🔐 INICIAR SESIÓN")
        titulo.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        titulo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(titulo)
        
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        self.usuario_input = QLineEdit()
        self.usuario_input.setPlaceholderText("Ingrese su usuario")
        self.usuario_input.setMinimumHeight(35)
        form_layout.addRow("👤 Usuario:", self.usuario_input)
        
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("Ingrese su contraseña")
        self.password_input.setMinimumHeight(35)
        form_layout.addRow("🔒 Contraseña:", self.password_input)
        
        layout.addWidget(form_widget)

        self.recordar_check = QCheckBox("🔒 Recordar credenciales")
        self.recordar_check.setStyleSheet(
            "QCheckBox { color: #636366; font-size: 10pt; spacing: 6px; }"
            "QCheckBox::indicator { width: 16px; height: 16px; }"
        )
        layout.addWidget(self.recordar_check)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(15)
        
        self.btn_login = QPushButton("✅ INICIAR SESIÓN")
        self.btn_login.clicked.connect(self.accept)
        
        self.btn_cancel = QPushButton("❌ CANCELAR")
        self.btn_cancel.clicked.connect(self.reject)
        
        button_layout.addWidget(self.btn_login)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
        self.usuario_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.accept)

    def _setup_styles(self):
        c = theme.colors()
        self.setStyleSheet(theme.base_stylesheet() + f"""
            QDialog {{ background-color: {c['bg']}; }}
            QLabel {{ font-size: 10pt; color: {c['text2']}; }}
            QLineEdit {{
                padding: 9px 14px;
                border: 1.5px solid {c['input_border']};
                border-radius: 10px;
                font-size: 10.5pt;
                background-color: {c['input_bg']};
                color: {c['text']};
                min-height: 36px;
            }}
            QLineEdit:focus {{
                border: 2px solid {c['accent']};
                background-color: {c['surface']};
            }}
            QLineEdit:hover:!focus {{ border-color: {c['border_strong']}; }}
            QPushButton {{
                font-weight: 700;
                padding: 11px;
                border-radius: 10px;
                font-size: 10.5pt;
                min-width: 150px;
                min-height: 42px;
            }}
            QPushButton#btn_login {{
                background-color: {c['accent']};
                color: white;
                border: none;
            }}
            QPushButton#btn_login:hover {{ background-color: {c['accent_hover']}; color: white; }}
            QPushButton#btn_login:pressed {{ background-color: {c['accent_press']}; color: white; }}
            QPushButton#btn_cancel {{
                background-color: transparent;
                color: {c['error']};
                border: 1.5px solid {c['error']};
            }}
            QPushButton#btn_cancel:hover {{ background-color: {c['error']}; color: white; }}
            QPushButton#btn_cancel:pressed {{ background-color: {c['error_bg']}; color: {c['error']}; }}
        """)
        
        self.btn_login.setObjectName("btn_login")
        self.btn_cancel.setObjectName("btn_cancel")
    
    def get_credentials(self):
        return self.usuario_input.text(), self.password_input.text()