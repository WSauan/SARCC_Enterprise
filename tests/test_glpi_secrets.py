from pathlib import Path


def test_repair_agent_has_no_hardcoded_glpi_secret():
    """Garante que o repair_agent.ps1 não contém o secret OAuth em texto plano."""
    content = Path("core/scripts/dashboard/repair_agent.ps1").read_text(encoding="utf-8")
    secret_hardcoded = "3fcba97de33697cf59dd2b862b49a8907594b10172c8a6d89905542a6306c300"
    assert secret_hardcoded not in content, "Secret do GLPI hardcoded no repair_agent.ps1!"


def test_deploy_glpi_agent_has_no_hardcoded_glpi_secret():
    """Garante que o Deploy_GLPI_Agent.ps1 não contém o secret OAuth em texto plano."""
    content = Path("core/scripts/user_scripts/Deploy_GLPI_Agent.ps1").read_text(encoding="utf-8")
    secret_hardcoded = "3fcba97de33697cf59dd2b862b49a8907594b10172c8a6d89905542a6306c300"
    assert secret_hardcoded not in content, "Secret do GLPI hardcoded no Deploy_GLPI_Agent.ps1!"


def test_repair_agent_uses_placeholder_for_glpi():
    """Garante que o script usa placeholders em vez de valores fixos."""
    content = Path("core/scripts/dashboard/repair_agent.ps1").read_text(encoding="utf-8")
    assert "{{glpi_oauth_id}}" in content, "Placeholder {{glpi_oauth_id}} ausente no repair_agent.ps1"
    assert "{{glpi_oauth_secret}}" in content, "Placeholder {{glpi_oauth_secret}} ausente no repair_agent.ps1"