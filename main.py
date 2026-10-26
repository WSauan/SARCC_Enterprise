import sys
import os
import qdarktheme
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication
from gui.app_window import MainWindow
from core.logger import get_logger
from core.resources import resource_path

log = get_logger(__name__)

def main():
    # Garante que os diretórios graváveis existem ANTES de qualquer
    # import de logger/database que possa falhar.
    from core.config import ensure_dirs
    ensure_dirs()

    app = QApplication(sys.argv)

    # --- Ícone da janela + taskbar ---
    icon_path = resource_path("logo.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
        log.info(f"Ícone carregado: {icon_path}")
    else:
        log.warning(f"Ícone não encontrado em {icon_path} — usando padrão do Qt")

    log.info("=" * 60)
    log.info("SARCC Enterprise v2.7.0 — Iniciando aplicação")
    log.info("=" * 60)

    # Aplica o tema escuro moderno
    app.setStyleSheet(qdarktheme.load_stylesheet("dark"))

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    log.info("SARCC Enterprise v2.7.0 — Encerrando aplicação")
    log.info("=" * 60)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()