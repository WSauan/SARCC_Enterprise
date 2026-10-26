import os
import sys
from pathlib import Path

APP_NAME = "SARCC"
APP_ORGANIZATION = "SARCC"

SHARE_ROOT: str = os.environ.get("SARCC_SHARE", r"\\hul-vp-imagem-cc\netshared")
SHARE_SOFTWARE: str = rf"{SHARE_ROOT}\Softwares"
SHARE_DRIVERS: str = rf"{SHARE_ROOT}\Drivers"
SHARE_WINGET: str = rf"{SHARE_ROOT}\Winget"

PORT_WINRM_HTTP = 5985
PORT_WINRM_HTTPS = 5986
PORT_SMB = 445
PORT_RDP = 3389
PORT_VNC = 5900
PORT_WOL = 9
PORT_ZABBIX = 10050

TIMEOUT_DB = 20.0
TIMEOUT_PORT_PROBE = 1.0
TIMEOUT_POWERSHELL_LOCAL = 600
TIMEOUT_WMI_HOURS = 8

def is_dev_mode() -> bool:
    return not getattr(sys, "frozen", False)

def get_data_dir() -> Path:
    env_override = os.environ.get("SARCC_DATA_DIR")
    if env_override:
        return Path(env_override).expanduser().resolve()
    if not is_dev_mode():
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / APP_NAME
        return Path.home() / APP_NAME
    project_root = Path(__file__).resolve().parent.parent
    return project_root / "data"

def get_logs_dir() -> Path: return get_data_dir() / "logs"
def get_db_path() -> Path: return get_data_dir() / "sarcc.db"
def get_credentials_path() -> Path: return get_data_dir() / "credentials.dat"

def get_ps_scripts_dir() -> Path:
    from core.resources import resource_path
    return Path(resource_path(os.path.join("core", "scripts")))

def ensure_dirs() -> None:
    get_data_dir().mkdir(parents=True, exist_ok=True)
    get_logs_dir().mkdir(parents=True, exist_ok=True)

def get_max_threads(default: int = 12) -> int:
    raw = os.environ.get("SARCC_MAX_THREADS", "").strip()
    if not raw: return default
    try:
        value = int(raw)
        return value if value >= 1 else default
    except ValueError:
        return default