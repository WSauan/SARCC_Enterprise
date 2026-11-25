"""
Fonte única de verdade para a versão e metadados do SARCC Enterprise.
"""

__version__ = "3.0.0"
__build_date__ = "2026-11-25"
APP_TITLE = "SARCC Enterprise"


def get_version_string() -> str:
    """Retorna a versão formatada (ex: 'v2.12.0 (2026-11-19)')."""
    return f"v{__version__} ({__build_date__})"
