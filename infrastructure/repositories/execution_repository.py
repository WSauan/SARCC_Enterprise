from typing import List, Optional, Tuple
from core.database import DatabaseManager


class ExecutionRepository:
    """Repositório de persistência SQLite para auditoria e histórico de execuções."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def record_execution(
        self,
        target_pc: str,
        script_name: str,
        status: str,
        result_data: str,
        technician: str = "N/A",
        module: str = "Automático",
    ) -> None:
        self.db.save_execution(
            target_pc=target_pc,
            script_name=script_name,
            status=status,
            result_data=result_data,
            technician=technician,
            module=module,
        )

    def list_executions(self, deleted: bool = False, limit: int = 1000) -> List[Tuple]:
        """Lista os registros de execução ativos (deleted=False) ou na lixeira (deleted=True)."""
        flag = 1 if deleted else 0
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, start_time, target_pc, script_name, status, result_data, technician, module
                FROM executions
                WHERE excluido = ?
                ORDER BY start_time DESC
                LIMIT ?
                """,
                (flag, int(limit)),
            )
            return cursor.fetchall()

    def get_by_id(self, execution_id: int) -> Optional[Tuple]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT start_time, target_pc, script_name, status, result_data, technician, module
                FROM executions
                WHERE id = ?
                """,
                (execution_id,),
            )
            return cursor.fetchone()

    def soft_delete_many(self, ids: List[int]) -> int:
        """Move os registros informados para a lixeira (excluido = 1)."""
        if not ids:
            return 0
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE executions SET excluido = 1 WHERE id = ?",
                [(int(i),) for i in ids],
            )
            conn.commit()
            return cursor.rowcount

    def restore_many(self, ids: List[int]) -> int:
        """Restaura registros da lixeira para o histórico ativo (excluido = 0)."""
        if not ids:
            return 0
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE executions SET excluido = 0 WHERE id = ?",
                [(int(i),) for i in ids],
            )
            conn.commit()
            return cursor.rowcount

    def hard_delete_many(self, ids: List[int]) -> int:
        """Exclui permanentemente os registros selecionados do banco SQLite."""
        if not ids:
            return 0
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(
                "DELETE FROM executions WHERE id = ?",
                [(int(i),) for i in ids],
            )
            conn.commit()
            return cursor.rowcount

    def empty_trash(self) -> int:
        """Remove definitivamente todos os registros que estão na lixeira (excluido = 1)."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM executions WHERE excluido = 1")
            conn.commit()
            return cursor.rowcount