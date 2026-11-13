from datetime import datetime, timedelta
from core.database import DatabaseManager


def test_database_initialization_and_script_crud(tmp_path):
    """Valida criação de tabelas, inserção, listagem, atualização e exclusão de scripts."""
    db_file = tmp_path / "test_sarcc.db"
    db = DatabaseManager(db_path=db_file)

    # 1. Criar script
    db.save_script("Limpeza Teste", "Remove temp", "Manutenção", "Remove-Item C:\\Temp\\*")
    scripts = db.get_all_scripts()
    assert len(scripts) == 1
    script_id, nome, desc, cat, conteudo = scripts[0]
    assert nome == "Limpeza Teste"
    assert cat == "Manutenção"

    # 2. Atualizar script
    db.update_script(script_id, "Limpeza Teste v2", "Nova desc", "Sistema", "Clear-RecycleBin -Force")
    scripts_updated = db.get_all_scripts()
    assert scripts_updated[0][1] == "Limpeza Teste v2"
    assert scripts_updated[0][4] == "Clear-RecycleBin -Force"

    # 3. Apagar script
    db.delete_script(script_id)
    assert len(db.get_all_scripts()) == 0


def test_database_save_execution_and_audit_columns(tmp_path):
    """Garante que os registos de execução gravam técnico e módulo corretamente."""
    db_file = tmp_path / "test_audit.db"
    db = DatabaseManager(db_path=db_file)

    db.save_execution(
        target_pc="HUL-WK-TESTE",
        script_name="Instalar: PuTTY",
        status="SUCESSO",
        result_data="Instalado com sucesso",
        technician="adm.wsauan",
        module="Gestão de Software/Drivers"
    )

    with db.get_connection() as conn:
        row = conn.execute(
            "SELECT target_pc, script_name, status, technician, module FROM executions"
        ).fetchone()

    assert row == (
        "HUL-WK-TESTE",
        "Instalar: PuTTY",
        "SUCESSO",
        "adm.wsauan",
        "Gestão de Software/Drivers"
    )


def test_database_auto_cleanup_removes_old_records(tmp_path):
    """Verifica se registos com mais de 90 dias são expurgados automaticamente."""
    db_file = tmp_path / "test_cleanup.db"
    db = DatabaseManager(db_path=db_file)

    old_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d %H:%M:%S")
    recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")

    with db.get_connection() as conn:
        conn.execute(
            "INSERT INTO executions (start_time, target_pc, script_name, status, result_data) VALUES (?, ?, ?, ?, ?)",
            (old_date, "PC-ANTIGO", "Script1", "SUCESSO", "OK")
        )
        conn.execute(
            "INSERT INTO executions (start_time, target_pc, script_name, status, result_data) VALUES (?, ?, ?, ?, ?)",
            (recent_date, "PC-RECENTE", "Script2", "SUCESSO", "OK")
        )
        conn.commit()

    db._auto_cleanup(days_to_keep=90)

    with db.get_connection() as conn:
        remaining = conn.execute("SELECT target_pc FROM executions").fetchall()

    assert len(remaining) == 1
    assert remaining[0][0] == "PC-RECENTE"