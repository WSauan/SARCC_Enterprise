from core.database import DatabaseManager
from infrastructure.repositories.script_repository import ScriptRepository


def test_script_repository_upsert_and_case_insensitive_lookup(tmp_path):
    """Valida criação, busca case-insensitive e atualização automática via upsert."""
    db = DatabaseManager(db_path=tmp_path / "repo_scripts.db")
    repo = ScriptRepository(db_manager=db)

    status1 = repo.upsert("Limpar Cache", "Desc 1", "Manutenção", "Clear-Host")
    assert status1 == "created"

    found = repo.get_by_name("limpar cache")
    assert found is not None
    assert found["nome"] == "Limpar Cache"
    assert found["conteudo"] == "Clear-Host"

    status2 = repo.upsert("LIMPAR CACHE", "Desc 2", "Sistema", "Write-Output 'Novo'")
    assert status2 == "updated"

    all_scripts = repo.list_as_dicts()
    assert len(all_scripts) == 1
    assert all_scripts[0]["conteudo"] == "Write-Output 'Novo'"