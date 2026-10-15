import json
import os
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QLineEdit, QPushButton, QTableWidget, 
                             QTableWidgetItem, QHeaderView, QGroupBox, 
                             QMessageBox, QTabWidget, QComboBox, QDialog,
                             QTextEdit, QGridLayout, QApplication)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.remote_connection import RemoteConnectionManager
from core.database import DatabaseManager
from gui.views.base_view import BaseView
from PyQt6.QtWidgets import QDialog, QTextEdit

class EventDetailDialog(QDialog):
    """Dialog para exibir detalhes completos de um evento (resumo ou tabela principal)."""

    def __init__(self, event_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalhes do Evento")
        self.resize(850, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # --- Cabeçalho: campos estruturados ---
        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(20)
        info_grid.setVerticalSpacing(6)

        def mk_label(titulo, valor, cor_valor="#e0e0e0"):
            lbl = QLabel(f"<b>{titulo}:</b> <span style='color:{cor_valor}'>{valor}</span>")
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return lbl

        info_grid.addWidget(mk_label("Data/Hora", event_data.get("Data", "N/A")), 0, 0)
        info_grid.addWidget(
            mk_label("Log", event_data.get("LogName", event_data.get("Log", "N/A"))),
            0, 1,
        )
        info_grid.addWidget(
            mk_label("Nível", event_data.get("Nivel", "N/A"), _get_level_color(event_data)),
            1, 0,
        )
        info_grid.addWidget(mk_label("Fonte", event_data.get("Fonte", "N/A")), 1, 1)

        if event_data.get("ID") is not None:
            info_grid.addWidget(mk_label("ID do Evento", event_data.get("ID", "N/A")), 2, 0)

        layout.addLayout(info_grid)

        # --- Mensagem completa ---
        layout.addWidget(QLabel("<b>Mensagem completa:</b>"))
        txt_msg = QTextEdit()
        txt_msg.setReadOnly(True)
        txt_msg.setPlainText(str(event_data.get("Mensagem", "Sem mensagem.")))
        txt_msg.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 13px; "
            "background-color: #1e1e1e; color: #d4d4d4; "
            "padding: 10px; border: 1px solid #444; border-radius: 4px;"
        )
        layout.addWidget(txt_msg)

        # --- Botões ---
        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Copiar mensagem")
        btn_copy.setFixedHeight(32)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet(
            "padding: 0 15px; background-color: #5bc0de; color: black; "
            "font-weight: bold; border-radius: 4px;"
        )
        btn_copy.clicked.connect(
            lambda: self._copy_to_clipboard(txt_msg.toPlainText())
        )
        btn_layout.addWidget(btn_copy)

        btn_layout.addStretch()

        btn_close = QPushButton("Fechar")
        btn_close.setFixedHeight(32)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet(
            "padding: 0 20px; background-color: #4a90e2; color: white; "
            "font-weight: bold; border-radius: 4px;"
        )
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _copy_to_clipboard(self, texto):
        QApplication.clipboard().setText(texto)
        QMessageBox.information(self, "Copiado", "Mensagem copiada para a área de transferência.")


def _get_level_color(event_data):
    """Retorna cor hex para o nível do evento."""
    nivel = str(event_data.get("Nivel", "")).lower()
    if "critical" in nivel or "crítico" in nivel:
        return "#f44336"
    elif "error" in nivel or "erro" in nivel:
        return "#f0ad4e"
    elif "warning" in nivel or "aviso" in nivel:
        return "#ffc107"
    return "#e0e0e0"

class SysManagerWorker(QThread):
    finished = pyqtSignal(list, str)
    error = pyqtSignal(str)

    def __init__(self, target_pc, action_type, extra_params=None):
        super().__init__()
        self.target_pc = target_pc
        self.action_type = action_type
        self.extra_params = extra_params or {}

    def run(self):
        conn = RemoteConnectionManager()
        ps_script = ""

        if self.action_type == "get_processes":
            ps_script = """
            $p = Get-Process | Select-Object Id, ProcessName, @{Name='MemoryMB';Expression={[math]::Round($_.WorkingSet / 1MB, 2)}}, @{Name='CPU';Expression={[math]::Round($_.CPU, 2)}}
            @{ Data = @($p) } | ConvertTo-Json -Depth 3 -Compress | Write-Output
            """
        elif self.action_type == "kill_process":
            pid = self.extra_params.get("pid")
            nome = self.extra_params.get("name", "Desconhecido")
            ps_script = f"""
            $LogData = @{{
                Script = "Ação de Processo (Kill)"
                Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
                Computador = $env:COMPUTERNAME
                StatusFinal = "SUCESSO"
                Detalhes = @("Alvo: Processo '{nome}' (PID: {pid})", "Comando executado: Stop-Process -Id {pid} -Force")
                Mensagem = "O processo '{nome}' (PID: {pid}) foi encerrado com sucesso à força."
            }}
            try {{
                Stop-Process -Id {pid} -Force -ErrorAction Stop
                @{{ Data = @($LogData) }} | ConvertTo-Json -Depth 4 -Compress | Write-Output
            }} catch {{
                $LogData.StatusFinal = "ERRO"
                $LogData.Mensagem = "Falha ao encerrar processo '{nome}' (PID {pid}): $($_.Exception.Message)"
                @{{ Data = @($LogData) }} | ConvertTo-Json -Depth 4 -Compress | Write-Output
            }}
            """
            
        elif self.action_type == "get_services":
            ps_script = """
            $s = Get-Service | Select-Object Name, DisplayName, @{Name='Status';Expression={$_.Status.ToString()}}
            @{ Data = @($s) } | ConvertTo-Json -Depth 3 -Compress | Write-Output
            """
            
        elif self.action_type == "manage_service":
            svc_name = self.extra_params.get("name")
            action = self.extra_params.get("action")
            acao_pt = {"Start": "iniciado", "Stop": "parado", "Restart": "reiniciado"}.get(str(action), action)
            ps_script = f"""
            $LogData = @{{
                Script = "Ação de Serviço ({action})"
                Inicio = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
                Computador = $env:COMPUTERNAME
                StatusFinal = "SUCESSO"
                Detalhes = @("Alvo: Serviço '{svc_name}'", "Comando executado: {action}-Service -Name '{svc_name}' -Force")
                Mensagem = "O serviço '{svc_name}' foi {acao_pt} com sucesso."
            }}
            try {{
                {action}-Service -Name '{svc_name}' -Force -ErrorAction Stop
                Start-Sleep -Seconds 2
                $checkSvc = Get-Service -Name '{svc_name}' -ErrorAction SilentlyContinue
                $LogData.Detalhes += "Status atual após comando: $($checkSvc.Status)"
                @{{ Data = @($LogData) }} | ConvertTo-Json -Depth 4 -Compress | Write-Output
            }} catch {{
                $LogData.StatusFinal = "ERRO"
                $LogData.Mensagem = "Falha na ação {action} do serviço '{svc_name}': $($_.Exception.Message)"
                @{{ Data = @($LogData) }} | ConvertTo-Json -Depth 4 -Compress | Write-Output
            }}
            """
        elif self.action_type == "get_critical_summary":
            ps_script = """
            $ErrorActionPreference = 'SilentlyContinue'
            $result = @()

            foreach ($logName in @('System', 'Application')) {
                try {
                    $events = Get-WinEvent -FilterHashtable @{LogName=$logName; Level=1,2} -MaxEvents 10 -ErrorAction Stop
                    foreach ($e in $events) {
                        $msg = if ($e.Message) {
                            $m = $e.Message -replace "`r?`n", " "
                            if ($m.Length -gt 200) { $m.Substring(0, 200) + "..." } else { $m }
                        } else { "" }
                        $result += [PSCustomObject]@{
                            LogName = $logName
                            ID = $e.Id
                            Data = $e.TimeCreated.ToString('dd/MM HH:mm:ss')
                            Nivel = $e.LevelDisplayName
                            Fonte = $e.ProviderName
                            Mensagem = $msg
                            TimeCreated = $e.TimeCreated
                        }
                    }
                } catch { }
            }

            $top5 = $result | Sort-Object TimeCreated -Descending | Select-Object -First 5

            @{ Data = @($top5) } | ConvertTo-Json -Depth 4 -Compress
            """


        elif self.action_type == "get_events":
            log_name = self.extra_params.get("log_name", "System")
            level = self.extra_params.get("level", "1,2") 
            max_events = self.extra_params.get("max", 50)
            ps_script = f"""
            try {{
                $events = Get-WinEvent -FilterHashtable @{{LogName='{log_name}'; Level={level}}} -MaxEvents {max_events} -ErrorAction Stop
                $res = @()
                foreach ($e in $events) {{
                    $res += [PSCustomObject]@{{
                        ID = $e.Id
                        Data = $e.TimeCreated.ToString('yyyy-MM-dd HH:mm:ss')
                        Nivel = $e.LevelDisplayName
                        Fonte = $e.ProviderName
                        Mensagem = $e.Message
                    }}
                }}
                @{{ Data = $res }} | ConvertTo-Json -Depth 4 -Compress | Write-Output
            }} catch {{
                @{{ Data = @(@{{ Erro = $($_.Exception.Message) }}) }} | ConvertTo-Json -Depth 3 -Compress | Write-Output
            }}
            """

        try:
            res = conn.execute_script(self.target_pc, ps_script)
            
            if res["status"] == "Sucesso":
                json_data = res.get("json_data", {})
                
                if "Data" in json_data:
                    parsed_data = json_data["Data"]
                    if not isinstance(parsed_data, list):
                        parsed_data = [parsed_data] if parsed_data else []
                    self.finished.emit(parsed_data, self.action_type)
                elif "Mensagem" in json_data and json_data.get("StatusFinal") == "ERRO FATAL":
                    self.error.emit(json_data["Mensagem"])
                else:
                    self.finished.emit([], self.action_type)
            else:
                self.error.emit(res.get("log_saida", "Erro desconhecido na coleta WMI/WinRM."))
        except Exception as e:
            self.error.emit(str(e))

class SystemManagerView(BaseView):
    def __init__(self, main_window_ref=None):
        super().__init__(main_window_ref)
        self.db = DatabaseManager()
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Gerenciador de Processos e Serviços do Sistema")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        layout.addWidget(title)

        target_group = QGroupBox("Computador Alvo")
        target_layout = QHBoxLayout(target_group)
        target_layout.setContentsMargins(15, 20, 15, 15)
        
        self.inp_target = QLineEdit()
        self.inp_target.setFixedHeight(32)
        self.inp_target.setPlaceholderText("Ex: HUL-WK-244377E ou 10.8.128.14")
        self.inp_target.setStyleSheet("padding: 0 10px;")
        self.inp_target.textChanged.connect(self._force_uppercase)
        
        target_layout.addWidget(QLabel("Hostname / IP:"))
        target_layout.addWidget(self.inp_target, stretch=1)
        layout.addWidget(target_group)

        self.tabs = QTabWidget()
        
        # --- ABA 1: PROCESSOS ---
        self.tab_proc = QWidget()
        proc_layout = QVBoxLayout(self.tab_proc)
        
        proc_controls = QHBoxLayout()
        self.inp_search_proc = QLineEdit()
        self.inp_search_proc.setFixedHeight(32)
        self.inp_search_proc.setPlaceholderText("🔍 Filtrar processos...")
        self.inp_search_proc.setStyleSheet("padding: 0 10px;")
        self.inp_search_proc.textChanged.connect(lambda text: self.filter_table(self.tbl_proc, text))
        
        self.btn_load_proc = QPushButton("↻ Listar Processos")
        self.btn_load_proc.setFixedHeight(32)
        self.btn_load_proc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_proc.setStyleSheet("padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_load_proc.clicked.connect(lambda: self.run_worker("get_processes"))
        
        self.btn_kill_proc = QPushButton("❌ Encerrar Processo Selecionado")
        self.btn_kill_proc.setFixedHeight(32)
        self.btn_kill_proc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_kill_proc.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_kill_proc.clicked.connect(self.kill_process)
        
        proc_controls.addWidget(self.inp_search_proc, stretch=1)
        proc_controls.addWidget(self.btn_load_proc)
        proc_controls.addWidget(self.btn_kill_proc)
        proc_layout.addLayout(proc_controls)
        
        self.tbl_proc = QTableWidget(0, 4)
        self.tbl_proc.setHorizontalHeaderLabels(["PID", "Nome do Processo", "Memória (MB)", "CPU"])
        self.tbl_proc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_proc.horizontalHeader().setStretchLastSection(True)
        self.tbl_proc.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_proc.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        proc_layout.addWidget(self.tbl_proc)
        self.tabs.addTab(self.tab_proc, "⚙️ Processos")

        # --- ABA 2: SERVIÇOS ---
        self.tab_svc = QWidget()
        svc_layout = QVBoxLayout(self.tab_svc)
        
        svc_controls = QHBoxLayout()
        self.inp_search_svc = QLineEdit()
        self.inp_search_svc.setFixedHeight(32)
        self.inp_search_svc.setPlaceholderText("🔍 Filtrar serviços...")
        self.inp_search_svc.setStyleSheet("padding: 0 10px;")
        self.inp_search_svc.textChanged.connect(lambda text: self.filter_table(self.tbl_svc, text))
        
        self.btn_load_svc = QPushButton("↻ Listar Serviços")
        self.btn_load_svc.setFixedHeight(32)
        self.btn_load_svc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_svc.setStyleSheet("padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_load_svc.clicked.connect(lambda: self.run_worker("get_services"))
        
        self.btn_start_svc = QPushButton("▶ Iniciar")
        self.btn_start_svc.setFixedHeight(32)
        self.btn_start_svc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start_svc.setStyleSheet("background-color: #1e8a5e; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_start_svc.clicked.connect(lambda: self.manage_service("Start"))
        
        self.btn_stop_svc = QPushButton("⏹ Parar")
        self.btn_stop_svc.setFixedHeight(32)
        self.btn_stop_svc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop_svc.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_stop_svc.clicked.connect(lambda: self.manage_service("Stop"))
        
        self.btn_restart_svc = QPushButton("↻ Reiniciar")
        self.btn_restart_svc.setFixedHeight(32)
        self.btn_restart_svc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restart_svc.setStyleSheet("background-color: #f0ad4e; color: black; font-weight: bold; padding: 0 15px; border-radius: 4px;")
        self.btn_restart_svc.clicked.connect(lambda: self.manage_service("Restart"))
        
        svc_controls.addWidget(self.inp_search_svc, stretch=1)
        svc_controls.addWidget(self.btn_load_svc)
        svc_controls.addWidget(self.btn_start_svc)
        svc_controls.addWidget(self.btn_stop_svc)
        svc_controls.addWidget(self.btn_restart_svc)
        svc_layout.addLayout(svc_controls)
        
        self.tbl_svc = QTableWidget(0, 3)
        self.tbl_svc.setHorizontalHeaderLabels(["Nome", "Display Name", "Status"])
        self.tbl_svc.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_svc.horizontalHeader().setStretchLastSection(True)
        self.tbl_svc.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_svc.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        svc_layout.addWidget(self.tbl_svc)
        self.tabs.addTab(self.tab_svc, "🛠️ Serviços")

        # --- ABA 3: EVENTOS DO WINDOWS ---
        self.tab_events = QWidget()
        ev_layout = QVBoxLayout(self.tab_events)
        ev_layout.setContentsMargins(12, 12, 12, 12)
        ev_layout.setSpacing(10)
        ev_layout.setContentsMargins(5, 5, 5, 5)
        ev_layout.setSpacing(6)

        # ---- Painel de Resumo: Últimos 5 Críticos/Erros (System + Application) ----
        summary_header = QHBoxLayout()
        summary_header.setContentsMargins(0, 0, 0, 0)
        summary_header.setSpacing(12)

        lbl_summary_title = QLabel("🚨 Últimos 5 Eventos Críticos / Erros")
        lbl_summary_title.setStyleSheet("font-weight: bold; color: #4a90e2; font-size: 13px;")
        summary_header.addWidget(lbl_summary_title)

        summary_header.addStretch()

        self.lbl_summary_status = QLabel("Não carregado.")
        self.lbl_summary_status.setStyleSheet(
            "color: #888; font-style: italic; font-size: 12px;"
        )
        summary_header.addWidget(self.lbl_summary_status)

        self.btn_refresh_summary = QPushButton("↻ Atualizar Resumo")
        self.btn_refresh_summary.setFixedHeight(32)
        self.btn_refresh_summary.setMinimumWidth(160)
        self.btn_refresh_summary.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh_summary.setStyleSheet(
            "padding: 0 15px; background-color: #2a7de1; color: white; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_refresh_summary.clicked.connect(self.load_critical_summary)
        summary_header.addWidget(self.btn_refresh_summary)

        ev_layout.addLayout(summary_header)

        self.tbl_summary = QTableWidget(0, 5)
        self.tbl_summary.setHorizontalHeaderLabels(["Data/Hora", "Log", "Nível", "Fonte", "Resumo"])
        self.tbl_summary.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_summary.horizontalHeader().resizeSection(0, 110)
        self.tbl_summary.horizontalHeader().resizeSection(1, 80)
        self.tbl_summary.horizontalHeader().resizeSection(2, 80)
        self.tbl_summary.horizontalHeader().resizeSection(3, 170)
        self.tbl_summary.horizontalHeader().setStretchLastSection(True)
        self.tbl_summary.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_summary.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_summary.setWordWrap(False)
        self.tbl_summary.verticalHeader().setVisible(False)
        self.tbl_summary.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_summary.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tbl_summary.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.tbl_summary.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tbl_summary.cellDoubleClicked.connect(self._on_summary_double_click)
        # Altura inicial mínima (será ajustada dinamicamente ao popular)
        self.tbl_summary.setFixedHeight(90)
        ev_layout.addWidget(self.tbl_summary)

        # Espaçador visual entre o resumo e a seção de busca
        ev_layout.addSpacing(15)

        # ---- Controles de busca de eventos ----
        ev_controls = QHBoxLayout()
        ev_controls.setSpacing(8)

        self.cmb_ev_log = QComboBox()
        self.cmb_ev_log.setFixedHeight(32)
        self.cmb_ev_log.addItems(["System", "Application", "Security"])
        self.cmb_ev_log.setStyleSheet("padding: 0 10px;")

        self.cmb_ev_level = QComboBox()
        self.cmb_ev_level.setFixedHeight(32)
        self.cmb_ev_level.addItem("Crítico / Erro", "1,2")
        self.cmb_ev_level.addItem("Aviso", "3")
        self.cmb_ev_level.addItem("Informação", "4")
        self.cmb_ev_level.setStyleSheet("padding: 0 10px;")

        self.cmb_ev_max = QComboBox()
        self.cmb_ev_max.setFixedHeight(32)
        self.cmb_ev_max.addItems(["20", "50", "100", "200"])
        self.cmb_ev_max.setStyleSheet("padding: 0 10px;")

        self.inp_search_ev = QLineEdit()
        self.inp_search_ev.setFixedHeight(32)
        self.inp_search_ev.setPlaceholderText("🔍 Filtrar eventos...")
        self.inp_search_ev.setStyleSheet("padding: 0 10px;")
        self.inp_search_ev.textChanged.connect(lambda text: self.filter_table(self.tbl_events, text))

        self.btn_load_events = QPushButton("🔍 Buscar Eventos")
        self.btn_load_events.setFixedHeight(32)
        self.btn_load_events.setMinimumWidth(160)
        self.btn_load_events.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_events.setStyleSheet(
            "background-color: #2a7de1; color: white; font-weight: bold; "
            "padding: 0 15px; border-radius: 4px;"
        )
        self.btn_load_events.clicked.connect(lambda: self.run_worker("get_events"))

        ev_controls.addWidget(QLabel("Log:"))
        ev_controls.addWidget(self.cmb_ev_log)
        ev_controls.addWidget(QLabel("Nível:"))
        ev_controls.addWidget(self.cmb_ev_level)
        ev_controls.addWidget(QLabel("Limite:"))
        ev_controls.addWidget(self.cmb_ev_max)
        ev_controls.addWidget(self.inp_search_ev, stretch=1)
        ev_controls.addWidget(self.btn_load_events)
        ev_layout.addLayout(ev_controls)

        self.tbl_events = QTableWidget(0, 5)
        self.tbl_events.setHorizontalHeaderLabels(["ID", "Data/Hora", "Nível", "Fonte", "Mensagem"])
        self.tbl_events.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_events.horizontalHeader().resizeSection(0, 60)
        self.tbl_events.horizontalHeader().resizeSection(1, 140)
        self.tbl_events.horizontalHeader().resizeSection(2, 80)
        self.tbl_events.horizontalHeader().resizeSection(3, 150)
        self.tbl_events.horizontalHeader().setStretchLastSection(True)
        self.tbl_events.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_events.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_events.setWordWrap(True)
        self.tbl_events.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_events.cellDoubleClicked.connect(self._on_events_double_click)
        ev_layout.addWidget(self.tbl_events)

        self.tabs.addTab(self.tab_events, "📋 Logs de Eventos")
        self.tabs.currentChanged.connect(self.on_tab_changed)
        layout.addWidget(self.tabs)

    def filter_table(self, table, text):
        search_text = text.lower()
        for row in range(table.rowCount()):
            match = False
            for col in range(table.columnCount()):
                item = table.item(row, col)
                if item and search_text in item.text().lower():
                    match = True
                    break
            table.setRowHidden(row, not match)

    def _on_summary_double_click(self, row, col):
        item = self.tbl_summary.item(row, 0)
        if not item:
            return
        event_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(event_data, dict):
            EventDetailDialog(event_data, parent=self).exec()

    def _on_events_double_click(self, row, col):
        item = self.tbl_events.item(row, 0)
        if not item:
            return
        event_data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(event_data, dict):
            EventDetailDialog(event_data, parent=self).exec()

    def run_worker(self, action_type, extra_params=None):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        if action_type == "get_events":
            if not extra_params: extra_params = {}
            extra_params["log_name"] = self.cmb_ev_log.currentText()
            extra_params["level"] = self.cmb_ev_level.currentData()
            extra_params["max"] = self.cmb_ev_max.currentText()

        self.worker = SysManagerWorker(target, action_type, extra_params)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(lambda e: QMessageBox.critical(self, "Erro", str(e)))
        self.worker.start()

    def kill_process(self):
        row = self.tbl_proc.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um processo na tabela.")
            return
            
        pid = self.tbl_proc.item(row, 0).text()
        name = self.tbl_proc.item(row, 1).text()
        
        reply = QMessageBox.question(self, 'Confirmar', f'Deseja forçar o encerramento do processo {name} (PID: {pid})?', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.run_worker("kill_process", {"pid": pid, "name": name})

    def manage_service(self, action):
        row = self.tbl_svc.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um serviço na tabela.")
            return
            
        name = self.tbl_svc.item(row, 0).text()
        self.run_worker("manage_service", {"name": name, "action": action})

    def load_critical_summary(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        self.btn_refresh_summary.setEnabled(False)
        self.btn_refresh_summary.setText("Carregando...")
        self.lbl_summary_status.setText("Consultando eventos recentes...")
        self.lbl_summary_status.setStyleSheet(
            "color: #f0ad4e; font-style: italic; margin-right: 10px;"
        )

        self.run_worker("get_critical_summary")
        
    def _adjust_summary_height(self):
        """Ajusta altura da tabela resumo com base no conteúdo — sem scroll, sem corte."""
        rows = self.tbl_summary.rowCount()
        header_h = self.tbl_summary.horizontalHeader().height()
        # Altura de linha: usa a real se existir alguma, senão assume 30px
        if rows > 0:
            row_h = self.tbl_summary.rowHeight(0) or 30
        else:
            row_h = 30
        # Mostra pelo menos 1 linha vazia (feedback visual de "tabela existe")
        visible_rows = max(rows, 1)
        total = header_h + (row_h * visible_rows) + 4
        self.tbl_summary.setFixedHeight(total)

    def populate_critical_summary(self, data_list):
        self.btn_refresh_summary.setEnabled(True)
        self.btn_refresh_summary.setText("↻ Atualizar Resumo")

        self.tbl_summary.setSortingEnabled(False)
        self.tbl_summary.setRowCount(0)

        if not data_list:
            self.lbl_summary_status.setText("✓ Nenhum evento crítico/erro recente.")
            self.lbl_summary_status.setStyleSheet(
                "color: #4CAF50; font-style: italic; margin-right: 10px;"
            )
            self._adjust_summary_height()
            return

        for e in data_list:
            if not isinstance(e, dict):
                continue
            r = self.tbl_summary.rowCount()
            self.tbl_summary.insertRow(r)

            # Guarda o dict completo na coluna 0 para o dialog de detalhes
            item_data = QTableWidgetItem(str(e.get("Data", "")))
            item_data.setData(Qt.ItemDataRole.UserRole, e)
            self.tbl_summary.setItem(r, 0, item_data)

            self.tbl_summary.setItem(r, 1, QTableWidgetItem(str(e.get("LogName", ""))))

            lvl_item = QTableWidgetItem(str(e.get("Nivel", "")))
            lvl_txt = lvl_item.text().lower()
            if "critical" in lvl_txt or "crítico" in lvl_txt:
                lvl_item.setForeground(Qt.GlobalColor.red)
            elif "error" in lvl_txt or "erro" in lvl_txt:
                lvl_item.setForeground(Qt.GlobalColor.darkYellow)
            self.tbl_summary.setItem(r, 2, lvl_item)

            self.tbl_summary.setItem(r, 3, QTableWidgetItem(str(e.get("Fonte", ""))))
            self.tbl_summary.setItem(r, 4, QTableWidgetItem(str(e.get("Mensagem", ""))))

        self.tbl_summary.setSortingEnabled(True)
        self.lbl_summary_status.setText(f"{len(data_list)} evento(s) recente(s).")
        self.lbl_summary_status.setStyleSheet(
            "color: #888; font-style: italic; margin-right: 10px;"
        )

        self._adjust_summary_height()
    def on_tab_changed(self, index):
        """Auto-carrega o resumo de eventos quando o usuário entra na aba."""
        if index == 2:  # ABA 3 — Logs de Eventos
            if self.inp_target.text().strip() and self.tbl_summary.rowCount() == 0:
                self.load_critical_summary()
                
    def on_worker_finished(self, data_list, action_type):
        
        executor = os.environ.get("USERNAME", "Desconhecido")
        target = self.inp_target.text().strip()
        if action_type == "get_critical_summary":
            self.populate_critical_summary(data_list)
            return
        if action_type in ["kill_process", "manage_service"]:
            log_dict = data_list[0] if data_list else {}
            status_final = log_dict.get("StatusFinal", "SUCESSO")
            mensagem = log_dict.get("Mensagem", "Ação concluída.")
            
            script_name = "Encerrar Processo" if action_type == "kill_process" else "Gerenciar Serviço"
            modulo = "[Gerenciador] Processos" if action_type == "kill_process" else "[Gerenciador] Serviços"

            self.db.save_execution(
                target_pc=target, 
                script_name=script_name, 
                status=status_final, 
                result_data=json.dumps(log_dict, ensure_ascii=False) if log_dict else mensagem, 
                technician=executor, 
                module=modulo
            )
            
            if status_final == "SUCESSO":
                QMessageBox.information(self, "Sucesso", mensagem)
            else:
                QMessageBox.warning(self, "Aviso da Ação", mensagem)
                
            if action_type == "kill_process":
                self.run_worker("get_processes")
            else:
                self.run_worker("get_services")
            return

        if len(data_list) > 0 and "Erro" in data_list[0]:
            QMessageBox.warning(self, "Aviso do Sistema Alvo", data_list[0]["Erro"])
            return

        if action_type == "get_processes":
            self.tbl_proc.setSortingEnabled(False)
            self.tbl_proc.setRowCount(0)
            
            for p in data_list:
                r = self.tbl_proc.rowCount()
                self.tbl_proc.insertRow(r)
                
                item_id = QTableWidgetItem()
                item_id.setData(Qt.ItemDataRole.EditRole, int(p.get("Id", 0)))
                self.tbl_proc.setItem(r, 0, item_id)
                
                self.tbl_proc.setItem(r, 1, QTableWidgetItem(str(p.get("ProcessName", ""))))
                
                item_mem = QTableWidgetItem()
                item_mem.setData(Qt.ItemDataRole.EditRole, float(p.get("MemoryMB", 0)))
                self.tbl_proc.setItem(r, 2, item_mem)
                
                item_cpu = QTableWidgetItem()
                item_cpu.setData(Qt.ItemDataRole.EditRole, float(p.get("CPU", 0)))
                self.tbl_proc.setItem(r, 3, item_cpu)
                
            self.tbl_proc.setSortingEnabled(True)
            self.filter_table(self.tbl_proc, self.inp_search_proc.text())
                
        elif action_type == "get_services":
            self.tbl_svc.setSortingEnabled(False)
            self.tbl_svc.setRowCount(0)
            
            for s in data_list:
                r = self.tbl_svc.rowCount()
                self.tbl_svc.insertRow(r)
                
                self.tbl_svc.setItem(r, 0, QTableWidgetItem(str(s.get("Name", ""))))
                self.tbl_svc.setItem(r, 1, QTableWidgetItem(str(s.get("DisplayName", ""))))
                
                status_str = str(s.get("Status", ""))
                status_item = QTableWidgetItem()
                
                if "Running" in status_str:
                    status_item.setText("Em Execução")
                    status_item.setForeground(Qt.GlobalColor.green)
                elif "Stopped" in status_str:
                    status_item.setText("Parado")
                    status_item.setForeground(Qt.GlobalColor.red)
                else:
                    status_item.setText(status_str)
                    
                self.tbl_svc.setItem(r, 2, status_item)
                
            self.tbl_svc.setSortingEnabled(True)
            self.filter_table(self.tbl_svc, self.inp_search_svc.text())
                
        elif action_type == "get_events":
            self.tbl_events.setSortingEnabled(False)
            self.tbl_events.setRowCount(0)
            
            for e in data_list:
                r = self.tbl_events.rowCount()
                self.tbl_events.insertRow(r)
                
                item_id = QTableWidgetItem()
                try:
                    item_id.setData(Qt.ItemDataRole.EditRole, int(e.get("ID", 0)))
                except:
                    item_id.setData(Qt.ItemDataRole.EditRole, str(e.get("ID", "")))
                
                # Guarda o dict completo na coluna 0 para o dialog de detalhes
                item_id.setData(Qt.ItemDataRole.UserRole, e)
                self.tbl_events.setItem(r, 0, item_id)
                self.tbl_events.setItem(r, 1, QTableWidgetItem(str(e.get("Data", ""))))
                
                lvl_item = QTableWidgetItem(str(e.get("Nivel", "")))
                if "Error" in lvl_item.text() or "Critical" in lvl_item.text():
                    lvl_item.setForeground(Qt.GlobalColor.red)
                elif "Warning" in lvl_item.text():
                    lvl_item.setForeground(Qt.GlobalColor.darkYellow)
                    
                self.tbl_events.setItem(r, 2, lvl_item)
                self.tbl_events.setItem(r, 3, QTableWidgetItem(str(e.get("Fonte", ""))))
                self.tbl_events.setItem(r, 4, QTableWidgetItem(str(e.get("Mensagem", ""))))
                
            self.tbl_events.setSortingEnabled(True)
            self.filter_table(self.tbl_events, self.inp_search_ev.text())

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()