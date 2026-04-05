##ALERTRAN_SGD V.8.0
##Cualquier Pull Request notificar por teams para pronta respuesta eduar fabian vargas

##importacion de librerias IMPORTANTE EN ENTORNO EMPRESARIAN RESTRINGE PANDAS.

import sys
import asyncio
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
import qasync

from ui.main_window import VentanaPrincipal


def _app_icon() -> QIcon:
    """Carga el icono desde assets/ o desde el bundle de PyInstaller."""
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
    for name in ('alertran.ico', 'alertran_icon.png'):
        p = base / 'assets' / name
        if p.exists():
            return QIcon(str(p))
    return QIcon()


def main():
    """Función principal"""
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    app.setStyle('Fusion')
    app.setWindowIcon(_app_icon())

    ventana = VentanaPrincipal()
    ventana.show()

    with loop:
        sys.exit(loop.run_forever())

if __name__ == "__main__":
    main()