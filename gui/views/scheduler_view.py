import os
import json
import base64
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QGroupBox, 
                             QComboBox, QMessageBox, QTimeEdit, QAbstractItemView, QInputDialog)
from PyQt6.QtCore import Qt, QTime, pyqtSlot, QThread, pyqtSignal

from core.task_queue import TaskQueueManager
from core.database import DatabaseManager
from core.remote_connection import RemoteConnectionManager
from gui.views.base_view import BaseView
from core.logger import get_logger

log = get_logger(__name__)

class FetchTasksWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, target_pc):
        super().__init__()
        self.target_pc = target_pc

    def run(self):
        try:
            conn = RemoteConnectionManager()
            ps_script = """
            $tasks = Get-ScheduledTask -TaskPath "\\SARCC\\" -ErrorAction SilentlyContinue
            $list = @()
            if ($tasks) {
                foreach ($t in $tasks) {$list += [PSCustomObject]@{
                        Name = $t.TaskName
                        State = $t.State.ToString()
                    }
                }
            }
            @{ Tarefas = $list } | ConvertTo-Json -Depth 3 -Compress
            """
            res = conn.execute_script(self.target_pc, ps_script)
            
            if res["status"] == "Sucesso" and res.get("json_data"):
                self.finished.emit(res["json_data"].get("Tarefas", []))
            else:
                self.error.emit(res.get("log_saida", "Falha ao ler agendamentos do alvo."))
        except Exception as e:
            self.error.emit(str(e))

class SchedulerView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.db = DatabaseManager()
        self.queue_manager = getattr(main_window_ref, 'queue_manager', None) or TaskQueueManager(max_threads=5)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Agendador de Tarefas Remotas (Automação)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        layout.addWidget(title)

        config_group = QGroupBox("1. Novo Agendamento")
        config_layout = QHBoxLayout(config_group)
        config_layout.setContentsMargins(15, 20, 15, 15)
        
        self.inp_target = QLineEdit()
        self.inp_target.setFixedHeight(32)
        self.inp_target.setPlaceholderText("IP ou Hostname (ex: HUL-WK-244377E)")
        self.inp_target.setStyleSheet("padding: 0 10px;")
        self.inp_target.textChanged.connect(self._force_uppercase)
        
        self.cmb_scripts = QComboBox()
        self.cmb_scripts.setFixedHeight(32)
        self.cmb_scripts.setStyleSheet("padding: 0 10px; font-weight: bold;")
        
        self.btn_reload_scripts = QPushButton("↻ Recarregar Biblioteca")
        self.btn_reload_scripts.setFixedHeight(32)
        self.btn_reload_scripts.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_reload_scripts.setStyleSheet("padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_reload_scripts.clicked.connect(self.load_scripts)
        
        config_layout.addWidget(QLabel("Computador Alvo:"))
        config_layout.addWidget(self.inp_target, stretch=1)
        config_layout.addWidget(QLabel(" Script:"))
        config_layout.addWidget(self.cmb_scripts, stretch=2)
        config_layout.addWidget(self.btn_reload_scripts)
        layout.addWidget(config_group)

        trigger_group = QGroupBox("2. Regra de Execução (Gatilho)")
        trigger_layout = QHBoxLayout(trigger_group)
        trigger_layout.setContentsMargins(15, 20, 15, 15)
        
        self.cmb_trigger = QComboBox()
        self.cmb_trigger.setFixedHeight(32)
        self.cmb_trigger.addItems(["Ao Iniciar a Máquina (Boot)", "Diariamente (Horário Específico)"])
        self.cmb_trigger.setStyleSheet("padding: 0 10px; font-weight: bold;")
        self.cmb_trigger.currentTextChanged.connect(self.toggle_time_input)
        
        self.inp_time = QTimeEdit()
        self.inp_time.setFixedHeight(32)
        self.inp_time.setDisplayFormat("HH:mm")
        self.inp_time.setStyleSheet("padding: 0 10px; font-size: 14px;")
        self.inp_time.setEnabled(False) 
        
        trigger_layout.addWidget(QLabel("Quando?"))
        trigger_layout.addWidget(self.cmb_trigger)
        trigger_layout.addWidget(QLabel("  Horário:"))
        trigger_layout.addWidget(self.inp_time)
        trigger_layout.addStretch()
        
        self.btn_schedule = QPushButton("⏱️ Agendar Tarefa")
        self.btn_schedule.setFixedHeight(32)
        self.btn_schedule.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_schedule.setStyleSheet("background-color: #1e8a5e; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_schedule.clicked.connect(self.schedule_task)
        
        trigger_layout.addWidget(self.btn_schedule)
        layout.addWidget(trigger_group)

        manager_group = QGroupBox("3. Gestão de Tarefas Remotas")
        manager_layout = QVBoxLayout(manager_group)
        manager_layout.setContentsMargins(15, 20, 15, 15)
        
        actions_layout = QHBoxLayout()
        self.btn_list = QPushButton("📋 Buscar Tarefas do Alvo")
        self.btn_list.setFixedHeight(32)
        self.btn_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_list.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_list.clicked.connect(self.fetch_active_tasks)
        
        self.btn_remove = QPushButton("🗑️ Remover Tarefa Selecionada")
        self.btn_remove.setFixedHeight(32)
        self.btn_remove.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_remove.setStyleSheet("background-color: #d9534f; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_remove.clicked.connect(self.remove_selected_task)
        
        actions_layout.addWidget(self.btn_list)
        actions_layout.addWidget(self.btn_remove)
        actions_layout.addStretch()
        manager_layout.addLayout(actions_layout)

        self.tasks_table = QTableWidget(0, 2)
        self.tasks_table.setHorizontalHeaderLabels(["Nome da Tarefa", "Status"])
        self.tasks_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tasks_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tasks_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        manager_layout.addWidget(self.tasks_table)
        
        layout.addWidget(manager_group)

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()
        self.load_scripts()

    def toggle_time_input(self, text):
        if "Diariamente" in text: self.inp_time.setEnabled(True)
        else: self.inp_time.setEnabled(False)

    def load_scripts(self):
        self.cmb_scripts.clear()
        scripts = self.db.get_all_scripts()
        if not scripts: self.cmb_scripts.addItem("Nenhum script salvo na biblioteca.")
        else:
            for s in scripts:
                self.cmb_scripts.addItem(s[1], userData=s[4])

    def fetch_active_tasks(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        self.btn_list.setText("Buscando...")
        self.btn_list.setEnabled(False)
        self.tasks_table.setRowCount(0)

        self.worker = FetchTasksWorker(target)
        self.worker.finished.connect(self.populate_tasks)
        self.worker.error.connect(self.show_task_error)
        self.worker.start()

    def populate_tasks(self, tasks_list):
        self.btn_list.setText("📋 Buscar Tarefas do Alvo")
        self.btn_list.setEnabled(True)
        
        if not tasks_list:
            QMessageBox.information(self, "Lista", "Nenhuma tarefa do SARCC agendada neste computador.")
            return
            
        if not isinstance(tasks_list, list): tasks_list = [tasks_list]
            
        for t in tasks_list:
            row = self.tasks_table.rowCount()
            self.tasks_table.insertRow(row)
            self.tasks_table.setItem(row, 0, QTableWidgetItem(t.get("Name", "-")))
            self.tasks_table.setItem(row, 1, QTableWidgetItem(t.get("State", "-")))

    def show_task_error(self, err):
        self.btn_list.setText("📋 Buscar Tarefas do Alvo")
        self.btn_list.setEnabled(True)
        QMessageBox.warning(self, "Erro", f"Não foi possível ler as tarefas:\n{err}")

    def schedule_task(self):
        target = self.inp_target.text().strip()
        script_nome = self.cmb_scripts.currentText()
        ps_script = self.cmb_scripts.currentData()

        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return
        if not ps_script:
            return

        # --- Agendamento roda como SYSTEM → conta-máquina acessa o share ---
        # NÃO pedimos credenciais aqui. O script detecta em runtime que os
        # placeholders [[ADMIN_*]] não foram substituídos e cai em modo
        # conta-máquina (Kerberos autentica como DOMINIO\NOMEDAMÁQUINA$).
        #
        # Motivo: senha em arquivo .ps1 no disco = vulnerabilidade (admin local
        # consegue ler). Como a conta-máquina tem acesso ao share (validado),
        # evitamos por completo a exposição de credencial.
        if "[[ADMIN_PASS]]" in ps_script or "[[ADMIN_USER]]" in ps_script:
            log.info(
                f"Script '{script_nome}' contém placeholders de credencial — "
                "será agendado em modo conta-máquina (SYSTEM)"
            )

        # Codifica o script TAL COMO ESTÁ (placeholders preservados)
        trigger_type = self.cmb_trigger.currentText()
        trigger_time = self.inp_time.time().toString("HH:mm")
        b64_script = base64.b64encode(ps_script.encode('utf-8')).decode('utf-8')
        task_name = f"SARCC_{script_nome.replace(' ', '_')}"

        ps_remote_script = f"""
        $TaskName = "{task_name}"
        $EncodedScript = "{b64_script}"
        $TriggerType = "{trigger_type}"
        $TriggerTime = "{trigger_time}"
        
        $LogData = @{{ Script = "Agendamento ($TaskName)"; StatusFinal = "SUCESSO"; Detalhes = @() }}
        try {{
            $ScriptDir = "C:\\ProgramData\\SARCC\\Scripts"
            if (-not (Test-Path $ScriptDir)) {{ New-Item -ItemType Directory -Path $ScriptDir -Force | Out-Null }}
            $ScriptPath = "$ScriptDir\\$TaskName.ps1"
            
            [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($EncodedScript)) | Out-File -FilePath $ScriptPath -Encoding UTF8 -Force

            $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            if ($existingTask) {{ Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }}

            $Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ScriptPath`""
            if ($TriggerType -match "Diariamente") {{ $Trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime }} 
            else {{ $Trigger = New-ScheduledTaskTrigger -AtStartup }}

            $Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
            Register-ScheduledTask -TaskName $TaskName -TaskPath "\\SARCC\\" -Action $Action -Trigger $Trigger -Principal $Principal -Force | Out-Null
            $LogData.Detalhes += "Tarefa '$TaskName' agendada com sucesso!"
        }} catch {{
            $LogData.StatusFinal = "ERRO FATAL"; $LogData.Detalhes += $_.Exception.Message
        }} finally {{ $LogData | ConvertTo-Json -Compress | Write-Output }}
        """

        # Sem credentials — o script remoto roda como SYSTEM e detecta
        # modo conta-máquina automaticamente.
        self.disparar_fila(target, f"Agendar: {script_nome}", ps_remote_script, credentials=None)

    def remove_selected_task(self):
        target = self.inp_target.text().strip()
        selected_items = self.tasks_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Aviso", "Selecione uma tarefa na tabela primeiro.")
            return
            
        task_name = self.tasks_table.item(selected_items[0].row(), 0).text()
        
        reply = QMessageBox.question(self, 'Remover', f'Apagar a tarefa "{task_name}" do alvo {target}?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply != QMessageBox.StandardButton.Yes: return

        ps_remote_script = f"""
        $TaskName = "{task_name}"
        $LogData = @{{ Script = "Remover Agendamento ($TaskName)"; StatusFinal = "SUCESSO"; Detalhes = @() }}
        try {{
            $existingTask = Get-ScheduledTask -TaskName$TaskName -ErrorAction SilentlyContinue
            if ($existingTask) {{ 
                Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false 
                $LogData.Detalhes += "Tarefa '$TaskName' removida com sucesso."
            }} else {{
                $LogData.Detalhes += "Tarefa não encontrada."
            }}
            $ScriptPath = "C:\\ProgramData\\SARCC\\Scripts\\$TaskName.ps1"
            if (Test-Path $ScriptPath) {{ Remove-Item -Path$ScriptPath -Force }}
        }} catch {{
            $LogData.StatusFinal = "ERRO"; $LogData.Detalhes +=$_.Exception.Message
        }} finally {{ $LogData | ConvertTo-Json -Compress | Write-Output }}
        """
        
        self.disparar_fila(target, f"Remover: {task_name}", ps_remote_script)
    
    def disparar_fila(self, target, nome_tarefa, script_content, credentials=None):
        self.queue_manager.add_task(
            target_pc=target,
            script_name=nome_tarefa,
            script_content=script_content,
            credentials=credentials,
            on_start=None,
            on_finish=self._on_task_finished_refresh,
            on_error=self._on_task_error
        )
        QMessageBox.information(self, "Enviado", f"A solicitação '{nome_tarefa}' foi enviada.\nA tabela será atualizada quando concluir.")

    @pyqtSlot(str, str, dict)
    def _on_task_finished_refresh(self, target_pc, status, json_data):
        self.fetch_active_tasks()
        
    @pyqtSlot(str, str)
    def _on_task_error(self, target_pc, error_msg):
        QMessageBox.critical(self, "Falha na Ação", f"Ocorreu um erro no servidor {target_pc}:\n{error_msg}")