import os
import sqlite3
from datetime import datetime, timedelta


class DatabaseManager:
    def __init__(self, db_path=None):
        """
        Args:
            db_path: caminho do arquivo SQLite. Se None, usa o padrão
                    (definido por core.config.get_db_path()).
                    Aceita str ou Path.
        """
        if db_path is None:
            from core.config import get_db_path
            db_path = get_db_path()

        self.db_path = str(db_path)

        # Garante que o diretório-pai existe (evita makedirs("") quando
        # db_path é um nome simples tipo "sarcc.db").
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        self._initialize_db()
        self._auto_cleanup()

    def get_connection(self):
        # 1. timeout=20.0: Aguarda até 20s caso outro colega esteja gravando no momento
        # 2. check_same_thread=False: Libera o acesso simultâneo para a interface gráfica
        conn = sqlite3.connect(self.db_path, timeout=20.0, check_same_thread=False)

        # 3. Ativa o modo WAL para permitir Leituras e Gravações simultâneas na rede
        conn.execute('PRAGMA journal_mode=wal')

        return conn

    def _initialize_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Cria a tabela base
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT,
                    target_pc TEXT,
                    script_name TEXT,
                    status TEXT,
                    result_data TEXT,
                    excluido INTEGER DEFAULT 0
                )
            ''')

            # --- AUTO-MIGRAÇÃO (Adicionando Auditoria de Técnico e Módulo) ---
            cursor.execute("PRAGMA table_info(executions)")
            colunas_exe = [col[1] for col in cursor.fetchall()]

            if 'technician' not in colunas_exe:
                cursor.execute("ALTER TABLE executions ADD COLUMN technician TEXT DEFAULT 'N/A'")
            if 'module' not in colunas_exe:
                cursor.execute("ALTER TABLE executions ADD COLUMN module TEXT DEFAULT 'Execução Remota'")
            # -----------------------------------------------------------------

            cursor.execute("PRAGMA table_info(scripts)")
            colunas_scripts = [col[1] for col in cursor.fetchall()]
            if 'caminho' in colunas_scripts:
                cursor.execute("DROP TABLE scripts")

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT UNIQUE,
                    descricao TEXT,
                    categoria TEXT,
                    conteudo TEXT
                )
            ''')
            conn.commit()

    def _auto_cleanup(self, days_to_keep=90):
        cutoff_date = (datetime.now() - timedelta(days=days_to_keep)).strftime('%Y-%m-%d %H:%M:%S')
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM executions WHERE start_time < ?", (cutoff_date,))
                conn.commit()
        except Exception:
            pass

    def get_all_scripts(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, nome, descricao, categoria, conteudo FROM scripts ORDER BY nome ASC")
            return cursor.fetchall()

    def save_script(self, nome, descricao, categoria, conteudo):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scripts (nome, descricao, categoria, conteudo)
                VALUES (?, ?, ?, ?)
            ''', (nome, descricao, categoria, conteudo))
            conn.commit()

    def update_script(self, script_id, nome, descricao, categoria, conteudo):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE scripts
                SET nome = ?, descricao = ?, categoria = ?, conteudo = ?
                WHERE id = ?
            ''', (nome, descricao, categoria, conteudo, script_id))
            conn.commit()

    def delete_script(self, script_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM scripts WHERE id = ?", (script_id,))
            conn.commit()

    # Atualizado para receber tecnico e modulo
    def save_execution(self, target_pc, script_name, status, result_data, technician="N/A", module="Automático"):
        start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO executions (start_time, target_pc, script_name, status, result_data, technician, module)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (start_time, target_pc, script_name, status, result_data, technician, module))
            conn.commit()
