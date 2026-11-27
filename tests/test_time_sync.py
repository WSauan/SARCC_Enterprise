from gui.views.system_manager_view import SysManagerWorker


def test_sync_time_resync_mode(mocker):
    """Garante que o worker monta o script com o modo resync."""
    worker = SysManagerWorker("HUL-WK-TESTE", "sync_time", {"mode": "resync"})

    # Mock para não ler o arquivo real e gastar tempo
    mocker.patch("gui.views.system_manager_view.load_ps_template", return_value="script_mocado")

    script = worker._build_script()

    # O worker deve chamar o load_ps_template com a categoria certa e o modo correto
    from gui.views.system_manager_view import load_ps_template as mock_load
    mock_load.assert_called_once_with("system_manager", "sync_time", mode="resync")
    assert script == "script_mocado"

def test_sync_time_reset_mode(mocker):
    """Garante que o worker monta o script com o modo reset."""
    worker = SysManagerWorker("HUL-WK-TESTE", "sync_time", {"mode": "reset"})
    mocker.patch("gui.views.system_manager_view.load_ps_template", return_value="script_mocado")

    script = worker._build_script()

    from gui.views.system_manager_view import load_ps_template as mock_load
    mock_load.assert_called_once_with("system_manager", "sync_time", mode="reset")
    assert script == "script_mocado"
