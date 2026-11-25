from pathlib import Path
import re

def test_scripts_do_not_use_net_use_with_password():
    """
    Garante que nenhum script PowerShell usa 'net use' com senha na linha de comando.
    Isso evita que a senha seja capturada pelo Event ID 4688 ou Win32_Process.
    """
    scripts_dir = Path("core/scripts")
    ps1_files = list(scripts_dir.rglob("*.ps1"))
    
    assert len(ps1_files) > 0, "Nenhum arquivo .ps1 encontrado na pasta core/scripts"
    
    falhas = []
    
    for ps1 in ps1_files:
        content = ps1.read_text(encoding="utf-8")
        
        # Procura por qualquer linha que tenha 'net use' e a variável $AdminPass
        # (evita falso positivo de comentários que ensinam o comando)
        for line in content.splitlines():
            line_clean = line.strip()
            if line_clean.startswith("#"):
                continue
            
            # Regex para achar "net use" seguido de algo e a senha injetada
            if "net use" in line_clean and ("$AdminPass" in line_clean or "$AdminPassRaw" in line_clean):
                falhas.append(f"{ps1.name}: {line_clean}")
                
    assert not falhas, (
        "Senhas expostas no cmdline via 'net use' encontradas nos seguintes scripts:\n" +
        "\n".join(falhas)
    )