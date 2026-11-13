import re
from core import version


def test_version_metadata():
    """Garante que a versão segue o padrão SemVer (X.Y.Z) e formata a string corretamente."""
    assert re.match(r"^\d+\.\d+\.\d+$", version.__version__)
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", version.__build_date__)
    assert version.APP_TITLE == "SARCC Enterprise"

    formatted = version.get_version_string()
    assert f"v{version.__version__}" in formatted
    assert version.__build_date__ in formatted