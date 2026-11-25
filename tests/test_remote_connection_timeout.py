import pytest
import subprocess
from unittest.mock import MagicMock
from core.remote_connection import RemoteConnectionManager

def test_execute_script_uses_custom_timeout(mocker):
    """Garante que o timeout customizado é repassado para o subprocess."""
    conn = RemoteConnectionManager()
    
    mock_run = mocker.patch("core.remote_connection.subprocess.run")
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="powershell.exe", timeout=3600)
    
    mocker.patch.object(conn, "probe_host", return_value={"reachable": True, "winrm_open": True, "smb_open": True, "ping_ok": True})
    
    res = conn.execute_script("HUL-WK-TESTE", "DISM /Online", timeout_seconds=3600)
    
    # Verifica se o timeout foi aplicado na chamada do subprocess
    args, kwargs = mock_run.call_args
    assert kwargs.get("timeout") == 3600
    assert "3600s" in res["log_saida"]