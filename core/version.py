"""
Fonte única de verdade para a versão e metadados do SARCC Enterprise.
"""

__version__ = "2.9.1"
__build_date__ = "2026-11-13"
APP_TITLE = "SARCC Enterprise"


def get_version_string() -> str:
    """Retorna a versão formatada (ex: 'v2.9.1 (2026-11-13)')."""
    return f"v{__version__} ({__build_date__})"