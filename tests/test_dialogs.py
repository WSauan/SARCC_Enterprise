from PyQt6.QtWidgets import QApplication, QLineEdit
from gui.dialogs.dialogs import CredentialDialog

# Mantém referência global viva durante toda a sessão do pytest para evitar Crash C++ no PyQt6
_QAPP = QApplication.instance() or QApplication([])


def test_credential_dialog_password_visibility_and_accept():
    """Testa alternância de visibilidade da senha e confirmação no CredentialDialog."""
    dlg = CredentialDialog(user_display="EBSERHNET\\adm.wsauan", has_saved=True)

    assert dlg.inp_password.echoMode() == QLineEdit.EchoMode.Password
    assert dlg.chk_remember.isChecked() is True

    dlg._toggle_password_visibility(True)
    assert dlg.inp_password.echoMode() == QLineEdit.EchoMode.Normal

    dlg._toggle_password_visibility(False)
    assert dlg.inp_password.echoMode() == QLineEdit.EchoMode.Password

    dlg.inp_password.setText("MinhaSenha#2026")
    dlg._on_ok()
    assert dlg.password == "MinhaSenha#2026"
    assert dlg.remember is True
    dlg.close()