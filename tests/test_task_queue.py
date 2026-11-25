import base64
import queue
from unittest.mock import MagicMock

from core.task_queue import TaskWorker, WorkerSignals


def test_task_worker_base64_injection(mocker):
    """Verifica se credenciais e scripts grandes são injetados em Base64 pelo TaskWorker."""
    mock_conn_class = mocker.patch("core.task_queue.RemoteConnectionManager")
    mock_conn = mock_conn_class.return_value
    mock_conn.execute_script.return_value = {
        "status": "Sucesso",
        "log_saida": '{"StatusFinal": "SUCESSO"}',
        "json_data": {"StatusFinal": "SUCESSO"}
    }

    mock_db = MagicMock()
    test_q = queue.Queue()
    signals = WorkerSignals()

    creds = {"user": "admin", "pass": "1234", "vnc_pass": "5678"}
    script_template = "User=[[ADMIN_USER]] Pass=[[ADMIN_PASS]] VNC=[[VNC_PASS]] Payload={{script_b64}}"

    # Adicionado o timeout 300 no final da tupla
    test_q.put(("HUL-WK-01", "Teste Creds", script_template, "ModuloTeste", creds, "PAYLOAD_B64", signals, 300))
    test_q.put(None)

    worker = TaskWorker(test_q, mock_db)
    worker.run()

    expected_user = base64.b64encode(b"admin").decode("ascii")
    expected_pass = base64.b64encode(b"1234").decode("ascii")
    expected_vnc = base64.b64encode(b"5678").decode("ascii")
    expected_script = f"User={expected_user} Pass={expected_pass} VNC={expected_vnc} Payload=PAYLOAD_B64"

    # CORRIGIDO AQUI: Espera o timeout_seconds=300 no final da chamada
    mock_conn.execute_script.assert_called_once_with("HUL-WK-01", expected_script, timeout_seconds=300)


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

    # Adicionado o timeout 300 no final da tupla
    test_q.put(("HUL-WK-OFFLINE", "Teste Falha", "Get-Date", "Teste", None, None, signals, 300))
    test_q.put(None)

    worker = TaskWorker(test_q, mock_db)
    worker.run()

    assert len(captured_errors) == 1
    assert captured_errors[0][0] == "HUL-WK-OFFLINE"
    assert "Acesso Negado" in captured_errors[0][1]
