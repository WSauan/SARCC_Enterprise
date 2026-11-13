import json
import os
import base64
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QHeaderView, QGroupBox,
    QMessageBox, QTabWidget, QComboBox, QDialog,
    QTextEdit, QGridLayout, QApplication
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

from core.remote_connection import RemoteConnectionManager
from core.ps_loader import load_ps_template, PsTemplateError
from infrastructure.repositories.execution_repository import ExecutionRepository
from gui.views.base_view import BaseView
from gui.views.software_view import fix_mojibake


def safe_int(value, default: int = 0) -> int:
    """Converte valores (incluindo None ou strings vazias) para int sem levantar exceção."""
    if value is None or value == "":
        return default
    try:
        return int(float(str(value).replace(",", ".").strip()))
    except (ValueError, TypeError):
        return default


def safe_float(value, default: float = 0.0) -> float:
    """Converte valores (incluindo None ou strings com vírgula) para float com segurança."""
    if value is None or value == "":
        return default
    try:
        return round(float(str(value).replace(",", ".").strip()), 2)
    except (ValueError, TypeError):
        return default


def normalize_service_status(raw_status) -> tuple[str, Qt.GlobalColor | None]:
    """Padroniza o status do serviço do Windows (texto em EN/PT ou enum numérico WMI/ServiceController)."""
    s = fix_mojibake(str(raw_status or "")).strip()
    low = s.lower()
    if low in ("running", "4", "em execução", "em execucao"):
        return "Em Execução", Qt.GlobalColor.green
    if low in ("stopped", "1", "parado"):
        return "Parado", Qt.GlobalColor.red
    if low in ("paused", "7", "pausado"):
        return "Pausado", Qt.GlobalColor.darkYellow
    return (s if s else "Desconhecido"), None


class EventDetailDialog(QDialog):
    """Dialog para exibir detalhes completos de um evento."""

    def __init__(self, event_data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detalhes do Evento")
        self.resize(850, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        info_grid = QGridLayout()
        info_grid.setHorizontalSpacing(20)
        info_grid.setVerticalSpacing(6)

        def mk_label(titulo, valor, cor_valor="#e0e0e0"):
            val_clean = fix_mojibake(str(valor))
            lbl = QLabel(f"<b>{titulo}:</b> <span style='color:{cor_valor}'>{val_clean}</span>")
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

        layout.addWidget(QLabel("<b>Mensagem completa:</b>"))
        txt_msg = QTextEdit()
        txt_msg.setReadOnly(True)
        txt_msg.setPlainText(fix_mojibake(str(event_data.get("Mensagem", "Sem mensagem."))))
        txt_msg.setStyleSheet(
            "font-family: Consolas, monospace; font-size: 13px; "
            "background-color: #1e1e1e; color: #d4d4d4; "
            "padding: 10px; border: 1px solid #444; border-radius: 4px;"
        )
        layout.addWidget(txt_msg)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("📋 Copiar mensagem")
        btn_copy.setFixedHeight(32)
        btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_copy.setStyleSheet(
            "padding: 0 15px; background-color: #5bc0de; color: black; "
            "font-weight: bold; border-radius: 4px;"
        )
        btn_copy.clicked.connect(lambda: self._copy_to_clipboard(txt_msg.toPlainText()))
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
    nivel = fix_mojibake(str(event_data.get("Nivel", ""))).lower()
    if "critical" in nivel or "crítico" in nivel or "critico" in nivel:
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

    def _b64(self, text):
        return base64.b64encode(str(text).encode("utf-8")).decode("ascii")

    def _build_script(self) -> str:
        if self.action_type == "get_processes":
            return load_ps_template("system_manager", "get_processes")

        if self.action_type == "kill_process":
            return load_ps_template(
                "system_manager", "kill_process",
                pid_b64=self._b64(self.extra_params.get("pid")),
                nome_b64=self._b64(self.extra_params.get("name", "Desconhecido")),
            )

        if self.action_type == "get_services":
            return load_ps_template("system_manager", "get_services")

        if self.action_type == "manage_service":
            action = self.extra_params.get("action")
            acao_pt = {"Start": "iniciado", "Stop": "parado", "Restart": "reiniciado"}.get(str(action), action)
            return load_ps_template(
                "system_manager", "manage_service",
                svc_name_b64=self._b64(self.extra_params.get("name")),
                action_b64=self._b64(action),
                acao_pt_b64=self._b64(acao_pt),
            )

        if self.action_type == "get_critical_summary":
            return load_ps_template("system_manager", "get_critical_summary")

        if self.action_type == "get_events":
            return load_ps_template(
                "system_manager", "get_events",
                log_name=self.extra_params.get("log_name", "System"),
                level=self.extra_params.get("level", "1,2"),
                max_events=self.extra_params.get("max", 50),
            )

        raise PsTemplateError(f"action_type desconhecido: {self.action_type}")

    def run(self):
        try:
            ps_script = self._build_script()
        except PsTemplateError as e:
            self.error.emit(f"Erro de configuração interna: {e}")
            return

        conn = RemoteConnectionManager()
        try:
            res = conn.execute_script(self.target_pc, ps_script)

            if res["status"] == "Sucesso":
                json_data = res.get("json_data", {})
                if not isinstance(json_data, dict):
                    json_data = {}

                if "Data" in json_data:
                    parsed_data = json_data["Data"]
                    if not isinstance(parsed_data, list):
                        parsed_data = [parsed_data] if parsed_data else []
                    self.finished.emit(parsed_data, self.action_type)
                elif json_data.get("StatusFinal") == "ERRO FATAL" and "Mensagem" in json_data:
                    self.error.emit(fix_mojibake(str(json_data["Mensagem"])))
                elif "StatusFinal" in json_data or "Mensagem" in json_data:
                    self.finished.emit([json_data], self.action_type)
                else:
                    self.finished.emit([], self.action_type)
            else:
                self.error.emit(fix_mojibake(res.get("log_saida", "Erro desconhecido na coleta WMI/WinRM.")))
        except Exception as e:
            self.error.emit(fix_mojibake(str(e)))


class SystemManagerView(BaseView):
    def __init__(self, main_window_ref=None, exec_repo: ExecutionRepository = None):
        super().__init__(main_window_ref)
        self.exec_repo = exec_repo or ExecutionRepository()
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

        summary_header = QHBoxLayout()
        summary_header.setContentsMargins(0, 0, 0, 0)
        summary_header.setSpacing(12)

        lbl_summary_title = QLabel("🚨 Últimos 5 Eventos Críticos / Erros")
        lbl_summary_title.setStyleSheet("font-weight: bold; color: #4a90e2; font-size: 13px;")
        summary_header.addWidget(lbl_summary_title)

        summary_header.addStretch()

        self.lbl_summary_status = QLabel("Não carregado.")
        self.lbl_summary_status.setStyleSheet("color: #888; font-style: italic; font-size: 12px;")
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
        self.tbl_summary.setFixedHeight(90)
        ev_layout.addWidget(self.tbl_summary)

        ev_layout.addSpacing(15)

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
        search_text = text.lower().strip()
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

    def _reset_buttons(self):
        self.btn_load_proc.setEnabled(True)
        self.btn_load_proc.setText("↻ Listar Processos")

        self.btn_load_svc.setEnabled(True)
        self.btn_load_svc.setText("↻ Listar Serviços")

        self.btn_load_events.setEnabled(True)
        self.btn_load_events.setText("🔍 Buscar Eventos")

        self.btn_refresh_summary.setEnabled(True)
        self.btn_refresh_summary.setText("↻ Atualizar Resumo")

    def run_worker(self, action_type, extra_params=None):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        if action_type == "get_events":
            if not extra_params:
                extra_params = {}
            extra_params["log_name"] = self.cmb_ev_log.currentText()
            extra_params["level"] = self.cmb_ev_level.currentData()
            extra_params["max"] = self.cmb_ev_max.currentText()
            self.btn_load_events.setEnabled(False)
            self.btn_load_events.setText("Buscando...")
        elif action_type == "get_processes":
            self.btn_load_proc.setEnabled(False)
            self.btn_load_proc.setText("Aguarde...")
        elif action_type == "get_services":
            self.btn_load_svc.setEnabled(False)
            self.btn_load_svc.setText("Aguarde...")
        elif action_type == "get_critical_summary":
            self.btn_refresh_summary.setEnabled(False)
            self.btn_refresh_summary.setText("Carregando...")
            self.lbl_summary_status.setText("Consultando eventos recentes...")

        self.worker = SysManagerWorker(target, action_type, extra_params)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.error.connect(self._on_worker_error)
        self.worker.start()

    def _on_worker_error(self, err):
        self._reset_buttons()
        QMessageBox.critical(self, "Erro Remoto", fix_mojibake(str(err)))

    def kill_process(self):
        row = self.tbl_proc.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um processo na tabela.")
            return

        pid = self.tbl_proc.item(row, 0).text()
        name = self.tbl_proc.item(row, 1).text()

        reply = QMessageBox.question(
            self, "Confirmar",
            f"Deseja forçar o encerramento do processo {name} (PID: {pid})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

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
        self.run_worker("get_critical_summary")

    def _adjust_summary_height(self):
        rows = self.tbl_summary.rowCount()
        header_h = self.tbl_summary.horizontalHeader().height()
        row_h = (self.tbl_summary.rowHeight(0) or 30) if rows > 0 else 30
        visible_rows = max(rows, 1)
        total = header_h + (row_h * visible_rows) + 4
        self.tbl_summary.setFixedHeight(total)

    def populate_critical_summary(self, data_list):
        self.tbl_summary.setSortingEnabled(False)
        self.tbl_summary.setRowCount(0)

        if not data_list:
            self.lbl_summary_status.setText("✓ Nenhum evento crítico/erro recente.")
            self.lbl_summary_status.setStyleSheet("color: #4CAF50; font-style: italic; margin-right: 10px;")
            self._adjust_summary_height()
            return

        for e in data_list:
            if not isinstance(e, dict):
                continue
            r = self.tbl_summary.rowCount()
            self.tbl_summary.insertRow(r)

            item_data = QTableWidgetItem(fix_mojibake(str(e.get("Data", ""))))
            item_data.setData(Qt.ItemDataRole.UserRole, e)
            self.tbl_summary.setItem(r, 0, item_data)

            self.tbl_summary.setItem(r, 1, QTableWidgetItem(fix_mojibake(str(e.get("LogName", "")))))

            lvl_item = QTableWidgetItem(fix_mojibake(str(e.get("Nivel", ""))))
            lvl_txt = lvl_item.text().lower()
            if "critical" in lvl_txt or "crítico" in lvl_txt or "critico" in lvl_txt:
                lvl_item.setForeground(Qt.GlobalColor.red)
            elif "error" in lvl_txt or "erro" in lvl_txt:
                lvl_item.setForeground(Qt.GlobalColor.darkYellow)
            self.tbl_summary.setItem(r, 2, lvl_item)

            self.tbl_summary.setItem(r, 3, QTableWidgetItem(fix_mojibake(str(e.get("Fonte", "")))))
            self.tbl_summary.setItem(r, 4, QTableWidgetItem(fix_mojibake(str(e.get("Mensagem", "")))))

        self.tbl_summary.setSortingEnabled(True)
        self.lbl_summary_status.setText(f"{len(data_list)} evento(s) recente(s).")
        self.lbl_summary_status.setStyleSheet("color: #888; font-style: italic; margin-right: 10px;")

        self._adjust_summary_height()

    def on_tab_changed(self, index):
        if index == 2:
            if self.inp_target.text().strip() and self.tbl_summary.rowCount() == 0:
                self.load_critical_summary()

    def on_worker_finished(self, data_list, action_type):
        self._reset_buttons()
        executor = os.environ.get("USERNAME", "Desconhecido")
        target = self.inp_target.text().strip()

        if action_type == "get_critical_summary":
            self.populate_critical_summary(data_list)
            return

        if action_type in ["kill_process", "manage_service"]:
            log_dict = data_list[0] if (data_list and isinstance(data_list[0], dict)) else {}
            status_final = str(log_dict.get("StatusFinal", "SUCESSO"))
            mensagem = fix_mojibake(str(log_dict.get("Mensagem", "Ação concluída.")))

            script_name = "Encerrar Processo" if action_type == "kill_process" else "Gerenciar Serviço"
            modulo = "[Gerenciador] Processos" if action_type == "kill_process" else "[Gerenciador] Serviços"

            self.exec_repo.record_execution(
                target_pc=target,
                script_name=script_name,
                status=status_final,
                result_data=json.dumps(log_dict, ensure_ascii=False) if log_dict else mensagem,
                technician=executor,
                module=modulo
            )

            if "SUCESSO" in status_final.upper():
                QMessageBox.information(self, "Sucesso", mensagem)
            else:
                QMessageBox.warning(self, "Aviso da Ação", mensagem)

            if action_type == "kill_process":
                self.run_worker("get_processes")
            else:
                self.run_worker("get_services")
            return

        if len(data_list) > 0 and isinstance(data_list[0], dict) and "Erro" in data_list[0]:
            QMessageBox.warning(self, "Aviso do Sistema Alvo", fix_mojibake(str(data_list[0]["Erro"])))
            return

        if action_type == "get_processes":
            self.tbl_proc.setSortingEnabled(False)
            self.tbl_proc.setRowCount(0)

            for p in data_list:
                if not isinstance(p, dict):
                    continue
                r = self.tbl_proc.rowCount()
                self.tbl_proc.insertRow(r)

                item_id = QTableWidgetItem()
                item_id.setData(Qt.ItemDataRole.EditRole, safe_int(p.get("Id", 0)))
                self.tbl_proc.setItem(r, 0, item_id)

                self.tbl_proc.setItem(r, 1, QTableWidgetItem(fix_mojibake(str(p.get("ProcessName", "")))))

                item_mem = QTableWidgetItem()
                item_mem.setData(Qt.ItemDataRole.EditRole, safe_float(p.get("MemoryMB", 0.0)))
                self.tbl_proc.setItem(r, 2, item_mem)

                item_cpu = QTableWidgetItem()
                item_cpu.setData(Qt.ItemDataRole.EditRole, safe_float(p.get("CPU", 0.0)))
                self.tbl_proc.setItem(r, 3, item_cpu)

            self.tbl_proc.setSortingEnabled(True)
            self.filter_table(self.tbl_proc, self.inp_search_proc.text())

        elif action_type == "get_services":
            self.tbl_svc.setSortingEnabled(False)
            self.tbl_svc.setRowCount(0)

            for s in data_list:
                if not isinstance(s, dict):
                    continue
                r = self.tbl_svc.rowCount()
                self.tbl_svc.insertRow(r)

                self.tbl_svc.setItem(r, 0, QTableWidgetItem(fix_mojibake(str(s.get("Name", "")))))
                self.tbl_svc.setItem(r, 1, QTableWidgetItem(fix_mojibake(str(s.get("DisplayName", "")))))

                status_text, status_color = normalize_service_status(s.get("Status", ""))
                status_item = QTableWidgetItem(status_text)
                if status_color is not None:
                    status_item.setForeground(status_color)

                self.tbl_svc.setItem(r, 2, status_item)

            self.tbl_svc.setSortingEnabled(True)
            self.filter_table(self.tbl_svc, self.inp_search_svc.text())

        elif action_type == "get_events":
            self.tbl_events.setSortingEnabled(False)
            self.tbl_events.setRowCount(0)

            for e in data_list:
                if not isinstance(e, dict):
                    continue
                r = self.tbl_events.rowCount()
                self.tbl_events.insertRow(r)

                item_id = QTableWidgetItem()
                item_id.setData(Qt.ItemDataRole.EditRole, safe_int(e.get("ID", 0)))
                item_id.setData(Qt.ItemDataRole.UserRole, e)
                self.tbl_events.setItem(r, 0, item_id)

                self.tbl_events.setItem(r, 1, QTableWidgetItem(fix_mojibake(str(e.get("Data", "")))))

                lvl_item = QTableWidgetItem(fix_mojibake(str(e.get("Nivel", ""))))
                lvl_low = lvl_item.text().lower()
                if "error" in lvl_low or "erro" in lvl_low or "critical" in lvl_low or "crítico" in lvl_low:
                    lvl_item.setForeground(Qt.GlobalColor.red)
                elif "warning" in lvl_low or "aviso" in lvl_low:
                    lvl_item.setForeground(Qt.GlobalColor.darkYellow)

                self.tbl_events.setItem(r, 2, lvl_item)
                self.tbl_events.setItem(r, 3, QTableWidgetItem(fix_mojibake(str(e.get("Fonte", "")))))
                self.tbl_events.setItem(r, 4, QTableWidgetItem(fix_mojibake(str(e.get("Mensagem", "")))))

            self.tbl_events.setSortingEnabled(True)
            self.filter_table(self.tbl_events, self.inp_search_ev.text())

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()