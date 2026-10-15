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
                
            target_pc, script_name, script_content, module_name, credentials, signals = task
            conn = RemoteConnectionManager()
            
            # --- CAPTURA O TÉCNICO EXECUTOR ---
            # Pega o usuário que abriu o aplicativo (Ex: adm.wsauan)
            executor = os.environ.get("USERNAME", "Desconhecido")
            
            # --- PROTEÇÃO DE CREDENCIAIS (INJEÇÃO EM TEMPO DE EXECUÇÃO) ---
            # Placeholders canônicos: [[ADMIN_USER]], [[ADMIN_PASS]], [[VNC_PASS]]
            #
            # Regra:
            #   - Se credentials foi passado → substitui pelos valores reais
            #   - Se NÃO foi passado → DEIXA os placeholders literais no script.
            #     Isso é intencional: o script remoto detecta "[[" no valor e
            #     cai em modo conta-máquina (System), usado pelo SchedulerView.
            #
            # Fallback antigo via env vars foi removido — quem precisar, passa
            # o dict credentials.
            if credentials:
                # Codifica credenciais em Base64 — elimina qualquer problema
                # com caracteres especiais na senha ($, ", ', `, espaço, etc.).
                # O script PowerShell decodifica em runtime.
                def _b64(s: str) -> str:
                    return b64.b64encode((s or "").encode("utf-8")).decode("ascii")

                script_content = script_content.replace("[[ADMIN_USER]]", _b64(credentials.get("user", "")))
                script_content = script_content.replace("[[ADMIN_PASS]]", _b64(credentials.get("pass", "")))
                script_content = script_content.replace("[[VNC_PASS]]", _b64(credentials.get("vnc_pass", "")))
            # else: placeholders ficam literais → script detecta modo conta-máquina
            
            signals.started.emit(target_pc)
            
            try:
                res = conn.execute_script(target_pc, script_content)
                status = res.get("status", "Pendente")
                json_data = res.get("json_data", {})
                raw_data = res.get("log_saida", "")
                
                if status == "Sucesso" and "StatusFinal" in json_data:
                    status = json_data["StatusFinal"]
                    
                # Grava no banco com o Técnico e a Tela
                self.db.save_execution(target_pc, script_name, status, raw_data, technician=executor, module=module_name)
                
                if status.upper() in ["SUCESSO", "ALERTA", "ALERTA/ERRO"]:
                    signals.finished.emit(target_pc, status, json_data)
                else:
                    error_msg = json_data.get("Mensagem", "Falha na execução do script.")
                    signals.error.emit(target_pc, str(error_msg))
                    
            except Exception as e:
                log.error(
                    f"Worker falhou em '{script_name}' → {target_pc}: {e}",
                    exc_info=True,
                )
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

    # Atualizado para receber o nome da tela/módulo
    def add_task(self, target_pc, script_name, script_content, module_name="Execução Remota",
                 credentials=None, on_start=None, on_finish=None, on_error=None):
        """Enfileira uma execução remota.

        Args:
            credentials: dict opcional com chaves 'user', 'pass', 'vnc_pass'.
                         Quando presente, substitui os placeholders
                         [[ADMIN_USER]], [[ADMIN_PASS]], [[VNC_PASS]]
                         no script antes de enviá-lo ao alvo.
        """
        signals = WorkerSignals()
        if on_start: signals.started.connect(on_start)
        if on_finish: signals.finished.connect(on_finish)
        if on_error: signals.error.connect(on_error)
            
        self.task_queue.put((target_pc, script_name, script_content, module_name, credentials, signals))

    def shutdown(self, timeout: float = 2.0):
        """Encerra todos os workers graciosamente.

        Envia `None` para cada worker (sinal de parada) e aguarda até `timeout`
        segundos para cada um. Chamado no fechamento da aplicação.
        """
        log.info(f"TaskQueueManager: encerrando {len(self.workers)} worker(s)...")
        for _ in self.workers:
            self.task_queue.put(None)  # sinal de "pare"
        for w in self.workers:
            w.join(timeout=timeout)
        log.info("TaskQueueManager: workers encerrados.")