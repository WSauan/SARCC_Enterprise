import pytest
from core.remote_connection import RemoteConnectionManager


def test_smart_decode_preserves_utf8_accents():
    """Garante que o _smart_decode mantém acentos UTF-8 intactos (sem cair no cp850 por engano)."""
    conn = RemoteConnectionManager()
    original = "Câmera do Windows — Operação concluída com êxito"
    raw_utf8 = original.encode("utf-8")

    decoded = conn._smart_decode(raw_utf8)
    assert decoded == original


def test_process_output_extracts_last_valid_json_line():
    """Verifica se o _process_output ignora avisos iniciais e extrai o JSON final."""
    conn = RemoteConnectionManager()
    stdout = 'Aviso de inicializacao...\n{"StatusFinal": "SUCESSO", "Computador": "HUL-WK-TESTE"}'
    res = conn._process_output(stdout, "", 0)

    assert res["status"] == "Sucesso"
    assert res["json_data"]["StatusFinal"] == "SUCESSO"
    assert res["json_data"]["Computador"] == "HUL-WK-TESTE"


def test_execute_script_falls_back_to_wmi_when_winrm_fails(mocker):
    """Garante que se o WinRM falhar na porta 5985, o WMI assume automaticamente."""
    conn = RemoteConnectionManager()
    mocker.patch.object(conn, "_is_port_open", return_value=True)
    mocker.patch.object(conn, "_run_native_remoting", side_effect=Exception("WinRM bloqueado"))
    mock_wmi = mocker.patch.object(
        conn, "_run_wmi",
        return_value={"status": "Sucesso", "log_saida": "OK via WMI", "json_data": {"StatusFinal": "SUCESSO"}}
    )

    res = conn.execute_script("HUL-WK-REMOTO", "Get-Date")
    mock_wmi.assert_called_once()
    assert res["status"] == "Sucesso"
    assert "OK via WMI" in res["log_saida"]


def test_localizar_vnc_viewer_finds_portable_binary(tmp_path, mocker):
    """Verifica se localizar_vnc_viewer prioriza o executável portátil na pasta do SARCC."""
    fake_vnc = tmp_path / "vncviewer.exe"
    fake_vnc.write_bytes(b"MZ")

    conn = RemoteConnectionManager()
    mocker.patch.object(conn, "_get_search_dirs", return_value=[str(tmp_path)])

    found = conn.localizar_vnc_viewer()
    assert found == str(fake_vnc)


def test_abrir_anydesk_raises_filenotfound_when_missing(mocker):
    """Garante que abrir_anydesk levanta FileNotFoundError quando não instalado, acionando o fallback da UI."""
    conn = RemoteConnectionManager()
    mocker.patch.object(conn, "localizar_anydesk", return_value=None)

    with pytest.raises(FileNotFoundError):
        conn.abrir_anydesk("123456789")


def test_abrir_acesso_remoto_includes_options_vnc_when_available(tmp_path, mocker):
    """Verifica se o VNC Viewer recebe automaticamente o ficheiro -config options.vnc quando presente."""
    fake_vnc = tmp_path / "vncviewer.exe"
    fake_vnc.write_bytes(b"MZ")
    fake_opt = tmp_path / "options.vnc"
    fake_opt.write_text("[connection]", encoding="utf-8")

    conn = RemoteConnectionManager()
    mocker.patch.object(conn, "_get_search_dirs", return_value=[str(tmp_path)])
    mock_popen = mocker.patch("core.remote_connection.subprocess.Popen")

    conn.abrir_acesso_remoto("10.8.128.14")
    mock_popen.assert_called_once_with([str(fake_vnc), "10.8.128.14", "-config", str(fake_opt)])