from core.database import DatabaseManager
from infrastructure.repositories.execution_repository import ExecutionRepository
from domain.services.audit_service import AuditService


def test_audit_service_generates_formatted_glpi_report(tmp_path):
    """Garante que o relatório oficial de auditoria formata JSON, tempo e detalhes técnicos."""
    db = DatabaseManager(db_path=tmp_path / "svc_audit.db")
    repo = ExecutionRepository(db_manager=db)
    service = AuditService(repository=repo)

    raw_json = (
        '{"Script": "Limpeza_Padrao", "Inicio": "2026-11-13 08:00:00", '
        '"Fim": "2026-11-13 08:00:04", "StatusFinal": "SUCESSO", '
        '"Detalhes": ["Pastas TEMP* Eliminadas : 5"]}'
    )
    repo.record_execution("HUL-WK-TESTE", "Limpeza_Padrao", "SUCESSO", raw_json, "adm.wsauan", "[Execução] Lote")

    rows = repo.list_executions(deleted=False)
    exec_id = rows[0][0]

    report = service.generate_audit_report([exec_id])
    assert "SARCC - RELATÓRIO OFICIAL DE AUDITORIA E EXECUÇÃO" in report
    assert "COMPUTADOR ALVO  : HUL-WK-TESTE" in report
    assert "TEMPO DE EXECUÇÃO: 4.0s" in report
    assert "Pastas TEMP* Eliminadas : 5" in report