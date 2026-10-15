"""Dialogs customizados do SARCC."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QMessageBox,
)
from PyQt6.QtCore import Qt


class CredentialDialog(QDialog):
    """Dialog de senha com opção de lembrar entre sessões via DPAPI."""

    def __init__(self, user_display: str, has_saved: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cofre de Autenticação")
        self.setModal(True)
        self.setMinimumWidth(440)

        self.password = None
        self.remember = has_saved

        self._setup_ui(user_display, has_saved)

    def _setup_ui(self, user_display: str, has_saved: bool):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        titulo = QLabel("<b>Autenticação necessária</b>")
        titulo.setStyleSheet("font-size: 15px;")
        layout.addWidget(titulo)

        info = QLabel(
            "Este script requer acesso a recursos de rede.<br>"
            f"<span style='color: #888;'>Usuário: <b>{user_display}</b></span>"
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.inp_password = QLineEdit()
        self.inp_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.inp_password.setFixedHeight(32)
        self.inp_password.setPlaceholderText("Senha do AD")
        self.inp_password.setStyleSheet("padding: 0 10px;")
        layout.addWidget(self.inp_password)

        self.chk_remember = QCheckBox(
            "💾 Lembrar senha entre sessões (criptografada com DPAPI)"
        )
        self.chk_remember.setToolTip(
            "A senha é cifrada com a chave do SEU usuário Windows.\n"
            "Só pode ser decifrada na MESMA máquina com o MESMO usuário.\n"
            "Limpe a qualquer momento pelo botão na sidebar."
        )
        self.chk_remember.setChecked(has_saved)
        layout.addWidget(self.chk_remember)

        botoes = QHBoxLayout()
        botoes.addStretch()

        btn_cancel = QPushButton("Cancelar")
        btn_cancel.setFixedHeight(32)
        btn_cancel.clicked.connect(self.reject)
        botoes.addWidget(btn_cancel)

        btn_ok = QPushButton("OK")
        btn_ok.setFixedHeight(32)
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_ok)
        botoes.addWidget(btn_ok)

        layout.addLayout(botoes)
        self.inp_password.setFocus()

    def _on_ok(self):
        senha = self.inp_password.text().strip()
        if not senha:
            QMessageBox.warning(self, "Aviso", "A senha não pode estar vazia.")
            return
        self.password = senha
        self.remember = self.chk_remember.isChecked()
        self.accept()