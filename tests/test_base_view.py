from gui.views.base_view import read_text_file_safe, sanitize_filename


def test_read_text_file_safe_handles_utf8_bom_and_cp1252(tmp_path):
    """Garante leitura limpa tanto de arquivos UTF-8 com BOM quanto Windows-1252 (PowerShell ISE)."""
    f_bom = tmp_path / "bom.ps1"
    f_bom.write_bytes("Write-Output 'Teste'".encode("utf-8-sig"))
    assert read_text_file_safe(f_bom) == "Write-Output 'Teste'"

    f_ansi = tmp_path / "ansi.ps1"
    f_ansi.write_bytes("Manutenção de Rede — Câmera".encode("cp1252"))
    assert read_text_file_safe(f_ansi) == "Manutenção de Rede — Câmera"


def test_sanitize_filename_removes_windows_forbidden_chars():
    """Verifica se caracteres ilegais no Windows são convertidos em '-'."""
    raw = "HUL-WK-01_2026:11:13_Instalar (Winget): PuTTY/VLC"
    clean = sanitize_filename(raw)
    for bad in '<>:"/\\|?*':
        assert bad not in clean
    assert "HUL-WK-01" in clean
