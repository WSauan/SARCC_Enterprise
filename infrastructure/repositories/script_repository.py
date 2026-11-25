from typing import Any, Dict, List, Optional, Tuple

from core.database import DatabaseManager


class ScriptRepository:
    """Repositório de persistência SQLite para o catálogo de scripts PowerShell."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def list_all(self) -> List[Tuple[int, str, str, str, str]]:
        """Retorna todos os scripts ordenados por nome: (id, nome, descricao, categoria, conteudo)."""
        return self.db.get_all_scripts()

    def list_as_dicts(self) -> List[Dict[str, Any]]:
        """Retorna todos os scripts estruturados como dicionários."""
        rows = self.db.get_all_scripts()
        return [
            {
                "id": r[0],
                "nome": r[1],
                "descricao": r[2] or "",
                "categoria": r[3] or "Outros",
                "conteudo": r[4] or "",
            }
            for r in rows
        ]

    def get_by_id(self, script_id: int) -> Optional[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, nome, descricao, categoria, conteudo FROM scripts WHERE id = ?",
                (script_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "nome": row[1],
                "descricao": row[2] or "",
                "categoria": row[3] or "Outros",
                "conteudo": row[4] or "",
            }

    def get_by_name(self, nome: str) -> Optional[Dict[str, Any]]:
        """Busca um script pelo nome ignorando maiúsculas/minúsculas."""
        clean_name = (nome or "").strip()
        if not clean_name:
            return None
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, nome, descricao, categoria, conteudo FROM scripts WHERE LOWER(nome) = LOWER(?)",
                (clean_name,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "nome": row[1],
                "descricao": row[2] or "",
                "categoria": row[3] or "Outros",
                "conteudo": row[4] or "",
            }

    def create(self, nome: str, descricao: str, categoria: str, conteudo: str) -> None:
        self.db.save_script(nome.strip(), descricao.strip(), categoria.strip() or "Outros", conteudo)

    def update(self, script_id: int, nome: str, descricao: str, categoria: str, conteudo: str) -> None:
        self.db.update_script(script_id, nome.strip(), descricao.strip(), categoria.strip() or "Outros", conteudo)

    def upsert(self, nome: str, descricao: str, categoria: str, conteudo: str) -> str:
        """Insere um novo script ou atualiza o código caso o nome já exista. Retorna 'created' ou 'updated'."""
        existing = self.get_by_name(nome)
        if existing:
            desc_final = descricao.strip() or existing["descricao"] or "Atualizado via Importação"
            cat_final = categoria.strip() or existing["categoria"] or "Outros"
            self.update(existing["id"], existing["nome"], desc_final, cat_final, conteudo)
            return "updated"
        self.create(nome, descricao, categoria, conteudo)
        return "created"

    def delete(self, script_id: int) -> None:
        self.db.delete_script(script_id)
