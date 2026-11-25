import threading
import queue
import json
import os
import base64 as b64
from PyQt6.QtCore import QObject, pyqtSignal

from core.remote_connection import RemoteConnectionManager
from core.database import DatabaseManager
from core.config import get_max_threads
from core.logger import get_logger
from core.ps_loader import extract_script_timeout

log = get_logger(__name__)


class WorkerSignals(QObject):
    started = pyqtSignal(str)
    finished = pyqtSignal(str, str, dict)
    error = pyqtSignal(str, str)


class TaskWorker(threading.Thread):
    GENERIC_PARSE_MSG = "A execução ocorreu, mas não foi possível ler o pacote de dados formatados."

    def __init__(self, task_queue, db_manager):
        super().__init__()
        self.task_queue = task_queue
        self.db = db_manager
        self.daemon = True

    @classmethod
    def _extract_error_message(cls, json_data: dict, raw_data: str) -> str:
        """Extrai a mensagem de erro mais detalhada disponível no retorno."""
        if isinstance(json_data, dict):
            msg = json_data.get("Mensagem")
            detalhes = json_data.get("Detalhes")

            if msg and msg != cls.GENERIC_PARSE_MSG:
                if isinstance(detalhes, list) and detalhes:
                    det_str = "\n".join(str(x) for x in detalhes if str(x).strip())
                    return f"{msg}\n{det_str}" if det_str else str(msg)
                return str(msg)

            if isinstance(detalhes, list) and detalhes:
                det_str = "\n".join(str(x) for x in detalhes if str(x).strip())
                if det_str:
                    return det_str
            elif isinstance(detalhes, str) and detalhes.strip():
                return detalhes.strip()

        if raw_data and raw_data.strip():
            return raw_data.strip()

        return "Falha na execução do script."

    def run(self):
        while True:
            task = self.task_queue.get()
            if task is None:
                self.task_queue.task_done()
                break

            # Desempacotando a tupla corretamente com o timeout e o signals (R06)
            target_pc, script_name, script_content, module_name, credentials, script_b64, signals, timeout_seconds = task
            conn = RemoteConnectionManager()
            executor = os.environ.get("USERNAME", "Desconhecido")

            # Injeção Base64 Segura (Credenciais)
            if credentials and isinstance(credentials, dict):
                def _b64(s: str) -> str:
                    return b64.b64encode((s or "").encode("utf-8")).decode("ascii").replace("\n", "")

                user_b64 = _b64(credentials.get("user", ""))
                pass_b64 = _b64(credentials.get("pass", ""))
                vnc_b64 = _b64(credentials.get("vnc_pass", ""))

                script_content = script_content.replace("[[ADMIN_USER]]", user_b64)
                script_content = script_content.replace("[[ADMIN_PASS]]", pass_b64)
                script_content = script_content.replace("[[VNC_PASS]]", vnc_b64)

            # Injeção Base64 de Scripts Grandes (Bypass do WinError 206)
            if script_b64:
                script_content = script_content.replace("{{script_b64}}", script_b64)

            signals.started.emit(target_pc)

            try:
                # --- NOVO: Sobrescreve o timeout se o script tiver a diretiva # @timeout: ---
                timeout_final = extract_script_timeout(script_content, default_timeout=timeout_seconds)

                res = conn.execute_script(target_pc, script_content, timeout_seconds=timeout_final)
                status = res.get("status", "Pendente")
                json_data = res.get("json_data", {})
                if not isinstance(json_data, dict):
                    json_data = {}
                raw_data = res.get("log_saida", "")

                if status == "Sucesso" and "StatusFinal" in json_data:
                    status = str(json_data["StatusFinal"])

                self.db.save_execution(
                    target_pc, script_name, status, raw_data,
                    technician=executor, module=module_name
                )

                if status.upper() in ["SUCESSO", "ALERTA", "ALERTA/ERRO"]:
                    signals.finished.emit(target_pc, status, json_data)
                else:
                    error_msg = self._extract_error_message(json_data, raw_data)
                    signals.error.emit(target_pc, error_msg)

            except Exception as e:
                log.error(f"Worker falhou em '{script_name}' → {target_pc}: {e}", exc_info=True)
                error_json = json.dumps({"Erro": str(e), "StatusFinal": "ERRO FATAL"})
                self.db.save_execution(
                    target_pc, script_name, "ERRO FATAL", error_json,
                    technician=executor, module=module_name
                )
                signals.error.emit(target_pc, str(e))
            finally:
                self.task_queue.task_done()


class TaskQueueManager:
    def __init__(self, max_threads: int = None, db_manager: DatabaseManager = None):
        self.task_queue = queue.Queue()
        self.db = db_manager or DatabaseManager()
        threads_count = max_threads if (max_threads and max_threads >= 1) else get_max_threads(default=10)
        self.workers = []
        for _ in range(threads_count):
            worker = TaskWorker(self.task_queue, self.db)
            worker.start()
            self.workers.append(worker)

    def add_task(self, target_pc, script_name, script_content, module_name="Execução Remota",
                 credentials=None, script_b64=None, on_start=None, on_finish=None, on_error=None, timeout_seconds: int = 300):
        signals = WorkerSignals()
        if on_start:
            signals.started.connect(on_start)
        if on_finish:
            signals.finished.connect(on_finish)
        if on_error:
            signals.error.connect(on_error)
        
        # Adiciona o signals e o timeout na tupla da fila
        self.task_queue.put((target_pc, script_name, script_content, module_name, credentials, script_b64, signals, timeout_seconds))

    def shutdown(self, timeout: float = 2.0):
        log.info(f"TaskQueueManager: encerrando {len(self.workers)} worker(s)...")
        for _ in self.workers:
            self.task_queue.put(None)
        for w in self.workers:
            w.join(timeout=timeout)
        log.info("TaskQueueManager: workers encerrados.")