from core.version import __version__
from gui.views.help_view import APP_VERSION, strip_basic_html


def test_help_view_version_is_synced_with_core_version():
    """Garante que a versão exibida na aba Sobre segue core/version.py."""
    assert APP_VERSION == __version__


def test_strip_basic_html_cleans_firewall_documentation():
    """Valida a remoção de tags HTML ao copiar a documentação de firewall."""
    raw = "<b>• WinRM</b><br><i>Nota de Segurança</i><br/>Porta 5985"
    clean = strip_basic_html(raw)
    assert clean == "• WinRM\nNota de Segurança\nPorta 5985"