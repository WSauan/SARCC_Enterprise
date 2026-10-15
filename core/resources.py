"""
Utilitários para localizar recursos (ícones, docs, CHANGELOG) tanto em dev
quanto empacotado com PyInstaller.
"""

import os
import sys


def resource_path(relative_path: str) -> str:
    """Retorna o caminho absoluto de um recurso empacotado ou em dev.

    Em dev (rodando .py direto): raiz do projeto.
    Em .exe (PyInstaller): pasta _internal/ (sys._MEIPASS).
    """
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)