import sys
import queue
from unittest.mock import MagicMock
from core import version, resources
from core.ps_loader import load_ps_template
from core.task_queue import TaskWorker, WorkerSignals


def test_version_metadata():
    """Garante que a versão está definida e formatada corretamente."""
    assert version.__version__ == "2.9.0"
    assert "v2.9.0" in version.get_version_string()


def test_resource_path_prioritizes_external_file_when_frozen(tmp_path, monkeypatch):
    """Em modo .exe (frozen), deve priorizar ficheiros ao lado do executável antes do _MEIPASS."""
    exe_dir = tmp_path / "exe_folder"
    meipass_dir = tmp_path / "meipass_folder"
    exe_dir.mkdir()
    meipass_dir.mkdir()

    external_logo = exe_dir / "logo.ico"
    external_logo.write_bytes(b"ICON")
    internal_file = meipass_dir / "interno.txt"
    internal_file.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "SARCC.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass_dir), raising=False)

    assert resources.resource_path("logo.ico") == str(external_logo)
    assert resources.resource_path("interno.txt") == str(internal_file)


def test_ps_loader_strips_utf8_bom_and_converts_booleans(tmp_path, monkeypatch):
    """Verifica se o ps_loader remove o carácter invisível UTF-8 BOM e converte bool para $true/$false."""
    cat_dir = tmp_path / "teste_cat"
    cat_dir.mkdir()
    ps1_file = cat_dir / "script_bom.ps1"
    ps1_file.write_bytes("$Forcar = {{forcar}}".encode("utf-8-sig"))

    monkeypatch.setattr("core.ps_loader.get_ps_scripts_dir", lambda: tmp_path)

    result = load_ps_template("teste_cat", "script_bom", forcar=True)
    assert not result.startswith("\ufeff")
    assert result == "$Forcar = $true"


def test_task_worker_extracts_detailed_error_when_connection_fails(mocker):
    """Garante que falhas de WinRM/WMI enviam o log detalhado para o sinal de erro em vez de texto genérico."""
    mock_conn_class = mocker.patch("core.task_queue.RemoteConnectionManager")
    mock_conn = mock_conn_class.return_value
    mock_conn.execute_script.return_value = {
        "status": "Erro Fatal",
        "log_saida": "WinRM (Primário): Porta 5985 fechada\nWMI (Secundário): Acesso Negado",
        "json_data": {}
    }

    mock_db = MagicMock()
    test_q = queue.Queue()
    signals = WorkerSignals()
    captured_errors = []
    signals.error.connect(lambda pc, err: captured_errors.append((pc, err)))

    test_q.put(("HUL-WK-OFFLINE", "Teste Falha", "Get-Date", "Teste", None, None, signals))
    test_q.put(None)

    worker = TaskWorker(test_q, mock_db)
    worker.run()

    assert len(captured_errors) == 1
    assert captured_errors[0][0] == "HUL-WK-OFFLINE"
    assert "Acesso Negado" in captured_errors[0][1]