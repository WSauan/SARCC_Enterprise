import sys
import os
import ctypes
import qdarktheme
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from core.config import ensure_dirs
from core.version import __version__
from core.resources import resource_path


def _set_windows_app_id():
    """Garante que o ícone personalizado do SARCC apareça na barra de tarefas do Windows."""
    if sys.platform == "win32":
        try:
            app_id = f"EBSERH.SARCC.Enterprise.{__version__}"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass


def _install_exception_hook(log):
    """Regista qualquer exceção não tratada no sarcc.log para auditoria de falhas."""
    old_hook = sys.excepthook

    def _custom_hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            old_hook(exc_type, exc_value, exc_tb)
            return
        log.critical("Exceção não tratada na interface gráfica:", exc_info=(exc_type, exc_value, exc_tb))
        old_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = _custom_hook


def main():
    ensure_dirs()
    _set_windows_app_id()

    from core.logger import get_logger
    from gui.app_window import MainWindow

    log = get_logger(__name__)
    _install_exception_hook(log)

    app = QApplication(sys.argv)

    icon_path = resource_path("logo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        log.info(f"Ícone carregado: {icon_path}")
    else:
        log.warning(f"Ícone não encontrado em {icon_path} — usando padrão do Qt")

    log.info("=" * 60)
    log.info(f"SARCC Enterprise v{__version__} — Iniciando aplicação")
    log.info("=" * 60)

    app.setStyleSheet(qdarktheme.load_stylesheet("dark"))

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    log.info(f"SARCC Enterprise v{__version__} — Encerrando aplicação")
    log.info("=" * 60)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()