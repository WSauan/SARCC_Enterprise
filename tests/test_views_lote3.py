import sys
from PyQt6.QtWidgets import QApplication, QLineEdit
from core.version import __version__
from gui.views.help_view import APP_VERSION, strip_basic_html
from gui.dialogs.dialogs import CredentialDialog


def _get_qapp():
    return QApplication.instance() or QApplication(sys.argv)


def test_help_view_version_is_synced_with_core_version():
    """Garante que a versão exibida na aba Sobre segue core/version.py."""
    assert APP_VERSION == __version__


def test_strip_basic_html_cleans_firewall_documentation():
    """Valida a remoção de tags HTML ao copiar a documentação de firewall."""
    raw = "<b>• WinRM</b><br><i>Nota de Segurança</i><br/>Porta 5985"
    clean = strip_basic_html(raw)
    assert clean == "• WinRM\nNota de Segurança\nPorta 5985"


def test_credential_dialog_password_visibility_and_accept():
    """Testa alternância de visibilidade da senha e confirmação no CredentialDialog."""
    _get_qapp()
    dlg = CredentialDialog(user_display="EBSERHNET\\adm.wsauan", has_saved=True)

    assert dlg.inp_password.echoMode() == QLineEdit.EchoMode.Password
    assert dlg.chk_remember.isChecked() is True

    dlg.btn_toggle_pwd.setChecked(True)
    assert dlg.inp_password.echoMode() == QLineEdit.EchoMode.Normal

    dlg.btn_toggle_pwd.setChecked(False)
    assert dlg.inp_password.echoMode() == QLineEdit.EchoMode.Password

    dlg.inp_password.setText("MinhaSenha#2026")
    dlg._on_ok()
    assert dlg.password == "MinhaSenha#2026"
    assert dlg.remember is True