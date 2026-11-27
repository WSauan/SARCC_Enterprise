from gui.views.system_manager_view import SysManagerWorker


def test_bitlocker_worker_builds_script(mocker):
    """Garante que o worker monta o script de BitLocker corretamente."""
    worker = SysManagerWorker("HUL-WK-TESTE", "get_bitlocker")

    # Mock para não ler o arquivo real
    mocker.patch("gui.views.system_manager_view.load_ps_template", return_value="script_mocado")

    script = worker._build_script()

    from gui.views.system_manager_view import load_ps_template as mock_load
    mock_load.assert_called_once_with("system_manager", "get_bitlocker")
    assert script == "script_mocado"
