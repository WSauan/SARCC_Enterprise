from pathlib import Path

def test_scripts_do_not_contain_hardcoded_internal_ips_or_shares():
    """
    Garante que nenhum script PowerShell contém IPs internos ou caminhos de rede fixos.
    Eles devem usar placeholders como {{share_root}} ou {{zabbix_ip}}.
    """
    scripts_dir = Path("core/scripts")
    ps1_files = list(scripts_dir.rglob("*.ps1"))
    
    falhas = []
    
    ips_hardcoded = ["10.8.245.12"]
    shares_hardcoded = ["\\\\hul-vp-imagem-cc\\netshared", "\\\\hul-vp-imagem-cc"]
    
    for ps1 in ps1_files:
        # Pula pastas de backup
        if "Scripts " in str(ps1) or "backup" in str(ps1).lower():
            continue
            
        content = ps1.read_text(encoding="utf-8")
        
        for line_num, line in enumerate(content.splitlines(), 1):
            line_clean = line.strip()
            if line_clean.startswith("#"):
                continue
                
            for ip in ips_hardcoded:
                if ip in line_clean:
                    falhas.append(f"{ps1.name} (Linha {line_num}): IP hardcoded '{ip}'")
            
            for share in shares_hardcoded:
                if share in line_clean:
                    falhas.append(f"{ps1.name} (Linha {line_num}): Share hardcoded '{share}'")
                    
    assert not falhas, (
        "Infraestrutura hardcoded encontrada. Use placeholders do ps_loader:\n" +
        "\n".join(falhas)
    )