"""
Utilitários para localizar recursos (ícones, docs, CHANGELOG, scripts) tanto em dev
quanto empacotado com PyInstaller.
"""

import os
import sys


def resource_path(relative_path: str) -> str:
    """Retorna o caminho absoluto de um recurso empacotado ou em dev.

    Em .exe (PyInstaller):
      1º Verifica se existe o ficheiro externo ao lado do executável (permite atualização rápida).
      2º Fallback para a pasta interna descompactada pelo PyInstaller (sys._MEIPASS).
    Em dev (rodando .py direto):
      Raiz do projeto.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        external_candidate = os.path.join(exe_dir, relative_path)
        if os.path.exists(external_candidate):
            return external_candidate
        base = getattr(sys, "_MEIPASS", exe_dir)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)
