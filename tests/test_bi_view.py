from core.database import DatabaseManager
from infrastructure.repositories.execution_repository import ExecutionRepository


def test_bi_metrics_aggregation(tmp_path):
    db = DatabaseManager(db_path=tmp_path / "test_bi.db")
    repo = ExecutionRepository(db_manager=db)

    # Vamos criar uma contagem clara:
    # Script A: 3 vezes (Vai ser o Top 1)
    # Script B: 1 vez (Vai ser o Top 2)
    repo.record_execution("PC1", "Script A", "SUCESSO", "{}")
    repo.record_execution("PC2", "Script A", "SUCESSO", "{}")
    repo.record_execution("PC3", "Script A", "SUCESSO", "{}")
    repo.record_execution("PC1", "Script B", "ERRO FATAL", "{}")
    repo.record_execution("PC4", "Script C", "ALERTA", "{}")

    metrics = repo.get_bi_metrics(days=0)
    assert metrics["SUCESSO"] == 3
    assert metrics["FALHA"] == 1
    assert metrics["ALERTA"] == 1

    top = repo.get_top_scripts(days=0)
    assert len(top) == 3
    assert top[0][0] == "Script A"
    assert top[0][1] == 3

    maquinas = repo.get_unique_machines_count(days=0)
    assert maquinas == 4 # PC1, PC2, PC3, PC4
