from PyQt6.QtCore import Qt
from gui.views.shell_view import format_console_html
from gui.views.system_manager_view import (
    safe_int, safe_float, normalize_service_status, SysManagerWorker
)


def test_format_console_html_escapes_angle_brackets_and_repairs_mojibake():
    """Garante que tags <...> do PowerShell não sejam engolidas pelo QTextEdit.insertHtml."""
    raw = "CÃ¢mera <System.String> & <# Comentario #>\nLinha 2"
    html = format_console_html(raw)
    assert "Câmera" in html
    assert "&lt;System.String&gt;" in html
    assert "&amp;" in html
    assert "&lt;# Comentario #&gt;<br>Linha 2" in html


def test_safe_int_and_safe_float_handle_none_and_commas():
    """Evita crash quando o Get-Process do Windows retorna CPU=None ou decimais com vírgula."""
    assert safe_int(None) == 0
    assert safe_int("") == 0
    assert safe_int("1234") == 1234

    assert safe_float(None) == 0.0
    assert safe_float("") == 0.0
    assert safe_float("15,75") == 15.75
    assert safe_float(42.129) == 42.13


def test_normalize_service_status_handles_enum_and_strings():
    """Valida tradução e cores para status de serviços do Windows."""
    txt, color = normalize_service_status("Running")
    assert txt == "Em Execução"
    assert color == Qt.GlobalColor.green

    txt2, color2 = normalize_service_status(4)
    assert txt2 == "Em Execução"
    assert color2 == Qt.GlobalColor.green

    txt3, color3 = normalize_service_status("Stopped")
    assert txt3 == "Parado"
    assert color3 == Qt.GlobalColor.red


def test_sys_manager_worker_preserves_direct_action_json(mocker):
    """Garante que kill_process e manage_service entregam a mensagem real mesmo sem chave 'Data'."""
    mocker.patch("gui.views.system_manager_view.load_ps_template", return_value="Stop-Process")
    mock_conn_cls = mocker.patch("gui.views.system_manager_view.RemoteConnectionManager")
    mock_conn_cls.return_value.execute_script.return_value = {
        "status": "Sucesso",
        "log_saida": '{"StatusFinal": "SUCESSO", "Mensagem": "Processo notepad (123) encerrado."}',
        "json_data": {"StatusFinal": "SUCESSO", "Mensagem": "Processo notepad (123) encerrado."}
    }

    worker = SysManagerWorker("HUL-WK-TESTE", "kill_process", {"pid": 123, "name": "notepad"})
    results = []
    worker.finished.connect(lambda data, act: results.append((data, act)))
    worker.run()

    assert len(results) == 1
    data_list, action = results[0]
    assert action == "kill_process"
    assert len(data_list) == 1
    assert data_list[0]["Mensagem"] == "Processo notepad (123) encerrado."