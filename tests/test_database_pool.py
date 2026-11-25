from core.database import DatabaseManager


def test_database_reuses_connection_in_same_thread(tmp_path):
    """Garante que o DatabaseManager reutiliza a conexão em vez de abrir uma nova a cada query."""
    db = DatabaseManager(db_path=tmp_path / "test_pool.db")

    conn1 = db.get_connection()
    conn2 = db.get_connection()

    # As duas chamadas devem retornar o mesmo objeto de conexão (reutilização)
    assert conn1 is conn2
