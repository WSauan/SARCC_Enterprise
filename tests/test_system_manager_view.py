from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from gui.views.system_manager_view import (
    safe_int, safe_float, normalize_service_status,
    normalize_printer_status, SysManagerWorker, SystemManagerView
)

_QAPP = QApplication.instance() or QApplication([])


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


def test_normalize_printer_status_handles_online_and_offline():
    """Valida normalização visual do status das impressoras."""
    txt, color = normalize_printer_status("Normal")
    assert txt == "Pronta (Online)"
    assert color == Qt.GlobalColor.green

    txt_off, color_off = normalize_printer_status("Offline")
    assert txt_off == "Offline"
    assert color_off == Qt.GlobalColor.red


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


def test_system_manager_populates_printers_table():
    """Verifica se a aba Impressoras & Spooler preenche a tabela corretamente."""
    fake_repo = MagicMock()
    view = SystemManagerView(exec_repo=fake_repo)

    sample_printers = [
        {
            "Name": "HP LaserJet UTI 01",
            "PortName": "10.8.128.210",
            "DriverName": "HP Universal Printing PCL 6",
            "JobCount": 3,
            "Status": "Normal"
        },
        {
            "Name": "Microsoft Print to PDF",
            "PortName": "PORTPROMPT:",
            "DriverName": "Microsoft Print To PDF",
            "JobCount": 0,
            "Status": "Offline"
        }
    ]
    view.on_worker_finished(sample_printers, "get_printers")

    assert view.tbl_printers.rowCount() == 2
    assert view.tbl_printers.item(0, 0).text() == "HP LaserJet UTI 01"
    assert view.tbl_printers.item(0, 1).text() == "10.8.128.210"
    assert view.tbl_printers.item(0, 4).text() == "Pronta (Online)"
    assert view.tbl_printers.item(1, 4).text() == "Offline"
    view.close()