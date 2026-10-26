import threading
import queue
import json
import os
import base64 as b64
from PyQt6.QtCore import QObject, pyqtSignal

from core.remote_connection import RemoteConnectionManager
from core.database import DatabaseManager
from core.logger import get_logger

log = get_logger(__name__)

class WorkerSignals(QObject):
    started = pyqtSignal(str)
    finished = pyqtSignal(str, str, dict)
    error = pyqtSignal(str, str)

class TaskWorker(threading.Thread):
    def __init__(self, task_queue, db_manager):
        super().__init__()
        self.task_queue = task_queue
        self.db = db_manager
        self.daemon = True

    def run(self):
        while True:
            task = self.task_queue.get()
            if task is None:
                break
                
            # Desempacotar argumentos incluindo script_b64 (novo para o Agendador)
            target_pc, script_name, script_content, module_name, credentials, script_b64, signals = task
            conn = RemoteConnectionManager()
            executor = os.environ.get("USERNAME", "Desconhecido")
            
            # --- 1. Injeção Base64 Segura (Credenciais) ---
            if credentials and isinstance(credentials, dict):
                def _b64(s: str) -> str:
                    return b64.b64encode((s or "").encode("utf-8")).decode("ascii").replace('\n', '')

                user_b64 = _b64(credentials.get("user", ""))
                pass_b64 = _b64(credentials.get("pass", ""))
                vnc_b64 = _b64(credentials.get("vnc_pass", ""))

                script_content = script_content.replace("[[ADMIN_USER]]", user_b64)
                script_content = script_content.replace("[[ADMIN_PASS]]", pass_b64)
                script_content = script_content.replace("[[VNC_PASS]]", vnc_b64)
            
            # --- 2. Injeção Base64 de Scripts Grandes (Bypass do WinError 206) ---
            if script_b64:
                script_content = script_content.replace("{{script_b64}}", script_b64)
            
            signals.started.emit(target_pc)
            
            try:
                res = conn.execute_script(target_pc, script_content)
                status = res.get("status", "Pendente")
                json_data = res.get("json_data", {})
                raw_data = res.get("log_saida", "")
                
                if status == "Sucesso" and "StatusFinal" in json_data:
                    status = json_data["StatusFinal"]
                    
                self.db.save_execution(target_pc, script_name, status, raw_data, technician=executor, module=module_name)
                
                if status.upper() in ["SUCESSO", "ALERTA", "ALERTA/ERRO"]:
                    signals.finished.emit(target_pc, status, json_data)
                else:
                    error_msg = json_data.get("Mensagem", "Falha na execução do script.")
                    signals.error.emit(target_pc, str(error_msg))
                    
            except Exception as e:
                log.error(f"Worker falhou em '{script_name}' → {target_pc}: {e}", exc_info=True)
                error_json = json.dumps({"Erro": str(e), "StatusFinal": "ERRO FATAL"})
                self.db.save_execution(target_pc, script_name, "ERRO FATAL", error_json, technician=executor, module=module_name)
                signals.error.emit(target_pc, str(e))
            finally:
                self.task_queue.task_done()

class TaskQueueManager:
    def __init__(self, max_threads=10):
        self.task_queue = queue.Queue()
        self.db = DatabaseManager()
        self.workers = []
        for _ in range(max_threads):
            worker = TaskWorker(self.task_queue, self.db)
            worker.start()
            self.workers.append(worker)

    # Note a adição de `script_b64=None`
    def add_task(self, target_pc, script_name, script_content, module_name="Execução Remota",
                 credentials=None, script_b64=None, on_start=None, on_finish=None, on_error=None):
        signals = WorkerSignals()
        if on_start: signals.started.connect(on_start)
        if on_finish: signals.finished.connect(on_finish)
        if on_error: signals.error.connect(on_error)
        self.task_queue.put((target_pc, script_name, script_content, module_name, credentials, script_b64, signals))

    def shutdown(self, timeout: float = 2.0):
        log.info(f"TaskQueueManager: encerrando {len(self.workers)} worker(s)...")
        for _ in self.workers:
            self.task_queue.put(None)
        for w in self.workers:
            w.join(timeout=timeout)
        log.info("TaskQueueManager: workers encerrados.")