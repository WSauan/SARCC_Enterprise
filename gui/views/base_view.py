"""
BaseView — classe base para todas as views do SARCC.

Centraliza funcionalidades comuns:
- Referência à MainWindow (para acesso a serviços globais)
- Utilitário `_force_uppercase` para campos de alvo (hostname/IP)
- Leitura segura de ficheiros de texto com fallback de encoding (UTF-8-SIG / CP1252)
"""

from pathlib import Path

from PyQt6.QtWidgets import QWidget


def read_text_file_safe(file_path: str | Path) -> str:
    """Lê um ficheiro de texto removendo BOM UTF-8 e com fallback automático para CP1252 (ANSI)."""
    raw = Path(file_path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin1"):
        try:
            return raw.decode(enc).lstrip("\ufeff")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").lstrip("\ufeff")


def sanitize_filename(name: str, default: str = "Arquivo_SARCC") -> str:
    """Remove caracteres inválidos para nomes de ficheiro no Windows."""
    if not name or not name.strip():
        return default
    cleaned = "".join(
        "-" if c in '<>:"/\\|?*' else c
        for c in name.strip()
        if c.isprintable()
    )
    cleaned = cleaned.strip(" .")
    return cleaned if cleaned else default


class BaseView(QWidget):
    """Classe base para todas as views do SARCC. Não instancie diretamente."""

    def __init__(self, main_window_ref=None):
        super().__init__()
        self.main_window = main_window_ref

    def _get_target_field(self):
        """Retorna o campo de alvo da view (`self.inp_target` ou `self.target_input`)."""
        return getattr(self, "inp_target", None) or getattr(self, "target_input", None)

    def _force_uppercase(self, text: str):
        """Força o texto do campo alvo para MAIÚSCULAS preservando a posição do cursor e sem reemitir sinal."""
        upper_text = text.upper()
        if text != upper_text:
            field = self._get_target_field()
            if field is None:
                return
            cursor_pos = field.cursorPosition()
            field.blockSignals(True)
            field.setText(upper_text)
            field.setCursorPosition(cursor_pos)
            field.blockSignals(False)
