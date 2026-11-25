import base64
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.credential_store import CredentialStore
from core.ps_loader import PsTemplateError, load_ps_template
from core.remote_connection import RemoteConnectionManager
from core.task_queue import TaskQueueManager
from gui.dialogs.dialogs import CredentialDialog
from gui.views.base_view import BaseView
from infrastructure.repositories.execution_repository import ExecutionRepository


def _format_last_use(dt_str: str) -> str:
    """Converte 'YYYY-MM-DD HH:MM' em texto relativo amigável."""
    if not dt_str or dt_str == "N/A":
        return "N/A"
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return dt_str

    delta = datetime.now() - dt
    if delta.days == 0:
        return f"Hoje {dt.strftime('%H:%M')}"
    if delta.days == 1:
        return f"Ontem {dt.strftime('%H:%M')}"
    if 0 < delta.days < 7:
        return f"{delta.days} dias atrás"
    return dt.strftime("%d/%m/%Y")


def _is_temp_profile(profile_dict: dict) -> bool:
    """Identifica se o perfil é temporário (TEMP / TEMP.*)."""
    if not isinstance(profile_dict, dict):
        return False
    if profile_dict.get("IsTemp") is True:
        return True
    name = str(profile_dict.get("Name", "")).strip().upper()
    return name == "TEMP" or name.startswith("TEMP.")


def format_profile_session_status(profile_dict: dict, logged_names: set = None) -> tuple[str, Qt.GlobalColor | None, bool]:
    """
    Retorna (texto_status, cor_qt, pode_fazer_logoff) diferenciando:
    - Ativo (sessão ativa no console/RDP)
    - Desconectado (sessão aberta em 2º plano consumindo recursos)
    - Em 2º Plano (hive carregada)
    - Temp / Órfão
    - Inativo
    """
    logged_names = logged_names or set()
    name = str(profile_dict.get("Name", "?"))
    state = str(profile_dict.get("SessionState", "") or "").strip()
    sess_id = profile_dict.get("SessionId")
    is_temp = _is_temp_profile(profile_dict)
    is_loaded = bool(profile_dict.get("Loaded")) or (name in logged_names)

    id_suffix = f" (ID {sess_id})" if sess_id is not None and str(sess_id).isdigit() else ""

    if state.lower() == "ativo":
        return f"🟢 Ativo{id_suffix}", Qt.GlobalColor.green, True
    if state.lower() == "desconectado":
        return f"🟡 Desconectado{id_suffix}", Qt.GlobalColor.yellow, True
    if state.lower() == "carregado":
        return "🔵 Em 2º Plano", Qt.GlobalColor.cyan, True
    if is_loaded and not state:
        return f"🟢 Logado{id_suffix}", Qt.GlobalColor.green, True
    if is_temp:
        return "🟠 Temp / Órfão", Qt.GlobalColor.yellow, False
    return "⚪ Inativo", None, False


def _sort_profiles(profiles: list, logged_names: set) -> list:
    """Ordena: 1º Ativos, 2º Desconectados/2º Plano, 3º Normais por data, 4º Perfis TEMP*."""
    def sort_key(p):
        name = p.get("Name", "")
        state = str(p.get("SessionState", "") or "").lower()
        if state == "ativo":
            rank_session = 3
        elif state in ("desconectado", "carregado") or name in logged_names or p.get("Loaded"):
            rank_session = 2
        else:
            rank_session = 0

        is_normal = 0 if _is_temp_profile(p) else 1
        last_use = p.get("LastUse", "") or ""
        if last_use == "N/A":
            last_use = ""
        return (rank_session, is_normal, last_use)

    return sorted(profiles, key=sort_key, reverse=True)


def format_smart_badge(disk_type: str, smart_status: str) -> str:
    """Formata o tipo de disco e o status S.M.A.R.T. com destaque colorido em HTML."""
    dtype = str(disk_type or "Disco").strip()
    smart = str(smart_status or "N/A").strip()
    low = smart.lower()
    if "saudável" in low or "saudavel" in low or "ok" in low:
        color = "#4CAF50"
    elif "alerta" in low or "warning" in low:
        color = "#f0ad4e"
    elif "crítico" in low or "critico" in low or "unhealthy" in low:
        color = "#f44336"
    else:
        color = "#888888"
    return f"[{dtype}] S.M.A.R.T.: <span style='color: {color}; font-weight: bold;'>{smart}</span>"


def _activate_header_click_sort(table: QTableWidget, col: int):
    """Ativa ordenação sob demanda quando o usuário clica manualmente no cabeçalho."""
    if not table.isSortingEnabled():
        table.horizontalHeader().setSortIndicatorShown(True)
        table.setSortingEnabled(True)
        table.sortItems(col, Qt.SortOrder.AscendingOrder)


class ProfilesDialog(QDialog):
    """Lista completa de perfis de utilizador (Normais + Temporários + Sessões em 2º plano) do endpoint alvo."""

    def __init__(self, profiles: list, logged_names: set, target_pc: str, on_logoff_callback=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Perfis e Sessões de Usuário — {target_pc}")
        self.resize(700, 520)
        self.all_profiles = profiles
        self.logged_names = logged_names
        self.target_pc = target_pc
        self.on_logoff_callback = on_logoff_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        temp_count = sum(1 for p in profiles if _is_temp_profile(p))
        normal_count = len(profiles) - temp_count
        active_count = sum(1 for p in profiles if str(p.get("SessionState", "")).lower() == "ativo")
        disc_count = sum(
            1 for p in profiles
            if str(p.get("SessionState", "")).lower() in ("desconectado", "carregado")
        )

        header_layout = QHBoxLayout()
        info = QLabel(
            f"<b>Total: {len(profiles)}</b> &nbsp;|&nbsp; "
            f"Normais: <b>{normal_count}</b> &nbsp;|&nbsp; "
            f"<span style='color: #f0ad4e;'>TEMP*: <b>{temp_count}</b></span> &nbsp;|&nbsp; "
            f"<span style='color: #4CAF50;'>Ativos: <b>{active_count}</b></span> &nbsp;|&nbsp; "
            f"<span style='color: #ffd700;'>Desconectados (2º Plano): <b>{disc_count}</b></span>"
        )
        info.setStyleSheet("font-size: 13px;")
        header_layout.addWidget(info)
        header_layout.addStretch()

        self.chk_hide_temp = QCheckBox("Ocultar pastas TEMP*")
        self.chk_hide_temp.setStyleSheet("font-weight: bold; color: #5bc0de;")
        self.chk_hide_temp.stateChanged.connect(self._apply_filter)
        header_layout.addWidget(self.chk_hide_temp)
        layout.addLayout(header_layout)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Usuário / Pasta", "Último Acesso", "Status da Sessão"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().resizeSection(0, 260)
        self.table.horizontalHeader().resizeSection(1, 160)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.table.horizontalHeader().sectionClicked.connect(
            lambda col: _activate_header_click_sort(self.table, col)
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)

        self._populate()
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_logoff_sel = QPushButton("🚪 Fazer Logoff do Usuário Selecionado")
        self.btn_logoff_sel.setFixedHeight(32)
        self.btn_logoff_sel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logoff_sel.setStyleSheet(
            "padding: 0 16px; background-color: #f0ad4e; color: black; "
            "font-weight: bold; border-radius: 4px;"
        )
        self.btn_logoff_sel.clicked.connect(self._logoff_selected)
        btn_layout.addWidget(self.btn_logoff_sel)

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

    def _populate(self):
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setSortIndicatorShown(False)
        self.table.setRowCount(0)

        profiles_sorted = _sort_profiles(self.all_profiles, self.logged_names)

        for p in profiles_sorted:
            row = self.table.rowCount()
            self.table.insertRow(row)

            name = p.get("Name", "?")

            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, p)
            self.table.setItem(row, 0, name_item)

            last_use_item = QTableWidgetItem(_format_last_use(p.get("LastUse", "N/A")))
            last_use_item.setData(Qt.ItemDataRole.UserRole, p.get("LastUse", ""))
            self.table.setItem(row, 1, last_use_item)

            status_text, color, _ = format_profile_session_status(p, self.logged_names)
            status_item = QTableWidgetItem(status_text)
            if color is not None:
                status_item.setForeground(color)
            self.table.setItem(row, 2, status_item)

    def _apply_filter(self):
        hide_temp = self.chk_hide_temp.isChecked()
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            p_data = item.data(Qt.ItemDataRole.UserRole) if item else {}
            is_temp = _is_temp_profile(p_data)
            self.table.setRowHidden(r, hide_temp and is_temp)

    def _logoff_selected(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um usuário na tabela.")
            return
        item = self.table.item(row, 0)
        p_data = item.data(Qt.ItemDataRole.UserRole) if item else {}
        _, _, can_logoff = format_profile_session_status(p_data, self.logged_names)
        if not can_logoff:
            QMessageBox.information(
                self, "Sessão Inativa",
                f"O perfil '{p_data.get('Name', '')}' não está com sessão aberta no momento."
            )
            return
        if self.on_logoff_callback:
            self.on_logoff_callback(p_data.get("Name", ""), p_data.get("SessionId"))
            self.close()

    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        name_item = self.table.item(row, 0)
        p_data = name_item.data(Qt.ItemDataRole.UserRole) if name_item else {}
        username = p_data.get("Name", "")
        _, _, can_logoff = format_profile_session_status(p_data, self.logged_names)

        menu = QMenu(self)
        act_copy = menu.addAction(f"📋 Copiar usuário '{username}'")
        act_logoff = None
        if can_logoff:
            act_logoff = menu.addAction(f"🚪 Fazer Logoff apenas de '{username}'")

        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == act_copy:
            QApplication.clipboard().setText(username)
        elif act_logoff and chosen == act_logoff and self.on_logoff_callback:
            self.on_logoff_callback(username, p_data.get("SessionId"))
            self.close()


class PingTrackerWorker(QThread):
    success = pyqtSignal(str)
    timeout = pyqtSignal(str)

    def __init__(self, target_pc):
        super().__init__()
        self.target_pc = target_pc

    def run(self):
        for _ in range(60):
            res = subprocess.run(
                f"ping -n 1 -w 1000 {self.target_pc}",
                capture_output=True, text=True, shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if "TTL=" in res.stdout:
                self.success.emit(self.target_pc)
                return
            time.sleep(5)
        self.timeout.emit(self.target_pc)


class TelemetryWorker(QThread):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, target_pc):
        super().__init__()
        self.target_pc = target_pc
        self.is_cancelled = False

    def run(self):
        try:
            try:
                ps_script = load_ps_template("dashboard", "telemetry")
            except PsTemplateError as e:
                if not self.is_cancelled:
                    self.error.emit(f"Erro de configuração interna: {e}")
                return

            conn = RemoteConnectionManager()
            res = conn.execute_script(self.target_pc, ps_script)

            if self.is_cancelled:
                return

            if res["status"] == "Sucesso" and res.get("json_data"):
                self.finished.emit(res["json_data"])
            elif "WMI Assíncrono" in res["status"]:
                self.error.emit("A máquina alvo bloqueou o WinRM. O comando WMI disparou em 2º plano.")
            else:
                self.error.emit(res.get("log_saida", "Erro crítico na coleta."))
        except Exception as e:
            if not self.is_cancelled:
                self.error.emit(str(e))


class DashboardView(BaseView):
    NETWORK_SOFTWARE_SHARE = r"\\hul-vp-imagem-cc\netshared\Softwares"

    def __init__(self, main_window_ref=None, exec_repo: ExecutionRepository = None):
        super().__init__(main_window_ref)
        self.queue_manager = getattr(main_window_ref, "queue_manager", None) or TaskQueueManager(max_threads=5)
        self.exec_repo = exec_repo or ExecutionRepository()
        self.is_fetching = False
        self._last_anydesk_id = ""
        self._last_computer_desc = ""
        self._setup_ui()

    @staticmethod
    def _b64(text: str) -> str:
        return base64.b64encode(str(text or "").encode("utf-8")).decode("ascii")

    def _get_credentials(self):
        """Retorna credenciais — cache → disco (DPAPI) → popup."""
        cached = getattr(self.main_window, "get_cached_credentials", None)
        if cached:
            creds = cached()
            if creds:
                return creds

        saved = CredentialStore.load()
        if saved:
            setter = getattr(self.main_window, "set_cached_credentials", None)
            if setter:
                setter(saved["user"], saved["pass"])
            return saved

        dominio = os.environ.get("USERDOMAIN", "")
        usuario = os.environ.get("USERNAME", "")
        user_str = f"{dominio}\\{usuario}" if dominio else usuario

        dlg = CredentialDialog(user_display=user_str, has_saved=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None

        senha = dlg.password
        if not senha:
            return None

        if dlg.remember:
            CredentialStore.save(user_str, senha)

        setter = getattr(self.main_window, "set_cached_credentials", None)
        if setter:
            setter(user_str, senha)

        return {"user": user_str, "pass": senha, "vnc_pass": senha}

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        title = QLabel("Dashboard & Diagnóstico Operacional")
        title.setStyleSheet("font-size: 24px; font-weight: bold; color: #4a90e2;")
        main_layout.addWidget(title)

        target_group = QGroupBox("Computador Alvo (Telemetria)")
        target_layout = QHBoxLayout(target_group)
        target_layout.setContentsMargins(15, 20, 15, 15)

        self.inp_target = QLineEdit()
        self.inp_target.setFixedHeight(32)
        self.inp_target.setPlaceholderText("Ex: HUL-WK-001122E ou 192.168.0.2")
        self.inp_target.setStyleSheet("padding: 0 10px;")
        self.inp_target.textChanged.connect(self._force_uppercase)

        self.btn_fetch = QPushButton("🔄 Carregar Telemetria")
        self.btn_fetch.setFixedHeight(32)
        self.btn_fetch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fetch.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")
        self.btn_fetch.clicked.connect(self.fetch_telemetry)

        self.lbl_last_sync = QLabel(" Última atualização: -")
        self.lbl_last_sync.setStyleSheet("color: #888; font-style: italic; font-weight: bold;")

        target_layout.addWidget(QLabel("Alvo:"))
        target_layout.addWidget(self.inp_target)
        target_layout.addWidget(self.btn_fetch)
        target_layout.addWidget(self.lbl_last_sync)
        main_layout.addWidget(target_group)

        action_group = QGroupBox("⚡ Ações Rápidas, Acesso Remoto & Reparo de Agentes")
        action_layout = QHBoxLayout(action_group)
        action_layout.setContentsMargins(15, 20, 15, 15)
        action_layout.setSpacing(8)

        self.cmb_remote = QComboBox()
        self.cmb_remote.setFixedHeight(32)
        self.cmb_remote.addItems(["RDP (Windows)", "VNC Viewer", "AnyDesk", "Assistência Rápida"])
        self.cmb_remote.setStyleSheet("padding: 0 10px; font-weight: bold;")

        self.btn_connect = QPushButton("▶ Conectar")
        self.btn_connect.setFixedHeight(32)
        self.btn_connect.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_connect.setStyleSheet("background-color: #0275d8; color: white; font-weight: bold; padding: 0 12px; border-radius: 4px;")
        self.btn_connect.clicked.connect(self.action_connect)

        self.cmb_agent_repair = QComboBox()
        self.cmb_agent_repair.setFixedHeight(32)
        self.cmb_agent_repair.addItem("🛠️ Agente: Zabbix Agent 2", "zabbix")
        self.cmb_agent_repair.addItem("🛠️ Agente: UltraVNC Server", "uvnc")
        self.cmb_agent_repair.addItem("🛠️ Agente: GLPI (+ Forçar Sync)", "glpi")
        self.cmb_agent_repair.addItem("🛠️ Agente: Desktop Info", "desktopinfo")
        self.cmb_agent_repair.addItem("🛠️ Reparar Todos (Zabbix+VNC+GLPI+Info)", "all")
        self.cmb_agent_repair.setStyleSheet("padding: 0 10px; font-weight: bold;")

        self.btn_repair_agent = QPushButton("🔧 Reparar/Instalar")
        self.btn_repair_agent.setFixedHeight(32)
        self.btn_repair_agent.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_repair_agent.setStyleSheet("background-color: #1e8a5e; color: white; font-weight: bold; padding: 0 12px; border-radius: 4px;")
        self.btn_repair_agent.clicked.connect(self.action_repair_agent)

        self.btn_wol = QPushButton("📡 WoL")
        self.btn_wol.setFixedHeight(32)
        self.btn_wol.setToolTip("Enviar pacote mágico Wake-on-LAN")
        self.btn_wol.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_wol.setStyleSheet("background-color: #5cb85c; color: white; font-weight: bold; padding: 0 12px; border-radius: 4px;")
        self.btn_wol.clicked.connect(self.action_wol)

        self.btn_logoff = QPushButton("👤 Logoff")
        self.btn_logoff.setFixedHeight(32)
        self.btn_logoff.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logoff.setStyleSheet("background-color: #f0ad4e; color: white; font-weight: bold; padding: 0 12px; border-radius: 4px;")
        self.btn_logoff.clicked.connect(lambda: self.action_power("logoff"))

        self.btn_restart = QPushButton("🔄 Reiniciar")
        self.btn_restart.setFixedHeight(32)
        self.btn_restart.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_restart.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 0 12px; border-radius: 4px;")
        self.btn_restart.clicked.connect(lambda: self.action_power("restart"))

        self.btn_shutdown = QPushButton("🔌 Desligar")
        self.btn_shutdown.setFixedHeight(32)
        self.btn_shutdown.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_shutdown.setStyleSheet("background-color: #292b2c; color: white; font-weight: bold; padding: 0 12px; border-radius: 4px;")
        self.btn_shutdown.clicked.connect(lambda: self.action_power("shutdown"))

        action_layout.addWidget(self.cmb_remote)
        action_layout.addWidget(self.btn_connect)
        action_layout.addSpacing(6)
        action_layout.addWidget(self.cmb_agent_repair)
        action_layout.addWidget(self.btn_repair_agent)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_wol)
        action_layout.addWidget(self.btn_logoff)
        action_layout.addWidget(self.btn_restart)
        action_layout.addWidget(self.btn_shutdown)

        main_layout.addWidget(action_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")

        container = QWidget()
        content_layout = QVBoxLayout(container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(15)

        grid_cards = QGridLayout()
        grid_cards.setSpacing(15)
        grid_cards.setColumnStretch(0, 1)
        grid_cards.setColumnStretch(1, 1)

        self.card_sys = QGroupBox("🌐 Informações do Sistema & Inventário Físico")
        sys_layout = QVBoxLayout(self.card_sys)
        sys_layout.setContentsMargins(15, 20, 15, 15)

        sys_grid = QGridLayout()
        sys_grid.setSpacing(8)

        self.lbl_hostname = QLabel("Hostname: -")

        desc_row = QWidget()
        desc_row_layout = QHBoxLayout(desc_row)
        desc_row_layout.setContentsMargins(0, 0, 0, 0)
        desc_row_layout.setSpacing(6)
        self.lbl_desc = QLabel("Descrição (Local): -")
        self.btn_edit_desc = QPushButton("✏️")
        self.btn_edit_desc.setFixedSize(24, 22)
        self.btn_edit_desc.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_edit_desc.setToolTip("Editar remotamente a Descrição (Local / Setor) deste computador")
        self.btn_edit_desc.setStyleSheet(
            "background-color: #2b3a4a; color: #5bc0de; border: 1px solid #4a90e2; "
            "border-radius: 3px; font-size: 11px; padding: 0;"
        )
        self.btn_edit_desc.clicked.connect(self.action_edit_description)
        desc_row_layout.addWidget(self.lbl_desc)
        desc_row_layout.addWidget(self.btn_edit_desc)
        desc_row_layout.addStretch()

        self.lbl_hw_model = QLabel("Equipamento: -")
        self.lbl_serial = QLabel("Serial / BIOS: -")
        self.lbl_os = QLabel("SO: -")
        self.lbl_uptime = QLabel("Uptime: -")
        self.lbl_ip = QLabel("IP: -")
        self.lbl_mac = QLabel("MAC: -")
        self.lbl_av = QLabel("Antivírus: -")

        self.lbl_rdp = QLabel("RDP: -")
        self.lbl_vnc = QLabel("VNC: -")
        self.lbl_anydesk = QLabel("AnyDesk ID: -")
        self.lbl_wol = QLabel("WoL (OS): -")
        self.lbl_zabbix = QLabel("Zabbix: -")
        self.lbl_glpi = QLabel("GLPI: -")
        self.lbl_desktopinfo = QLabel("Desktop Info: -")
        self.lbl_winget = QLabel("Winget: -")
        self.lbl_reboot = QLabel("Reboot: -")

        for lbl in [
            self.lbl_hostname, self.lbl_desc, self.lbl_hw_model, self.lbl_serial,
            self.lbl_os, self.lbl_uptime, self.lbl_ip, self.lbl_mac,
            self.lbl_av, self.lbl_rdp, self.lbl_vnc, self.lbl_anydesk, self.lbl_wol,
            self.lbl_zabbix, self.lbl_glpi, self.lbl_desktopinfo, self.lbl_winget, self.lbl_reboot
        ]:
            lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        sys_grid.addWidget(self.lbl_hostname, 0, 0)
        sys_grid.addWidget(desc_row, 1, 0)
        sys_grid.addWidget(self.lbl_hw_model, 2, 0)
        sys_grid.addWidget(self.lbl_serial, 3, 0)
        sys_grid.addWidget(self.lbl_os, 4, 0)
        sys_grid.addWidget(self.lbl_uptime, 5, 0)
        sys_grid.addWidget(self.lbl_ip, 6, 0)
        sys_grid.addWidget(self.lbl_mac, 7, 0)
        sys_grid.addWidget(self.lbl_av, 8, 0)

        sys_grid.addWidget(self.lbl_rdp, 0, 1)
        sys_grid.addWidget(self.lbl_vnc, 1, 1)
        sys_grid.addWidget(self.lbl_anydesk, 2, 1)
        sys_grid.addWidget(self.lbl_wol, 3, 1)
        sys_grid.addWidget(self.lbl_zabbix, 4, 1)
        sys_grid.addWidget(self.lbl_glpi, 5, 1)
        sys_grid.addWidget(self.lbl_desktopinfo, 6, 1)
        sys_grid.addWidget(self.lbl_winget, 7, 1)
        sys_grid.addWidget(self.lbl_reboot, 8, 1)

        sys_layout.addLayout(sys_grid)
        grid_cards.addWidget(self.card_sys, 0, 0)

        self.card_profiles = QGroupBox("👥 Sessões e Perfis de Usuários")
        p_layout = QVBoxLayout(self.card_profiles)
        p_layout.setContentsMargins(15, 20, 15, 15)
        p_layout.setSpacing(10)

        counters = QHBoxLayout()
        counters.setSpacing(20)

        v_prof = QVBoxLayout()
        self.lbl_profiles_count = QLabel("-")
        self.lbl_profiles_count.setStyleSheet("font-size: 22px; font-weight: bold; color: #2a7de1;")
        self.lbl_profiles_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_prof.addWidget(self.lbl_profiles_count)
        v_prof.addWidget(QLabel("Perfis na Máquina", alignment=Qt.AlignmentFlag.AlignCenter))

        v_log = QVBoxLayout()
        self.lbl_logged_count = QLabel("-")
        self.lbl_logged_count.setStyleSheet("font-size: 22px; font-weight: bold; color: #f0ad4e;")
        self.lbl_logged_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v_log.addWidget(self.lbl_logged_count)
        v_log.addWidget(QLabel("Sessões Abertas (Ativas / 2º Plano)", alignment=Qt.AlignmentFlag.AlignCenter))

        counters.addLayout(v_prof)
        counters.addLayout(v_log)
        p_layout.addLayout(counters)

        self.tbl_profiles = QTableWidget(0, 3)
        self.tbl_profiles.setHorizontalHeaderLabels(["Usuário", "Último Acesso", "Status da Sessão"])
        self.tbl_profiles.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.tbl_profiles.horizontalHeader().resizeSection(0, 175)
        self.tbl_profiles.horizontalHeader().resizeSection(1, 130)
        self.tbl_profiles.horizontalHeader().setStretchLastSection(True)
        self.tbl_profiles.horizontalHeader().setSortIndicatorShown(False)
        self.tbl_profiles.horizontalHeader().sectionClicked.connect(
            lambda col: _activate_header_click_sort(self.tbl_profiles, col)
        )
        self.tbl_profiles.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_profiles.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_profiles.verticalHeader().setVisible(False)
        self.tbl_profiles.setShowGrid(False)
        self.tbl_profiles.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl_profiles.customContextMenuRequested.connect(self._on_profiles_table_context_menu)
        header_h = self.tbl_profiles.horizontalHeader().height()
        row_h = 24
        self.tbl_profiles.setFixedHeight(header_h + (row_h * 5) + 6)
        p_layout.addWidget(self.tbl_profiles)

        prof_footer = QHBoxLayout()
        self.btn_logoff_selected_user = QPushButton("🚪 Logoff Selecionado")
        self.btn_logoff_selected_user.setFixedHeight(26)
        self.btn_logoff_selected_user.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_logoff_selected_user.setToolTip(
            "Encerra apenas a sessão do usuário selecionado na tabela (útil para fechar sessões desconectadas em 2º plano)"
        )
        self.btn_logoff_selected_user.setStyleSheet(
            "padding: 0 10px; font-size: 12px; font-weight: bold; background-color: #f0ad4e; color: black; border-radius: 4px;"
        )
        self.btn_logoff_selected_user.clicked.connect(self.action_logoff_selected_table_user)
        prof_footer.addWidget(self.btn_logoff_selected_user)

        prof_footer.addStretch()

        self.btn_view_all_profiles = QPushButton("Ver todos")
        self.btn_view_all_profiles.setFixedHeight(26)
        self.btn_view_all_profiles.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_view_all_profiles.setStyleSheet(
            "padding: 0 12px; font-size: 12px; font-weight: bold; border-radius: 4px;"
        )
        self.btn_view_all_profiles.setVisible(False)
        self.btn_view_all_profiles.clicked.connect(self._open_profiles_dialog)
        prof_footer.addWidget(self.btn_view_all_profiles)

        p_layout.addLayout(prof_footer)
        grid_cards.addWidget(self.card_profiles, 0, 1)

        content_layout.addLayout(grid_cards)

        bottom_panels = QHBoxLayout()
        bottom_panels.setSpacing(15)

        self.card_resources = QGroupBox("⚙️ Recursos Físicos (Disco S.M.A.R.T., CPU, Topologia RAM)")
        res_layout = QVBoxLayout(self.card_resources)
        res_layout.setContentsMargins(15, 20, 15, 15)

        disk_header = QHBoxLayout()
        self.lbl_storage_info = QLabel("Disco C:: Aguardando leitura...")
        self.lbl_disk_smart = QLabel("S.M.A.R.T.: -")
        disk_header.addWidget(self.lbl_storage_info)
        disk_header.addStretch()
        disk_header.addWidget(self.lbl_disk_smart)

        self.prog_storage = QProgressBar()
        self.prog_storage.setValue(0)
        self.prog_storage.setStyleSheet(self._get_bar_style(0))

        self.lbl_cpu_info = QLabel("CPU: Aguardando leitura...")
        self.prog_cpu = QProgressBar()
        self.prog_cpu.setValue(0)
        self.prog_cpu.setStyleSheet(self._get_bar_style(0))

        self.lbl_temp_info = QLabel("Temperatura CPU: Aguardando leitura...")
        self.prog_temp = QProgressBar()
        self.prog_temp.setValue(0)
        self.prog_temp.setStyleSheet(self._get_bar_style(0, is_temp=True))

        ram_header = QHBoxLayout()
        self.lbl_ram_info = QLabel("RAM: Aguardando leitura...")
        self.lbl_ram_slots = QLabel("Slots: -")
        self.lbl_ram_slots.setStyleSheet("color: #5bc0de; font-weight: bold;")
        ram_header.addWidget(self.lbl_ram_info)
        ram_header.addStretch()
        ram_header.addWidget(self.lbl_ram_slots)

        self.prog_ram = QProgressBar()
        self.prog_ram.setValue(0)
        self.prog_ram.setStyleSheet(self._get_bar_style(0))

        res_layout.addLayout(disk_header)
        res_layout.addWidget(self.prog_storage)
        res_layout.addSpacing(10)

        cpu_horiz = QHBoxLayout()
        cpu_horiz.setSpacing(15)

        v_cpu = QVBoxLayout()
        v_cpu.setSpacing(5)
        v_cpu.addWidget(self.lbl_cpu_info)
        v_cpu.addWidget(self.prog_cpu)

        v_temp = QVBoxLayout()
        v_temp.setSpacing(5)
        v_temp.addWidget(self.lbl_temp_info)
        v_temp.addWidget(self.prog_temp)

        cpu_horiz.addLayout(v_cpu, stretch=1)
        cpu_horiz.addLayout(v_temp, stretch=1)
        res_layout.addLayout(cpu_horiz)

        res_layout.addSpacing(10)
        res_layout.addLayout(ram_header)
        res_layout.addWidget(self.prog_ram)

        bottom_panels.addWidget(self.card_resources, stretch=65)

        lic_group = QGroupBox("🔑 Licenciamento (KMS)")
        lic_layout = QVBoxLayout(lic_group)
        lic_layout.setContentsMargins(12, 18, 12, 10)
        lic_layout.setSpacing(8)

        self.lbl_activation = QLabel("Status: -")
        self.lbl_activation.setStyleSheet("font-weight: bold;")
        lic_layout.addWidget(self.lbl_activation)

        self.cmb_license = QComboBox()
        self.cmb_license.setFixedHeight(28)
        self.cmb_license.addItem("Windows 10/11 Pro",             "W269N-WFGWX-YVC9B-4J6C9-T83GX")
        self.cmb_license.addItem("Windows 10/11 Enterprise",      "NPPR9-FWDCX-D2C8J-H872K-2YT43")
        self.cmb_license.addItem("Windows 10/11 Education",       "NW6C2-QMPVW-D7KKK-3GKT6-VCFB2")
        self.cmb_license.addItem("Windows 10/11 Pro Education",   "6TP4R-GNPTD-KYYHQ-7B7DP-J447Y")
        self.cmb_license.addItem("Windows 10/11 Enterprise LTSC", "M7XTQ-FN8P6-TTKYV-9D4CC-J462D")
        self.cmb_license.setStyleSheet("padding: 0 8px;")
        lic_layout.addWidget(self.cmb_license)

        self.btn_apply_key = QPushButton("⚙️ Aplicar Chave")
        self.btn_apply_key.setFixedHeight(28)
        self.btn_apply_key.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apply_key.setStyleSheet(
            "background-color: #f0ad4e; color: black; padding: 0 12px; "
            "font-weight: bold; border-radius: 4px; font-size: 12px;"
        )
        self.btn_apply_key.clicked.connect(self.change_windows_key)
        lic_layout.addWidget(self.btn_apply_key)

        lic_layout.addStretch()

        bottom_panels.addWidget(lic_group, stretch=35)
        content_layout.addLayout(bottom_panels)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    def _get_bar_style(self, val, is_temp=False, disabled=False):
        if disabled:
            color = "#666666"
        elif is_temp:
            if val >= 85:
                color = "#d9534f"
            elif val >= 70:
                color = "#f0ad4e"
            else:
                color = "#1e8a5e"
        else:
            if val >= 90:
                color = "#d9534f"
            elif val >= 75:
                color = "#f0ad4e"
            else:
                color = "#1e8a5e"

        return f"QProgressBar {{ border: 1px solid #444; color: white; font-weight: bold; border-radius: 4px; text-align: center; height: 16px; }} QProgressBar::chunk {{ background-color: {color}; }}"

    def showEvent(self, event):
        super().showEvent(event)
        self.inp_target.setFocus()

    def action_edit_description(self):
        """Edita remotamente a Descrição do Computador (Local / Setor) no Windows."""
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo antes de editar a descrição.")
            self.inp_target.setFocus()
            return

        current_desc = "" if self._last_computer_desc in ("-", "Sem descrição") else self._last_computer_desc
        new_desc, ok = QInputDialog.getText(
            self,
            f"Editar Descrição (Local / Setor) — {target}",
            "Informe o Setor / Local / Modelo para gravar na descrição da máquina:",
            QLineEdit.EchoMode.Normal,
            current_desc
        )
        if not ok:
            return

        new_desc = new_desc.strip()
        try:
            ps_script = load_ps_template("dashboard", "set_description", desc_b64=self._b64(new_desc))
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro Interno", f"Template ausente:\n{e}")
            return

        self.btn_edit_desc.setEnabled(False)
        self.queue_manager.add_task(
            target_pc=target,
            script_name=f"Alterar Descrição ({new_desc or 'Vazio'})",
            script_content=ps_script,
            module_name="[Dashboard] Inventário",
            on_finish=lambda t, s, d: self._on_desc_updated(t, new_desc, d),
            on_error=lambda t, e: self._on_desc_error(t, e)
        )

    def _on_desc_updated(self, target_pc, new_desc, json_data):
        self.btn_edit_desc.setEnabled(True)
        self._last_computer_desc = new_desc or "Sem descrição"
        self.lbl_desc.setText(
            f"Descrição (Local): <span style='color: #5bc0de; font-weight: bold;'>{self._last_computer_desc}</span>"
        )
        msg = json_data.get("Mensagem", "Descrição atualizada.") if isinstance(json_data, dict) else "Descrição atualizada."
        QMessageBox.information(self, "Descrição Atualizada", f"[{target_pc}] {msg}")

    def _on_desc_error(self, target_pc, error_msg):
        self.btn_edit_desc.setEnabled(True)
        QMessageBox.critical(self, "Erro ao Alterar Descrição", f"Não foi possível alterar a descrição em {target_pc}:\n\n{error_msg}")

    def action_logoff_selected_table_user(self):
        """Faz logoff apenas do usuário selecionado na tabela do Dashboard."""
        row = self.tbl_profiles.currentRow()
        if row < 0:
            QMessageBox.warning(self, "Aviso", "Selecione um usuário na tabela de sessões.")
            return
        item = self.tbl_profiles.item(row, 0)
        p_data = item.data(Qt.ItemDataRole.UserRole) if item else {}
        username = p_data.get("Name", "")
        _, _, can_logoff = format_profile_session_status(p_data, getattr(self, "_last_logged_names", set()))
        if not can_logoff:
            QMessageBox.information(
                self, "Sessão Inativa",
                f"O perfil '{username}' está inativo e não possui sessão aberta para encerrar."
            )
            return
        self.action_logoff_specific_user(username, p_data.get("SessionId"))

    def _on_profiles_table_context_menu(self, pos):
        item = self.tbl_profiles.itemAt(pos)
        if not item:
            return
        row = item.row()
        name_item = self.tbl_profiles.item(row, 0)
        p_data = name_item.data(Qt.ItemDataRole.UserRole) if name_item else {}
        username = p_data.get("Name", "")
        _, _, can_logoff = format_profile_session_status(p_data, getattr(self, "_last_logged_names", set()))

        menu = QMenu(self)
        act_copy = menu.addAction(f"📋 Copiar usuário '{username}'")
        act_logoff = None
        if can_logoff:
            act_logoff = menu.addAction(f"🚪 Fazer Logoff apenas de '{username}'")

        chosen = menu.exec(self.tbl_profiles.viewport().mapToGlobal(pos))
        if chosen == act_copy:
            QApplication.clipboard().setText(username)
        elif act_logoff and chosen == act_logoff:
            self.action_logoff_specific_user(username, p_data.get("SessionId"))

    def action_logoff_specific_user(self, username: str, session_id=None):
        """Executa o logoff seletivo de um único usuário na máquina alvo."""
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            return

        id_str = str(session_id) if session_id is not None else ""
        reply = QMessageBox.question(
            self,
            "Confirmar Logoff Seletivo",
            f"Deseja encerrar apenas a sessão do usuário '{username}' "
            f"{f'(ID {id_str}) ' if id_str else ''}em {target}?\n\n"
            "• Outros usuários logados não serão afetados.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ps_script = load_ps_template(
                "dashboard", "logoff_session",
                username_b64=self._b64(username),
                session_id_b64=self._b64(id_str)
            )
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro Interno", f"Template ausente:\n{e}")
            return

        self.queue_manager.add_task(
            target_pc=target,
            script_name=f"Logoff Seletivo ({username})",
            script_content=ps_script,
            module_name="[Dashboard] Sessões",
            on_finish=lambda t, s, d: self._on_selective_logoff_finished(t, username, d),
            on_error=lambda t, e: QMessageBox.critical(self, "Falha no Logoff", f"Erro ao desconectar '{username}' em {t}:\n{e}")
        )

    def _on_selective_logoff_finished(self, target_pc, username, json_data):
        msg = json_data.get("Mensagem", f"Sessão de '{username}' encerrada.") if isinstance(json_data, dict) else "Concluído."
        QMessageBox.information(self, "Logoff Concluído", f"[{target_pc}] {msg}")
        self.fetch_telemetry()

    def action_repair_agent(self):
        """Dispara o reparo ou instalação automatizada do(s) agente(s) selecionado(s)."""
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo antes de reparar um agente.")
            self.inp_target.setFocus()
            return

        agent_key = self.cmb_agent_repair.currentData()
        agent_label = self.cmb_agent_repair.currentText().replace("🛠️ ", "")

        reply = QMessageBox.question(
            self,
            "Confirmar Reparo / Deploy de Agente",
            f"Deseja executar o reparo/instalação de '{agent_label}' no computador {target}?\n\n"
            "• Se o serviço estiver parado, será reconfigurado e iniciado.\n"
            "• Se não estiver instalado, o SARCC fará o deploy silencioso a partir de \\\\hul-vp-imagem-cc\\netshared.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        credentials = self._get_credentials()
        if credentials is None:
            return

        glpi_oauth = None
        if agent_key in ("glpi", "all"):
            glpi_oauth = CredentialStore.load_glpi_oauth()
            if not glpi_oauth:
                from core.config import get_glpi_oauth
                env_oauth = get_glpi_oauth()
                if env_oauth["id"] and env_oauth["secret"]:
                    glpi_oauth = env_oauth

            if not glpi_oauth or not glpi_oauth.get("id") or not glpi_oauth.get("secret"):
                QMessageBox.warning(
                    self, "OAuth GLPI Ausente",
                    "Para reparar o GLPI, configure as credenciais via:\n\n"
                    "1. Variáveis de ambiente: SARCC_GLPI_OAUTH_ID e SARCC_GLPI_OAUTH_SECRET\n"
                    "2. Ou use o cofre DPAPI (menu lateral > Configurações)."
                )
                return

        try:
            kwargs = {"agent_target": agent_key}
            if glpi_oauth:
                kwargs["glpi_oauth_id"] = glpi_oauth["id"]
                kwargs["glpi_oauth_secret"] = glpi_oauth["secret"]

            ps_script = load_ps_template("dashboard", "repair_agent", **kwargs)
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro Interno", f"Template de reparo não encontrado:\n{e}")
            return

        self.btn_repair_agent.setEnabled(False)
        self.btn_repair_agent.setText("⏳ Reparando...")

        self.queue_manager.add_task(
            target_pc=target,
            script_name=f"Reparo ({agent_label})",
            script_content=ps_script,
            module_name="[Dashboard] Agentes",
            credentials=credentials,
            on_finish=lambda t, s, d: self._on_repair_finished(t, s, d),
            on_error=lambda t, e: self._on_repair_error(t, e)
        )

    def _on_repair_finished(self, target_pc, status, json_data):
        self.btn_repair_agent.setEnabled(True)
        self.btn_repair_agent.setText("🔧 Reparar/Instalar")
        msg = json_data.get("Mensagem", "Operação concluída com sucesso.") if isinstance(json_data, dict) else "Concluído."
        QMessageBox.information(self, "Agente Reparado", f"[{target_pc}] {msg}")
        self.fetch_telemetry()

    def _on_repair_error(self, target_pc, error_msg):
        self.btn_repair_agent.setEnabled(True)
        self.btn_repair_agent.setText("🔧 Reparar/Instalar")
        QMessageBox.critical(self, "Falha no Reparo", f"Não foi possível reparar o agente em {target_pc}:\n\n{error_msg}")

    def _install_missing_client_tool(self, tool_name: str, winget_id: str, net_keyword: str) -> bool:
        """Oferece auto-instalação local (via Rede SMB ou Winget) caso falte a ferramenta na máquina do técnico."""
        reply = QMessageBox.question(
            self,
            f"{tool_name} Não Encontrado",
            f"O utilitário '{tool_name}' não foi encontrado nesta estação de trabalho.\n\n"
            f"Deseja que o SARCC instale o {tool_name} automaticamente agora na sua máquina?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if os.path.exists(self.NETWORK_SOFTWARE_SHARE):
                for fname in os.listdir(self.NETWORK_SOFTWARE_SHARE):
                    low = fname.lower()
                    if net_keyword.lower() in low and low.endswith((".exe", ".msi")):
                        installer_path = os.path.join(self.NETWORK_SOFTWARE_SHARE, fname)
                        if low.endswith(".msi"):
                            subprocess.run(
                                ["msiexec.exe", "/i", installer_path, "/qn", "/norestart"],
                                creationflags=subprocess.CREATE_NO_WINDOW
                            )
                        else:
                            subprocess.run(
                                [installer_path, "/S", "/silent", "/quiet", "/norestart"],
                                creationflags=subprocess.CREATE_NO_WINDOW
                            )
                        return True

            winget_exe = shutil.which("winget") or os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe")
            if winget_exe and os.path.exists(winget_exe):
                res = subprocess.run(
                    [
                        winget_exe, "install", "--id", winget_id,
                        "--exact", "--silent",
                        "--accept-package-agreements", "--accept-source-agreements",
                        "--disable-interactivity", "--source", "winget"
                    ],
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                return res.returncode == 0

            return False
        except Exception:
            return False
        finally:
            QApplication.restoreOverrideCursor()

    def action_connect(self):
        target = self.inp_target.text().strip()
        tool = self.cmb_remote.currentText()
        executor = os.environ.get("USERNAME", "Desconhecido")

        if tool != "Assistência Rápida" and not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo para conectar.")
            self.inp_target.setFocus()
            return

        conn = RemoteConnectionManager()

        try:
            if tool == "RDP (Windows)":
                subprocess.Popen(["mstsc", f"/v:{target}"])
            elif tool == "VNC Viewer":
                try:
                    conn.abrir_acesso_remoto(target)
                except FileNotFoundError:
                    if self._install_missing_client_tool("UltraVNC Viewer", "uvncbvba.UltraVNC", "vnc"):
                        conn.abrir_acesso_remoto(target)
                    else:
                        raise
            elif tool == "AnyDesk":
                anydesk_target = self._last_anydesk_id if self._last_anydesk_id else target
                try:
                    conn.abrir_anydesk(anydesk_target)
                except FileNotFoundError:
                    if self._install_missing_client_tool("AnyDesk", "AnyDeskSoftwareGmbH.AnyDesk", "anydesk"):
                        conn.abrir_anydesk(anydesk_target)
                    else:
                        raise
            elif tool == "Assistência Rápida":
                subprocess.Popen("start quickassist", shell=True)

            self.exec_repo.record_execution(
                target_pc=target if target else "Sessão Local",
                script_name=f"Acesso Remoto ({tool})",
                status="SUCESSO",
                result_data="Conexão solicitada via interface gráfica.",
                technician=executor,
                module="[Dashboard] Conexão"
            )
        except Exception as e:
            self.exec_repo.record_execution(
                target_pc=target if target else "Sessão Local",
                script_name=f"Acesso Remoto ({tool})",
                status="ERRO",
                result_data=str(e),
                technician=executor,
                module="[Dashboard] Conexão"
            )
            QMessageBox.warning(
                self,
                "Erro ao Iniciar Ferramenta",
                f"Não foi possível abrir '{tool}'.\n\nDetalhe: {e}"
            )

    def on_wol_success(self, target):
        self.btn_wol.setText("📡 WoL")
        self.btn_wol.setEnabled(True)
        QMessageBox.information(self, "Máquina Online!", f"O computador {target} já está ligado e respondendo a PING na rede!\n\nVocê já pode iniciar o Acesso Remoto.")

    def on_wol_timeout(self, target):
        self.btn_wol.setText("📡 WoL")
        self.btn_wol.setEnabled(True)
        QMessageBox.warning(self, "Tempo Esgotado", f"O pacote mágico foi enviado, mas o computador {target} não respondeu a ping após 5 minutos.\n\nVerifique se ele possui cabo de energia conectado ou se o WoL está habilitado na BIOS.")

    def action_wol(self):
        mac_text = self.lbl_mac.text().replace("MAC Address: ", "").replace("MAC: ", "").strip()
        alvo_text = self.inp_target.text().strip()
        executor = os.environ.get("USERNAME", "Desconhecido")

        if not mac_text or mac_text == "-" or mac_text == "N/A":
            if alvo_text.count(":") == 5 or alvo_text.count("-") == 5:
                mac_text = alvo_text
            else:
                mac_text, ok = QInputDialog.getText(
                    self, "Wake-on-LAN",
                    "A máquina está offline e sem telemetria.\n\nCole o MAC Address (Ex: 00:11:22:33:44:55):"
                )
                if not ok or not mac_text:
                    return

        mac_clean = mac_text.replace(':', '').replace('-', '').replace('.', '').upper()

        if len(mac_clean) != 12:
            QMessageBox.warning(self, "Erro", f"O formato do MAC Address fornecido parece inválido: {mac_text}")
            return

        try:
            data = bytes.fromhex('FF' * 6 + mac_clean * 16)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(data, ('255.255.255.255', 9))
            sock.sendto(data, ('255.255.255.255', 7))
            sock.close()

            target_log = alvo_text if alvo_text else mac_clean
            self.exec_repo.record_execution(
                target_pc=target_log,
                script_name="Wake-on-LAN",
                status="SUCESSO",
                result_data=f"Pacote Mágico disparado na rede para o MAC {mac_clean}",
                technician=executor,
                module="[Dashboard] Energia"
            )

            if alvo_text and (alvo_text.count(".") == 3 or not alvo_text.count(":")):
                self.btn_wol.setText("⏳...")
                self.btn_wol.setEnabled(False)
                self.ping_worker = PingTrackerWorker(alvo_text)
                self.ping_worker.success.connect(self.on_wol_success)
                self.ping_worker.timeout.connect(self.on_wol_timeout)
                self.ping_worker.start()
                QMessageBox.information(self, "Wake-on-LAN Disparado", "O Pacote Mágico foi enviado.\n\nO SARCC continuará testando a conectividade em segundo plano e te avisará assim que a máquina ligar.")
            else:
                QMessageBox.information(self, "Wake-on-LAN Disparado", f"O Pacote Mágico foi enviado com sucesso para o MAC:\n{mac_text}")

        except Exception as e:
            target_log = alvo_text if alvo_text else mac_clean
            self.exec_repo.record_execution(
                target_pc=target_log,
                script_name="Wake-on-LAN",
                status="ERRO",
                result_data=str(e),
                technician=executor,
                module="[Dashboard] Energia"
            )
            QMessageBox.critical(self, "Erro Crítico", f"Falha ao enviar o pacote Wake-on-LAN:\n{e}")

    def action_power(self, action_type):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        acoes = {
            "restart":  ("Reiniciar",     "power_restart"),
            "shutdown": ("Desligar",      "power_shutdown"),
            "logoff":   ("Forçar Logoff", "power_logoff"),
        }
        nome_acao, template_name = acoes[action_type]

        reply = QMessageBox.question(
            self, 'Confirmação Crítica',
            f'ATENÇÃO: Você está prestes a {nome_acao} o computador {target}.\n\nDeseja realmente prosseguir com esta ação disruptiva?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ps_script = load_ps_template("dashboard", template_name)
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro interno", f"Template ausente: {e}")
            return

        self.queue_manager.add_task(
            target_pc=target,
            script_name=f"Power: {nome_acao}",
            script_content=ps_script,
            module_name="[Dashboard] Energia",
            on_start=lambda t: None,
            on_finish=lambda t, s, d: None,
            on_error=lambda t, e: QMessageBox.critical(self, "Falha de Conexão", f"Não foi possível enviar o comando para {t}:\n{e}")
        )
        QMessageBox.information(self, "Comando Despachado", f"O comando de {nome_acao} foi enfileirado para envio a {target}.\n\nVocê pode conferir o resultado final na aba Histórico de Logs.")

    def fetch_telemetry(self):
        if getattr(self, 'is_fetching', False):
            if hasattr(self, 'worker') and self.worker.isRunning():
                self.worker.is_cancelled = True

            self._reset_fetch_button()
            agora = datetime.now().strftime('%H:%M:%S')
            self.lbl_last_sync.setText(f" Última atualização: Cancelado pelo usuário às {agora}")
            return

        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        self.is_fetching = True
        self.btn_fetch.setText("⛔ Cancelar Coleta")
        self.btn_fetch.setStyleSheet("background-color: #d9534f; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")

        agora = datetime.now().strftime('%H:%M:%S')
        self.lbl_last_sync.setText(f" Iniciado às: {agora}...")

        self.worker = TelemetryWorker(target)
        self.worker.finished.connect(self.update_telemetry_ui)
        self.worker.error.connect(self.show_telemetry_error)
        self.worker.start()

    def _reset_fetch_button(self):
        self.is_fetching = False
        self.btn_fetch.setText("🔄 Carregar Telemetria")
        self.btn_fetch.setStyleSheet("background-color: #2a7de1; color: white; padding: 0 15px; font-weight: bold; border-radius: 4px;")

    def update_telemetry_ui(self, data):
        if hasattr(self, "worker") and getattr(self.worker, 'is_cancelled', False):
            return

        self._reset_fetch_button()
        agora = datetime.now().strftime('%H:%M:%S')
        self.lbl_last_sync.setText(f" Última atualização: {agora}")

        pct = data.get("DiskPct", 0)
        free = data.get("DiskFree", 0)
        total = data.get("DiskTotal", 0)
        disk_type = data.get("DiskType", "Disco Local")
        disk_smart = data.get("DiskSmart", "N/A")

        self.prog_storage.setValue(int(pct))
        self.prog_storage.setStyleSheet(self._get_bar_style(pct))
        self.prog_storage.setFormat("%p%")
        self.lbl_storage_info.setText(f"Disco C:: Usado {pct}% ({free} GB livres de {total} GB)")
        self.lbl_disk_smart.setText(format_smart_badge(disk_type, disk_smart))

        cpuModel = data.get("CPUModel", "N/A")
        cpuUsage = data.get("CPUUsage", 0)
        self.prog_cpu.setValue(int(cpuUsage))
        self.prog_cpu.setStyleSheet(self._get_bar_style(cpuUsage))
        self.prog_cpu.setFormat("%p%")
        self.lbl_cpu_info.setText(f"CPU: {cpuModel}")

        tempVal = data.get("CPUTemp", "N/A")
        if tempVal != "N/A":
            tempVal = str(tempVal).replace(",", ".")

        if tempVal == "N/A" or float(tempVal) <= 0:
            self.prog_temp.setValue(0)
            self.prog_temp.setStyleSheet(self._get_bar_style(0, disabled=True))
            self.prog_temp.setFormat("N/A")
            self.lbl_temp_info.setText("Temperatura CPU: Sensor não suportado")
        else:
            t = float(tempVal)
            self.prog_temp.setValue(int(t))
            self.prog_temp.setStyleSheet(self._get_bar_style(t, is_temp=True))
            self.prog_temp.setFormat("%v°C")
            self.lbl_temp_info.setText("Temperatura CPU:")

        totalRam = data.get("TotalRAM", 0)
        usedRam = data.get("UsedRAM", 0)
        ramPct = data.get("RAMPct", 0)
        ramSlots = data.get("RAMSlots", "N/A")
        self.prog_ram.setValue(int(ramPct))
        self.prog_ram.setStyleSheet(self._get_bar_style(ramPct))
        self.prog_ram.setFormat("%p%")
        self.lbl_ram_info.setText(f"RAM: Usando {usedRam} GB de {totalRam} GB")
        self.lbl_ram_slots.setText(f"Topologia: {ramSlots}")

        profiles_list = data.get("ProfilesList", [])
        if not isinstance(profiles_list, list):
            profiles_list = [profiles_list] if profiles_list else []
        logged_names = set(data.get("LoggedNames", []) or [])
        self._last_profiles_list = profiles_list
        self._last_logged_names = logged_names

        total_prof_count = len(profiles_list)
        temp_prof_count = data.get("TempProfilesCount")
        if temp_prof_count is None:
            temp_prof_count = sum(1 for p in profiles_list if _is_temp_profile(p))

        if temp_prof_count > 0:
            self.lbl_profiles_count.setText(f"{total_prof_count} ({temp_prof_count} Temp)")
            self.lbl_profiles_count.setStyleSheet("font-size: 20px; font-weight: bold; color: #f0ad4e;")
        else:
            self.lbl_profiles_count.setText(str(total_prof_count))
            self.lbl_profiles_count.setStyleSheet("font-size: 22px; font-weight: bold; color: #2a7de1;")

        active_cnt = data.get("ActiveUsersCount")
        disc_cnt = data.get("DisconnectedUsersCount")
        if active_cnt is not None and disc_cnt is not None and disc_cnt > 0:
            self.lbl_logged_count.setText(f"{len(logged_names)} ({active_cnt} Ativo / {disc_cnt} Desc.)")
            self.lbl_logged_count.setStyleSheet("font-size: 18px; font-weight: bold; color: #f0ad4e;")
        else:
            self.lbl_logged_count.setText(str(len(logged_names)))
            self.lbl_logged_count.setStyleSheet("font-size: 22px; font-weight: bold; color: #4CAF50;")

        self._populate_profiles_table(profiles_list, logged_names)

        self.lbl_hostname.setText(f"Hostname: <b>{data.get('HostName', 'N/A')}</b>")
        desc = data.get("ComputerDesc", "Sem descrição")
        self._last_computer_desc = desc
        self.lbl_desc.setText(f"Descrição (Local): <span style='color: #5bc0de; font-weight: bold;'>{desc}</span>")
        self.lbl_hw_model.setText(f"Equipamento: <b>{data.get('HardwareModel', 'N/A')}</b>")
        self.lbl_serial.setText(f"Serial / BIOS: <b>{data.get('SerialNumber', 'N/A')}</b>")
        self.lbl_os.setText(f"SO: {data.get('OSVersion', 'N/A')}")
        self.lbl_uptime.setText(f"Uptime: {data.get('Uptime', 'N/A')}")
        self.lbl_ip.setText(f"IP: {data.get('IP', 'N/A')}")
        self.lbl_mac.setText(f"MAC: {data.get('MAC', 'N/A')}")

        av = data.get('AVProduct', 'N/A')
        self.lbl_av.setText(f"Antivírus: <span style='color: #4CAF50; font-weight: bold;'>{av}</span>")

        activation = data.get('Activation', 'N/A')
        if "Ativado" in activation:
            self.lbl_activation.setText(f"Status Atual: <span style='color: #4CAF50;'>{activation}</span>")
        else:
            self.lbl_activation.setText(f"Status Atual: <span style='color: #f44336;'>{activation}</span>")

        rdp = data.get('RDP', 'N/A')
        if rdp == "Ativado":
            self.lbl_rdp.setText(f"RDP: <span style='color: #4CAF50; font-weight: bold;'>{rdp}</span>")
        else:
            self.lbl_rdp.setText(f"RDP: <span style='color: #f44336; font-weight: bold;'>{rdp}</span>")

        vnc = data.get('VNC', 'N/A')
        if "Ativo" in vnc:
            self.lbl_vnc.setText(f"VNC: <span style='color: #4CAF50; font-weight: bold;'>{vnc}</span>")
        elif "Parado" in vnc:
            self.lbl_vnc.setText(f"VNC: <span style='color: #f44336; font-weight: bold;'>{vnc}</span>")
        else:
            self.lbl_vnc.setText(f"VNC: <span style='color: #888888; font-weight: bold;'>{vnc}</span>")

        anydesk = str(data.get('AnyDesk', 'N/A'))
        anydesk_digits = anydesk.replace(" ", "").strip()
        self._last_anydesk_id = anydesk_digits if anydesk_digits.isdigit() else ""

        if anydesk != "Não Instalado":
            self.lbl_anydesk.setText(f"AnyDesk ID: <span style='color: #4CAF50; font-weight: bold;'>{anydesk}</span>")
        else:
            self.lbl_anydesk.setText(f"AnyDesk ID: <span style='color: #888888; font-weight: bold;'>{anydesk}</span>")

        wol = data.get('WOL', 'N/A')
        if "Ativado" in wol:
            self.lbl_wol.setText(f"WoL (OS): <span style='color: #4CAF50; font-weight: bold;'>{wol}</span>")
        else:
            self.lbl_wol.setText(f"WoL (OS): <span style='color: #f44336; font-weight: bold;'>{wol}</span>")

        zabbix = data.get('Zabbix', 'N/A')
        if "Ativo" in zabbix:
            self.lbl_zabbix.setText(f"Zabbix: <span style='color: #4CAF50; font-weight: bold;'>{zabbix}</span>")
        elif "Parado" in zabbix:
            self.lbl_zabbix.setText(f"Zabbix: <span style='color: #f44336; font-weight: bold;'>{zabbix}</span>")
        else:
            self.lbl_zabbix.setText(f"Zabbix: <span style='color: #888888; font-weight: bold;'>{zabbix}</span>")

        glpi = data.get('GLPI', 'N/A')
        if "Ativo" in glpi:
            self.lbl_glpi.setText(f"GLPI: <span style='color: #4CAF50; font-weight: bold;'>{glpi}</span>")
        elif "Parado" in glpi:
            self.lbl_glpi.setText(f"GLPI: <span style='color: #f44336; font-weight: bold;'>{glpi}</span>")
        else:
            self.lbl_glpi.setText(f"GLPI: <span style='color: #888888; font-weight: bold;'>{glpi}</span>")

        dinfo = data.get('DesktopInfo', 'N/A')
        if "Ativo" in dinfo:
            self.lbl_desktopinfo.setText(f"Desktop Info: <span style='color: #4CAF50; font-weight: bold;'>{dinfo}</span>")
        else:
            self.lbl_desktopinfo.setText(f"Desktop Info: <span style='color: #888888; font-weight: bold;'>{dinfo}</span>")

        wg = data.get('Winget', 'N/A')
        if "Instalado" in wg and "Não" not in wg:
            self.lbl_winget.setText(f"Winget: <span style='color: #4CAF50; font-weight: bold;'>{wg}</span>")
        else:
            self.lbl_winget.setText(f"Winget: <span style='color: #f44336; font-weight: bold;'>{wg}</span>")

        reboot = data.get('RebootPending', 'N/A')
        if "Pendente" in reboot:
            self.lbl_reboot.setText(
                f"Reboot: <span style='color: #f0ad4e; font-weight: bold;'>⚠️ {reboot}</span>"
            )
        elif reboot == "OK":
            self.lbl_reboot.setText(
                f"Reboot: <span style='color: #4CAF50; font-weight: bold;'>{reboot}</span>"
            )
        else:
            self.lbl_reboot.setText(
                f"Reboot: <span style='color: #888888; font-weight: bold;'>{reboot}</span>"
            )

    def show_telemetry_error(self, err):
        if hasattr(self, "worker") and getattr(self.worker, 'is_cancelled', False):
            return

        self._reset_fetch_button()
        agora = datetime.now().strftime('%H:%M:%S')
        self.lbl_last_sync.setText(f" Última atualização: Falha às {agora}")
        QMessageBox.warning(self, "Aviso Operacional", f"{err}")

    def _populate_profiles_table(self, profiles: list, logged_names: set):
        self.tbl_profiles.setSortingEnabled(False)
        self.tbl_profiles.horizontalHeader().setSortIndicatorShown(False)
        self.tbl_profiles.setRowCount(0)

        if not profiles:
            self.btn_view_all_profiles.setVisible(False)
            return

        profiles_sorted = _sort_profiles(profiles, logged_names)

        for p in profiles_sorted[:5]:
            row = self.tbl_profiles.rowCount()
            self.tbl_profiles.insertRow(row)

            name = p.get("Name", "?")
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, p)
            self.tbl_profiles.setItem(row, 0, name_item)

            last_use_item = QTableWidgetItem(_format_last_use(p.get("LastUse", "N/A")))
            self.tbl_profiles.setItem(row, 1, last_use_item)

            status_text, color, _ = format_profile_session_status(p, logged_names)
            status_item = QTableWidgetItem(status_text)
            if color is not None:
                status_item.setForeground(color)
            self.tbl_profiles.setItem(row, 2, status_item)

        total = len(profiles)
        if total > 5:
            self.btn_view_all_profiles.setText(f"Ver todos ({total}) →")
            self.btn_view_all_profiles.setVisible(True)
        else:
            self.btn_view_all_profiles.setVisible(False)

    def _open_profiles_dialog(self):
        profiles = getattr(self, "_last_profiles_list", [])
        logged_names = getattr(self, "_last_logged_names", set())
        target = self.inp_target.text().strip() or "N/A"
        dlg = ProfilesDialog(
            profiles, logged_names, target,
            on_logoff_callback=self.action_logoff_specific_user,
            parent=self
        )
        dlg.exec()

    def change_windows_key(self):
        target = self.inp_target.text().strip()
        if not target:
            QMessageBox.warning(self, "Aviso", "Informe o computador alvo.")
            self.inp_target.setFocus()
            return

        version_name = self.cmb_license.currentText()
        gblk_key = self.cmb_license.currentData()

        reply = QMessageBox.question(
            self,
            'Confirmar Mudança de Edição',
            f"Alterar a EDIÇÃO do Windows em {target}?\n\n"
            f"Nova edição: {version_name}\n"
            f"Chave GVLK:  {gblk_key}\n\n"
            "AVISO: Esta ação troca a edição (Pro ↔ Education ↔ Enterprise).\n"
            "Não atualiza a versão do OS (Windows 10 ↔ Windows 11).\n\n"
            "Prosseguir?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            ps_script = load_ps_template(
                "dashboard", "change_windows_key",
                gblk_key=gblk_key,
                version_name=version_name,
            )
        except PsTemplateError as e:
            QMessageBox.critical(self, "Erro interno", f"Template ausente: {e}")
            return

        self.queue_manager.add_task(
            target_pc=target,
            script_name=f"Licença {version_name}",
            script_content=ps_script,
            module_name="[Dashboard] Licenciamento",
            on_start=lambda t: None,
            on_finish=lambda t, s, d: None,
            on_error=lambda t, e: QMessageBox.critical(self, "Erro", f"Falha na injeção da chave:\n{e}")
        )
        QMessageBox.information(self, "Ação Iniciada", "A chave está sendo processada em segundo plano. Verifique o Histórico de Logs em alguns instantes.")
