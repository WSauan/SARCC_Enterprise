
import pytest

from core.ps_loader import PsTemplateError, load_ps_template


def test_ps_loader_blocks_tampered_script(tmp_path, monkeypatch):
    """Garante que o ps_loader rejeita um script se o hash não bater com o manifesto."""

    # 1. Configura um diretório de scripts temporário para o teste
    fake_scripts_dir = tmp_path / "scripts"
    fake_scripts_dir.mkdir()

    # 2. Cria um script falso e um manifesto com um hash ERRADO (simulando adulteração)
    test_script = fake_scripts_dir / "hack.ps1"
    test_script.write_text("Write-Output 'Eu sou um payload malicioso'", encoding="utf-8")

    # Manifesto diz que o hash do "hack.ps1" é o hash de um script limpo
    fake_manifest = {
        "hack.ps1": "0000000000000000000000000000000000000000000000000000000000000000"
    }
    manifest_file = fake_scripts_dir / "manifest.json"
    import json
    manifest_file.write_text(json.dumps(fake_manifest), encoding="utf-8")

    # 3. Aponta o ps_loader para o diretório falso
    monkeypatch.setattr("core.ps_loader.get_ps_scripts_dir", lambda: fake_scripts_dir)

    # 4. O teste: deve levantar PsTemplateError (bloqueio de integridade)
    with pytest.raises(PsTemplateError, match="Falha de integridade"):
        load_ps_template(".", "hack")
