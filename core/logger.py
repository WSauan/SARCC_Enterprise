"""
Configuração central de logging do SARCC.

Uso:
    from core.logger import get_logger
    log = get_logger(__name__)
    log.info("mensagem")
    log.error("algo falhou", exc_info=True)

Saída:
    - Console (só WARNING+ por padrão, para não poluir o dev)
    - Arquivo rotativo em data/logs/sarcc.log (10 MB × 5 backups)
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler


from core.config import get_logs_dir

_LOG_DIR = get_logs_dir()
_LOG_FILE = _LOG_DIR / "sarcc.log"

_configured = False


def _configure_root_logger():
    """Configura o logger raiz uma única vez (idempotente)."""
    global _configured
    if _configured:
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("sarcc")
    root.setLevel(logging.DEBUG)
    root.propagate = False  # não deixa o Python duplicar

    # ---- Handler de arquivo (rotativo) ----
    file_handler = RotatingFileHandler(
        _LOG_FILE,
        maxBytes=10 * 1024 * 1024,   # 10 MB por arquivo
        backupCount=5,               # mantém 5 arquivos .1 .2 .3 .4 .5
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] [%(name)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)
    root.addHandler(file_handler)

    # ---- Handler de console (só WARNING+ para não poluir dev) ----
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.WARNING)

    console_fmt = logging.Formatter(
        "[%(levelname)s] %(name)s: %(message)s"
    )
    console_handler.setFormatter(console_fmt)
    root.addHandler(console_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger filho configurado para o SARCC.

    Args:
        name: normalmente `__name__` (ex.: 'gui.views.software_view').

    Returns:
        logging.Logger já pronto para uso.
    """
    _configure_root_logger()
    # Prefixa com 'sarcc.' para cair sob o logger raiz do projeto
    if not name.startswith("sarcc."):
        name = f"sarcc.{name}"
    return logging.getLogger(name)