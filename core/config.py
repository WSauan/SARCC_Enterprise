"""
Configuração central do SARCC.

Fonte única da verdade para:
  - Localização de dados graváveis (BD, logs, credenciais, scripts PS)
  - Constantes de rede (share, portas, timeouts)
  - Variáveis de ambiente lidas em runtime

REGRAS DE LOCALIZAÇÃO DE DADOS
──────────────────────────────
1. Se SARCC_DATA_DIR estiver setada → usa essa pasta (override para testes)
2. Se empacotado (.exe via PyInstaller) → %APPDATA%\\SARCC\\
3. Se em dev (.py direto)             → <raiz do projeto>\\data\\

Isso preserva o comportamento atual em desenvolvimento (nada quebra) e
corrige o comportamento quando empacotado (funciona em Program Files).

RECURSOS vs DADOS
─────────────────
- Recursos (logo, CHANGELOG, templates .ps1) → core.resources.resource_path()
  São READ-ONLY, ficam dentro do bundle/raiz.
- Dados (BD, logs, credenciais) → funções deste módulo.
  São GRAVÁVEIS, ficam em %APPDATA% quando empacotado.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Identidade do aplicativo
# ─────────────────────────────────────────────────────────────────────────────
APP_NAME = "SARCC"
APP_ORGANIZATION = "SARCC"

# ─────────────────────────────────────────────────────────────────────────────
# Compartilhamento de rede (fonte única)
#
# Pode ser sobrescrito via SARCC_SHARE no ambiente — útil para testar
# contra um share diferente sem recompilar.
# ─────────────────────────────────────────────────────────────────────────────
SHARE_ROOT: str = os.environ.get("SARCC_SHARE", r"\\hul-vp-imagem-cc\netshared")
SHARE_SOFTWARE: str = rf"{SHARE_ROOT}\Softwares"
SHARE_DRIVERS: str = rf"{SHARE_ROOT}\Drivers"
SHARE_WINGET: str = rf"{SHARE_ROOT}\Winget"

# ─────────────────────────────────────────────────────────────────────────────
# Portas e protocolos
# ─────────────────────────────────────────────────────────────────────────────
PORT_WINRM_HTTP = 5985
PORT_WINRM_HTTPS = 5986
PORT_SMB = 445
PORT_RDP = 3389
PORT_VNC = 5900
PORT_WOL = 9          # UDP
PORT_ZABBIX = 10050

# ─────────────────────────────────────────────────────────────────────────────
# Timeouts
# ─────────────────────────────────────────────────────────────────────────────
TIMEOUT_DB = 20.0           # sqlite3.connect
TIMEOUT_PORT_PROBE = 1.0    # socket.connect
TIMEOUT_POWERSHELL_LOCAL = 600    # subprocess local (10 min — guarda-chuva)
TIMEOUT_WMI_HOURS = 8       # TODO(Fase 3): reduzir para 30-60 min

# ─────────────────────────────────────────────────────────────────────────────
# Modo de execução
# ─────────────────────────────────────────────────────────────────────────────
def is_dev_mode() -> bool:
    """True se rodando como código-fonte (.py), False se empacotado (.exe)."""
    return not getattr(sys, "frozen", False)


# ─────────────────────────────────────────────────────────────────────────────
# Localização de dados graváveis
# ─────────────────────────────────────────────────────────────────────────────
def get_data_dir() -> Path:
    """Diretório-raiz de dados graváveis do SARCC."""
    # 1. Override explícito (testes, dev customizado)
    env_override = os.environ.get("SARCC_DATA_DIR")
    if env_override:
        return Path(env_override).expanduser().resolve()

    # 2. Empacotado → %APPDATA%\SARCC
    if not is_dev_mode():
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        # Fallback raro (Windows sem APPDATA)
        return Path.home() / APP_NAME

    # 3. Dev → <raiz do projeto>/data
    project_root = Path(__file__).resolve().parent.parent
    return project_root / "data"


def get_logs_dir() -> Path:
    """Diretório dos arquivos de log rotativos."""
    return get_data_dir() / "logs"


def get_db_path() -> Path:
    """Caminho absoluto do banco SQLite."""
    return get_data_dir() / "sarcc.db"


def get_credentials_path() -> Path:
    """Caminho do blob DPAPI (user-scoped, só o mesmo usuário decifra)."""
    return get_data_dir() / "credentials.dat"


def get_ps_scripts_dir() -> Path:
    """Diretório dos scripts PowerShell empacotados como recursos.

    Fase 1 vai migrar os scripts inline para arquivos .ps1.
    Aqui é o ponto de entrada único para localizá-los.
    """
    # Scripts são RECURSO (read-only), não dado. Ficam dentro do bundle.
    from core.resources import resource_path
    return Path(resource_path("ps_scripts"))


# ─────────────────────────────────────────────────────────────────────────────
# Garantia de existência
# ─────────────────────────────────────────────────────────────────────────────
def ensure_dirs() -> None:
    """Cria todos os diretórios graváveis. Idempotente.

    Chamado uma vez no startup (main.py).
    """
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_logs_dir().mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Configurações vindas do ambiente
# ─────────────────────────────────────────────────────────────────────────────
def get_max_threads(default: int = 12) -> int:
    """Lê SARCC_MAX_THREADS do ambiente. Cai para `default` se ausente/inválido."""
    raw = os.environ.get("SARCC_MAX_THREADS", "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value >= 1 else default
    except ValueError:
        return default