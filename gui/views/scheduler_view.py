import os
import base64
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, 
    QGroupBox, QComboBox, QMessageBox, QTableWidget, QTableWidgetItem, 
    QHeaderView, QAbstractItemView, QTimeEdit, QDateEdit, QCheckBox
)
from PyQt6.QtCore import Qt, pyqtSlot, QDate, QTime

from core.task_queue import TaskQueueManager
from core.database import DatabaseManager
from core.ps_loader import load_ps_template, PsTemplateError
from core.config import get_ps_scripts_dir, get_data_dir
from gui.views.base_view import BaseView

class SchedulerView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.queue_manager = getattr(main_window_ref, 'queue_manager', None) or TaskQueueManager(max_threads=5)
        self.db = DatabaseManager()
        self._setup_ui()
        self.load_local_scripts()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Agendador de Tarefas Remotas (Automação)")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        main_layout.addWidget(title)

        group_schedule = QGroupBox("1. Novo Agendamento Automático")
        layout_schedule = QVBoxLayout(group_schedule)
        layout_schedule.setContentsMargins(15, 20, 15, 15)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Computador Alvo:"))
        self.inp_target = QLineEdit()
        self.inp_target.setPlaceholderText("Ex: HUL-WK-TESTE")
        self.inp_target.textChanged.connect(self._force_uppercase)
        row1.addWidget(self.inp_target, stretch=2)

        row1.addSpacing(15)

        row1.addWidget(QLabel("Script a Executar:"))
        self.cmb_scripts = QComboBox()
        row1.addWidget(self.cmb_scripts, stretch=3)

        btn_reload = QPushButton("↻ Recarregar Biblioteca")
        btn_reload.clicked.connect(self.load_local_scripts)
        row1.addWidget(btn_reload)
        layout_schedule.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Quando iniciar?"))
        
        self.cmb_trigger = QComboBox()
        self.cmb_trigger.addItems([
            "Uma vez (Data/Hora específica)",
            "Diariamente", 
            "Semanalmente",
            "Ao Iniciar o Computador (Boot)", 
            "Ao Fazer Logon"
        ])
        self.cmb_trigger.currentIndexChanged.connect(self._toggle_trigger_options)
        row2.addWidget(self.cmb_trigger)

        self.lbl_date = QLabel(" Data:")
        row2.addWidget(self.lbl_date)
        self.date_picker = QDateEdit()
        self.date_picker.setDisplayFormat("dd/MM/yyyy")
        self.date_picker.setDate(QDate.currentDate())
        self.date_picker.setCalendarPopup(True)
        row2.addWidget(self.date_picker)

        self.lbl_time = QLabel(" Horário:")
        row2.addWidget(self.lbl_time)
        self.time_picker = QTimeEdit()
        self.time_picker.setDisplayFormat("HH:mm")
        self.time_picker.setTime(QTime.currentTime())
        row2.addWidget(self.time_picker)

        self.widget_days = QWidget()
        layout_days = QHBoxLayout(self.widget_days)
        layout_days.setContentsMargins(10, 0, 0, 0)
        self.chk_days = {}
        for day_name, day_val in [("Seg", "Monday"), ("Ter", "Tuesday"), ("Qua", "Wednesday"), 
                                  ("Qui", "Thursday"), ("Sex", "Friday"), ("Sáb", "Saturday"), ("Dom", "Sunday")]:
            chk = QCheckBox(day_name)
            self.chk_days[day_val] = chk
            layout_days.addWidget(chk)
        row2.addWidget(self.widget_days)

        row2.addStretch()

        self.btn_schedule = QPushButton("⏱ Agendar Tarefa no Alvo")
        self.btn_schedule.setFixedHeight(32)
        self.btn_schedule.setStyleSheet("background-color: #1e8a5e; color: white; font-weight: bold; padding: 0 20px; border-radius: 4px;")
        self.btn_schedule.clicked.connect(self.schedule_task)
        row2.addWidget(self.btn_schedule)

        layout_schedule.addLayout(row2)
        main_layout.addWidget(group_schedule)

        group_manage = QGroupBox("2. Gestão de Tarefas Remotas Ativas")
        layout_manage = QVBoxLayout(group_manage)
        layout_manage.setContentsMargins(15, 20, 15, 15)

        btn_layout = QHBoxLayout()
        self.btn_fetch = QPushButton("📋 Buscar Tarefas do Alvo")
        self.btn_fetch.setFixedHeight(32)
        self.btn_fetch.setStyleSheet("background-color: #2a7de1; color: white; font-weight: bold; padding: 0 20px; border-radius: 4px;")
        self.btn_fetch.clicked.connect(self.fetch_tasks)
        btn_layout.addWidget(self.btn_fetch)

        self.btn_remove = QPushButton("🗑 Remover Tarefa Selecionada")
        self.btn_remove.setFixedHeight(32)
        self.btn_remove.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 0 20px; border-radius: 4px;")
        self.btn_remove.clicked.connect(self.remove_task)
        btn_layout.addWidget(self.btn_remove)
        
        btn_layout.addStretch()
        layout_manage.addLayout(btn_layout)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Nome da Tarefa", "Status", "Gatilho", "Última Execução", "Próxima Execução"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.verticalHeader().setVisible(False)
        layout_manage.addWidget(self.table)

        main_layout.addWidget(group_manage, stretch=1)
        self._toggle_trigger_options()

    def load_local_scripts(self):
        self.cmb_scripts.clear()
        
        paths_to_check = [
            get_data_dir() / "scripts",
            get_ps_scripts_dir() / "user_scripts"
        ]
        
        found_any = False
        for path in paths_to_check:
            if not path.exists():
                try: path.mkdir(parents=True, exist_ok=True)
                except: pass
            
            if path.exists():
                for file in path.glob("*.ps1"):
                    self.cmb_scripts.addItem(file.stem, str(file))
                    found_any = True
                    
        if not found_any:
            self.cmb_scripts.addItem("<Nenhum script na pasta data/scripts>", "")

    def _toggle_trigger_options(self):
        trigger = self.cmb_trigger.currentText()
        
        self.lbl_time.hide()
        self.time_picker.hide()
        self.lbl_date.hide()
        self.date_picker.hide()
        self.widget_days.hide()
        
        if trigger == "Uma vez (Data/Hora específica)":
            self.lbl_date.show()
            self.date_picker.show()
            self.lbl_time.show()
            self.time_picker.show()
        elif trigger == "Diariamente":
            self.lbl_time.show()
            self.time_picker.show()
        elif trigger == "Semanalmente":
            self.lbl_time.show()
            self.time_picker.show()
            self.widget_days.show()

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()
        self.load_local_scripts()

    def schedule_task(self):
        target = self.inp_target.text().strip()
        if not target:
            return QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
        
        script_path = self.cmb_scripts.currentData()
        if not script_path or not Path(script_path).exists():
            return QMessageBox.warning(self, "Aviso", "Não existem scripts válidos selecionados.")

        script_name = self.cmb_scripts.currentText()
        
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            # Gera o Base64, mas envia como parâmetro 'script_b64' em vez de embutir no script_content
            b64_payload = base64.b64encode(script_content.encode('utf-8')).decode('ascii').replace('\n', '')
        except Exception as e:
            return QMessageBox.critical(self, "Erro", f"Falha ao ler o script local:\n{e}")

        ui_trigger = self.cmb_trigger.currentText()
        trigger_type = "Daily"
        trigger_days = ""

        if "Boot" in ui_trigger: trigger_type = "Boot"
        elif "Logon" in ui_trigger: trigger_type = "Logon"
        elif "Uma vez" in ui_trigger: trigger_type = "Once"
        elif "Diariamente" in ui_trigger: trigger_type = "Daily"
        elif "Semanalmente" in ui_trigger: 
            trigger_type = "Weekly"
            selected_days = [val for val, chk in self.chk_days.items() if chk.isChecked()]
            if not selected_days:
                return QMessageBox.warning(self, "Aviso", "Selecione pelo menos um dia da semana.")
            trigger_days = ",".join(selected_days)

        trigger_time = self.time_picker.time().toString("HH:mm")
        trigger_iso = f"{self.date_picker.date().toString('yyyy-MM-dd')}T{self.time_picker.time().toString('HH:mm:00')}"

        try:
            # Nota: O template schedule_task.ps1 já deve ter {{script_b64}} escrito. Não o vamos
            # embutir aqui no load_ps_template para evitar explodir a limitação de 8191 caracteres do PS.
            ps_script = load_ps_template(
                "scheduler", "schedule_task",
                task_name=script_name,
                trigger_type=trigger_type,
                trigger_time=trigger_time,
                trigger_iso=trigger_iso,
                trigger_days=trigger_days
            )
        except PsTemplateError as e:
            return QMessageBox.critical(self, "Erro", f"Falha no template:\n{e}")

        self.btn_schedule.setEnabled(False)
        self.btn_schedule.setText("Agendando...")

        # --- A injeção pesada acontece na TaskQueue via `script_b64=b64_payload` ---
        self.queue_manager.add_task(
            target_pc=target, script_name=f"Agendar: {script_name}", script_content=ps_script,
            module_name="[Scheduler] Agendamento", script_b64=b64_payload,
            on_finish=lambda t, s, d: self._on_task_done("Agendamento concluído.", d),
            on_error=lambda t, e: self._on_task_error(e)
        )

    def fetch_tasks(self):
        target = self.inp_target.text().strip()
        if not target:
            return QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")

        try:
            ps_script = load_ps_template("scheduler", "fetch_tasks")
        except PsTemplateError as e:
            return QMessageBox.critical(self, "Erro", f"Falha no template:\n{e}")

        self.btn_fetch.setEnabled(False)
        self.btn_fetch.setText("Buscando...")
        self.table.setRowCount(0)

        self.queue_manager.add_task(
            target_pc=target, script_name="Listar Tarefas Agendadas", script_content=ps_script,
            module_name="[Scheduler] Listagem",
            on_finish=lambda t, s, d: self._on_fetch_success(d),
            on_error=lambda t, e: self._on_task_error(e)
        )

    def remove_task(self):
        target = self.inp_target.text().strip()
        # Coleta todas as linhas que o utilizador selecionou (com Ctrl/Shift)
        selected_rows = sorted(list(set(idx.row() for idx in self.table.selectedIndexes())))
        
        if not target or not selected_rows:
            return QMessageBox.warning(self, "Aviso", "Selecione pelo menos uma tarefa na lista (use Ctrl ou Shift para várias).")

        # Puxa o nome exato da tarefa da Coluna 0
        task_names = [self.table.item(r, 0).text() for r in selected_rows]
        tasks_str = "\n".join(f"- {t}" for t in task_names)
        
        reply = QMessageBox.question(self, "Confirmação Múltipla", f"Remover {len(task_names)} tarefa(s) do alvo?\n\n{tasks_str}")
        if reply != QMessageBox.StandardButton.Yes: return

        try:
            # Envia todos os nomes numa única string separada por vírgula
            ps_script = load_ps_template("scheduler", "remove_task", task_names=",".join(task_names))
        except PsTemplateError as e:
            return QMessageBox.critical(self, "Erro", f"Falha no template:\n{e}")

        self.btn_remove.setEnabled(False)
        self.queue_manager.add_task(
            target_pc=target, script_name=f"Remover {len(task_names)} Tarefa(s)", script_content=ps_script,
            module_name="[Scheduler] Remoção",
            on_finish=lambda t, s, d: self._on_remove_success(d),
            on_error=lambda t, e: self._on_task_error(e)
        )

    @pyqtSlot(dict)
    def _on_remove_success(self, data):
        self.btn_remove.setEnabled(True)
        QMessageBox.information(self, "Sucesso", data.get("Mensagem", "Tarefas removidas."))
        self.fetch_tasks()

    @pyqtSlot(dict)
    def _on_fetch_success(self, data):
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("📋 Buscar Tarefas do Alvo")
        
        tasks = data.get("Tasks", [])
        if not isinstance(tasks, list):
            tasks = [tasks] if tasks else []

        self.table.setSortingEnabled(False)
        self.table.setRowCount(0) # Limpa tudo primeiro

        for t in tasks:
            r = self.table.rowCount()
            self.table.insertRow(r)
            
            self.table.setItem(r, 0, QTableWidgetItem(t.get("TaskName", "")))
            
            status = t.get("Status", "")
            item_status = QTableWidgetItem(status)
            item_status.setForeground(Qt.GlobalColor.green if status.lower() == "ready" else Qt.GlobalColor.darkYellow)
            self.table.setItem(r, 1, item_status)
            
            self.table.setItem(r, 2, QTableWidgetItem(t.get("Trigger", "Desconhecido")))
            self.table.setItem(r, 3, QTableWidgetItem(t.get("LastRun", "N/A")))
            self.table.setItem(r, 4, QTableWidgetItem(t.get("NextRun", "N/A")))
            
        self.table.setSortingEnabled(True)

    @pyqtSlot(str, dict)
    def _on_task_done(self, msg, data):
        self.btn_schedule.setEnabled(True)
        self.btn_schedule.setText("⏱ Agendar Tarefa no Alvo")
        QMessageBox.information(self, "Concluído", data.get("Mensagem", msg))
        self.fetch_tasks()

    @pyqtSlot(str)
    def _on_task_error(self, err_msg):
        self.btn_schedule.setEnabled(True)
        self.btn_schedule.setText("⏱ Agendar Tarefa no Alvo")
        self.btn_fetch.setEnabled(True)
        self.btn_fetch.setText("📋 Buscar Tarefas do Alvo")
        self.btn_remove.setEnabled(True)
        QMessageBox.critical(self, "Erro Remoto", err_msg)