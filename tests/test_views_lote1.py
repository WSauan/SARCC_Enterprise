from gui.views.base_view import read_text_file_safe, sanitize_filename
from gui.views.execution_view import parse_targets_string
from gui.views.history_view import extract_json_from_result, HistoryView


def test_read_text_file_safe_handles_utf8_bom_and_cp1252(tmp_path):
    """Garante leitura limpa tanto de arquivos UTF-8 com BOM quanto Windows-1252 (PowerShell ISE)."""
    f_bom = tmp_path / "bom.ps1"
    f_bom.write_bytes("\ufeffWrite-Output 'Teste'".encode("utf-8-sig"))
    assert read_text_file_safe(f_bom) == "Write-Output 'Teste'"

    f_ansi = tmp_path / "ansi.ps1"
    f_ansi.write_bytes("Manutenção de Rede — Câmera".encode("cp1252"))
    assert read_text_file_safe(f_ansi) == "Manutenção de Rede — Câmera"


def test_sanitize_filename_removes_windows_forbidden_chars():
    """Verifica se caracteres ilegais como ':' ou '/' são convertidos em '-'."""
    raw = "HUL-WK-01_2026:11:13_Instalar (Winget): PuTTY/VLC"
    clean = sanitize_filename(raw)
    for bad in '<>:"/\\|?*':
        assert bad not in clean
    assert "HUL-WK-01" in clean


def test_parse_targets_string_deduplicates_and_strips_bom():
    """Garante que alvos repetidos, com BOM ou separados por ';' são limpos e deduplicados."""
    raw = "\ufeffhul-wk-01, HUL-WK-02; hul-wk-01\n10.8.128.14 , "
    targets = parse_targets_string(raw)
    assert targets == ["HUL-WK-01", "HUL-WK-02", "10.8.128.14"]


def test_extract_json_from_result_handles_warnings_and_timer_footer():
    """Verifica se o histórico consegue extrair o JSON mesmo com avisos antes e rodapé de tempo depois."""
    raw_log = (
        "WARNING: Aviso prévio do PowerShell\n"
        '{"Script": "Limpeza", "StatusFinal": "SUCESSO", "Inicio": "2026-11-13 08:00:00", "Fim": "2026-11-13 08:00:05"}\n\n'
        "[⏱️ Tempo de Execução da Conexão: 5.12 segundos]"
    )
    js = extract_json_from_result(raw_log)
    assert js is not None
    assert js["StatusFinal"] == "SUCESSO"
    assert js["Script"] == "Limpeza"


def test_history_format_duration():
    """Valida a formatação de segundos, minutos e horas no histórico."""
    assert HistoryView._format_duration(12.34) == "12.3s"
    assert HistoryView._format_duration(125) == "2m 5s"
    assert HistoryView._format_duration(3665) == "1h 1m 5s"