import pytest
import base64
from core.ps_loader import load_ps_template, PsTemplateError

def test_load_nonexistent_template():
    """Garante que o sistema bloqueia e avisa quando tenta carregar um script que não existe."""
    with pytest.raises(PsTemplateError) as exc_info:
        load_ps_template("pasta_falsa", "script_fantasma")
    
    assert "pasta_falsa" in str(exc_info.value) or "script_fantasma" in str(exc_info.value)

def test_template_variable_injection(mocker):
    """
    Testa se as variáveis (agora no formato Base64 do motor atual) são injetadas corretamente
    sem precisar ler um ficheiro real do disco (usando mock).
    """
    # Simulamos o conteúdo do kill_process.ps1 ATUAL (que usa injeção blindada b64)
    fake_script_content = "Stop-Process -Id [Convert]::FromBase64String('{{pid_b64}}') -Name '{{nome_b64}}'"
    
    # Enganamos a função 'open' nativa do Python para ler a nossa string em vez do disco
    mocker.patch("builtins.open", mocker.mock_open(read_data=fake_script_content))
    mocker.patch("pathlib.Path.exists", return_value=True)

    # Convertendo os dados de teste para Base64 (exatamente como o system_manager_view.py faz)
    fake_pid_b64 = base64.b64encode("1234".encode('utf-8')).decode('ascii')
    fake_nome_b64 = base64.b64encode("chrome".encode('utf-8')).decode('ascii')

    # Executamos a função real
    resultado = load_ps_template("system_manager", "kill_process", pid_b64=fake_pid_b64, nome_b64=fake_nome_b64)

    # Verificamos se as strings em Base64 foram injetadas perfeitamente na string final
    assert fake_pid_b64 in resultado
    assert fake_nome_b64 in resultado
    
    # Verificamos se as chaves originais desapareceram (foram substituídas)
    assert "{{pid_b64}}" not in resultado
    assert "{{nome_b64}}" not in resultado