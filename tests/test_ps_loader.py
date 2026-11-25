import pytest

from core.ps_loader import PsTemplateError, load_ps_template


def test_load_nonexistent_template():
    """Garante que carregar um template inexistente levanta PsTemplateError."""
    with pytest.raises(PsTemplateError):
        load_ps_template("categoria_inexistente", "script_fantasma")


def test_template_variable_injection(tmp_path, monkeypatch):
    """Valida a substituição de placeholders {{chave}} no template PowerShell."""
    cat_dir = tmp_path / " dummy_cat "
    cat_dir = tmp_path / "teste"
    cat_dir.mkdir()
    ps_file = cat_dir / "ola.ps1"
    ps_file.write_text("Write-Output '{{mensagem}}'", encoding="utf-8")

    monkeypatch.setattr("core.ps_loader.get_ps_scripts_dir", lambda: tmp_path)

    res = load_ps_template("teste", "ola", mensagem="SARCC OK")
    assert res == "Write-Output 'SARCC OK'"


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
