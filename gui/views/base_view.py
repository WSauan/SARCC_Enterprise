"""
BaseView — classe base para todas as views do SARCC.

Centraliza funcionalidades comuns:
- Referência à MainWindow (para acesso a serviços globais)
- Utilitário `_force_uppercase` para campos de alvo (hostname/IP)

Views que herdam de BaseView podem usar `self.inp_target` ou
`self.target_input` — ambos são detectados automaticamente.
"""

from PyQt6.QtWidgets import QWidget


class BaseView(QWidget):
    """Classe base para todas as views do SARCC. Não instancie diretamente."""

    def __init__(self, main_window_ref=None):
        super().__init__()
        self.main_window = main_window_ref

    # ------------------------------------------------------------------
    # Utilitários
    # ------------------------------------------------------------------
    def _get_target_field(self):
        """Retorna o campo de alvo da view.

        Algumas views usam `self.inp_target`, outras `self.target_input`.
        O método retorna o que existir (ou None se nenhum).
        """
        return getattr(self, "inp_target", None) or getattr(self, "target_input", None)

    def _force_uppercase(self, text):
        """Força o texto do campo alvo para MAIÚSCULAS preservando o cursor."""
        upper_text = text.upper()
        if text != upper_text:
            field = self._get_target_field()
            if field is None:
                return
            cursor_pos = field.cursorPosition()
            field.setText(upper_text)
            field.setCursorPosition(cursor_pos)