from core import version


def test_version_metadata():
    """Garante que a versão está definida e formatada corretamente."""
    assert version.__version__ == "2.9.0"
    assert "v2.9.0" in version.get_version_string()