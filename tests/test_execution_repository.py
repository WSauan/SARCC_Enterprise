from core.database import DatabaseManager
from infrastructure.repositories.execution_repository import ExecutionRepository


def test_execution_repository_soft_delete_restore_and_empty_trash(tmp_path):
    """Testa o ciclo completo de auditoria: gravar, enviar para lixeira, restaurar e esvaziar."""
    db = DatabaseManager(db_path=tmp_path / "repo_exec.db")
    repo = ExecutionRepository(db_manager=db)

    repo.record_execution("HUL-WK-01", "Script A", "SUCESSO", "{}", "adm.wsauan", "Teste")
    repo.record_execution("HUL-WK-02", "Script B", "ERRO", "{}", "adm.wsauan", "Teste")

    ativos = repo.list_executions(deleted=False)
    assert len(ativos) == 2
    id_1 = ativos[0][0]
    id_2 = ativos[1][0]

    # Envia id_1 para a lixeira
    repo.soft_delete_many([id_1])
    assert len(repo.list_executions(deleted=False)) == 1
    assert len(repo.list_executions(deleted=True)) == 1

    # Restaura id_1 da lixeira
    repo.restore_many([id_1])
    assert len(repo.list_executions(deleted=False)) == 2

    # Move ambos para a lixeira e esvazia
    repo.soft_delete_many([id_1, id_2])
    removed = repo.empty_trash()
    assert removed == 2
    assert len(repo.list_executions(deleted=True)) == 0