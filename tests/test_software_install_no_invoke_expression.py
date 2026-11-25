from pathlib import Path


def test_software_install_has_no_invoke_expression():
    """Garante que o software_install.ps1 não usa Invoke-Expression para baixar código da internet."""
    content = Path("core/scripts/software/software_install.ps1").read_text(encoding="utf-8")
    # Falha se encontrar o padrão antigo
    assert "Invoke-Expression $installScript" not in content, \
        "Invoke-Expression vulnerável encontrado no software_install.ps1!"
    # Garante que agora usa o pacote oficial
    assert "nupkg" in content, "O script deve baixar o pacote .nupkg oficial do Chocolatey."
