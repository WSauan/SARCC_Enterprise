from typing import List, Optional, Tuple

from core.database import DatabaseManager
from core.remote_connection import resolve_target_hostname


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
        normalized_target = resolve_target_hostname(target_pc) or str(target_pc or "").strip()
        self.db.save_execution(
            target_pc=normalized_target,
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

    def get_bi_metrics(self, days: int = 0) -> dict:
        """Retorna contadores de sucesso, alerta e falha. Se days=0, considera todo o período."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()

            query = "SELECT status, COUNT(*) FROM executions WHERE excluido = 0"
            params = []

            if days > 0:
                query += " AND start_time >= date('now', ?)"
                params.append(f'-{days} days')

            query += " GROUP BY status"
            cursor.execute(query, params)

            rows = cursor.fetchall()

            metrics = {"SUCESSO": 0, "ALERTA": 0, "FALHA": 0}
            for status, count in rows:
                s = str(status).upper()
                if "SUCESSO" in s:
                    metrics["SUCESSO"] += count
                elif "ALERTA" in s:
                    metrics["ALERTA"] += count
                else:
                    metrics["FALHA"] += count

            return metrics

    def get_top_scripts(self, days: int = 0, limit: int = 5) -> List[Tuple[str, int]]:
        """Retorna os scripts mais executados."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT script_name, COUNT(*) as qtd FROM executions WHERE excluido = 0"
            params = []

            if days > 0:
                query += " AND start_time >= date('now', ?)"
                params.append(f'-{days} days')

            query += " GROUP BY script_name ORDER BY qtd DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            return cursor.fetchall()

    def get_unique_machines_count(self, days: int = 0) -> int:
        """Retorna o total de máquinas únicas atendidas."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT COUNT(DISTINCT target_pc) FROM executions WHERE excluido = 0"
            params = []

            if days > 0:
                query += " AND start_time >= date('now', ?)"
                params.append(f'-{days} days')

            cursor.execute(query, params)
            return cursor.fetchone()[0]
